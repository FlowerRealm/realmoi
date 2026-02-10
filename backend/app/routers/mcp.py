from __future__ import annotations

import asyncio
import base64
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi import UploadFile

from ..auth import decode_access_token
from ..db import SessionLocal
from ..models import User
from ..settings import SETTINGS
from ..services.job_paths import get_job_paths
from ..services.job_tests import list_job_tests, read_job_test_preview
from ..services import singletons
from ..utils.fs import read_json
from . import jobs as jobs_router
from ..services.mcp_judge import McpJudgeWebSocketSession
from . import models as models_router


router = APIRouter(prefix="/mcp", tags=["mcp"])


def _ws_error(*, code: int, message: str) -> dict[str, Any]:
    return {"code": code, "message": message}


def _read_token_from_ws(ws: WebSocket) -> str:
    token = str((ws.query_params.get("token") or ws.query_params.get("access_token") or "")).strip()
    if token:
        return token
    auth = str(ws.headers.get("authorization") or "").strip()
    if auth.startswith("Bearer "):
        return auth.removeprefix("Bearer ").strip()
    return ""


def _authenticate_token(*, token: str) -> str:
    if not token:
        raise ValueError("missing_token")
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise ValueError("invalid_token")
    return user_id


def _load_user(*, user_id: str) -> User | None:
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None or user.is_disabled:
            return None
        return user


@dataclass
class _Subscription:
    job_id: str
    stream: str
    task: asyncio.Task[None]


class McpWebSocketSession:
    def __init__(self, *, ws: WebSocket, user: User):
        self._ws = ws
        self._user = user
        self._send_lock = asyncio.Lock()
        self._subscriptions: dict[tuple[str, str], _Subscription] = {}

    async def _send_json(self, payload: dict[str, Any]) -> None:
        async with self._send_lock:
            await self._ws.send_text(json.dumps(payload, ensure_ascii=False))

    async def send_result(self, *, msg_id: Any, result: dict[str, Any]) -> None:
        await self._send_json({"jsonrpc": "2.0", "id": msg_id, "result": result})

    async def send_error(self, *, msg_id: Any, code: int, message: str) -> None:
        await self._send_json({"jsonrpc": "2.0", "id": msg_id, "error": _ws_error(code=code, message=message)})

    async def notify(self, *, method: str, params: dict[str, Any]) -> None:
        await self._send_json({"jsonrpc": "2.0", "method": method, "params": params})

    def _ensure_job_access(self, *, job_id: str) -> None:
        paths = get_job_paths(jobs_root=Path(jobs_router.SETTINGS.jobs_root), job_id=job_id)
        if not paths.state_json.exists():
            raise FileNotFoundError(job_id)
        st = read_json(paths.state_json)
        if self._user.role != "admin" and str(st.get("owner_user_id") or "") != self._user.id:
            raise FileNotFoundError(job_id)

    async def _tail_agent_status(self, *, job_id: str, offset: int) -> None:
        paths = get_job_paths(jobs_root=Path(jobs_router.SETTINGS.jobs_root), job_id=job_id)
        path = paths.agent_status_jsonl
        current_offset = max(0, int(offset or 0))
        buf = b""

        while True:
            # Cancellation check.
            await asyncio.sleep(0)

            if path.exists():
                with path.open("rb") as f:
                    f.seek(current_offset)
                    chunk = f.read(64 * 1024)
                    if chunk:
                        current_offset = f.tell()
                        buf += chunk
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                item = json.loads(line.decode("utf-8"))
                            except Exception:
                                continue
                            payload = {"job_id": job_id, "offset": current_offset - len(buf), "item": item}
                            await self.notify(method="agent_status", params=payload)
                        await asyncio.sleep(0.05)
                        continue

            await asyncio.sleep(0.25)

    async def _tail_terminal(self, *, job_id: str, offset: int) -> None:
        paths = get_job_paths(jobs_root=Path(jobs_router.SETTINGS.jobs_root), job_id=job_id)
        path = paths.terminal_log
        current_offset = max(0, int(offset or 0))

        while True:
            await asyncio.sleep(0)

            if path.exists():
                with path.open("rb") as f:
                    f.seek(current_offset)
                    chunk = f.read(64 * 1024)
                    if chunk:
                        current_offset = f.tell()
                        payload = {
                            "job_id": job_id,
                            "offset": current_offset,
                            "chunk_b64": base64.b64encode(chunk).decode("ascii"),
                        }
                        await self.notify(method="terminal", params=payload)
                        await asyncio.sleep(0.05)
                        continue

            await asyncio.sleep(0.25)

    def _cancel_subscription(self, *, job_id: str, stream: str) -> None:
        key = (job_id, stream)
        sub = self._subscriptions.pop(key, None)
        if sub is None:
            return
        try:
            sub.task.cancel()
        except Exception:
            return

    def _cancel_all_subscriptions(self) -> None:
        for sub in list(self._subscriptions.values()):
            try:
                sub.task.cancel()
            except Exception:
                pass
        self._subscriptions.clear()

    async def tool_list(self, *, msg_id: Any) -> None:
        tools = [
            {
                "name": "models.list",
                "description": "List available models. {live:true} fetches upstream models when possible.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {"live": {"type": "boolean"}},
                },
            },
            {
                "name": "job.create",
                "description": "Create a new job. tests_zip_b64 is base64 of tests.zip (optional).",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {
                        "model": {"type": "string"},
                        "upstream_channel": {"type": "string"},
                        "statement_md": {"type": "string"},
                        "current_code_cpp": {"type": "string"},
                        "tests_zip_b64": {"type": "string"},
                        "tests_format": {"type": "string"},
                        "compare_mode": {"type": "string"},
                        "run_if_no_expected": {"type": "boolean"},
                        "search_mode": {"type": "string"},
                        "reasoning_effort": {"type": "string"},
                        "time_limit_ms": {"type": "integer"},
                        "memory_limit_mb": {"type": "integer"},
                    },
                    "required": ["model", "statement_md"],
                },
            },
            {
                "name": "job.start",
                "description": "Start a job.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                },
            },
            {
                "name": "job.cancel",
                "description": "Cancel a job.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                },
            },
            {
                "name": "job.get_state",
                "description": "Get job state.json payload.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                },
            },
            {
                "name": "job.get_artifacts",
                "description": "Get job artifacts (main.cpp/solution.json/report.json).",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {"job_id": {"type": "string"}, "names": {"type": "array", "items": {"type": "string"}}},
                    "required": ["job_id"],
                },
            },
            {
                "name": "job.get_tests",
                "description": "List extracted tests (from user tests.zip).",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                },
            },
            {
                "name": "job.get_test_preview",
                "description": "Read preview text for a single test input/expected (tests/xx.in/.out).",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {
                        "job_id": {"type": "string"},
                        "input_rel": {"type": "string"},
                        "expected_rel": {"type": ["string", "null"]},
                        "max_bytes": {"type": "integer"},
                    },
                    "required": ["job_id", "input_rel"],
                },
            },
            {
                "name": "job.subscribe",
                "description": "Subscribe streams for a job; pushes JSON-RPC notifications: agent_status/terminal.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {
                        "job_id": {"type": "string"},
                        "streams": {"type": "array", "items": {"type": "string"}},
                        "agent_status_offset": {"type": "integer"},
                        "terminal_offset": {"type": "integer"},
                    },
                    "required": ["job_id"],
                },
            },
            {
                "name": "job.unsubscribe",
                "description": "Unsubscribe streams for a job.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {"job_id": {"type": "string"}, "streams": {"type": "array", "items": {"type": "string"}}},
                    "required": ["job_id"],
                },
            },
        ]
        await self.send_result(msg_id=msg_id, result={"tools": tools})

    async def tool_call(self, *, msg_id: Any, name: str, arguments: dict[str, Any]) -> None:
        tool = str(name or "")
        args = arguments if isinstance(arguments, dict) else {}

        try:
            if tool == "models.list":
                live = bool(args.get("live", True))
                with SessionLocal() as db:
                    if live:
                        rows = models_router.list_live_models(self._user, db=db)
                    else:
                        rows = models_router.list_models(self._user, db=db)
                payload = [r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in (rows or [])]
                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": {"items": payload}},
                )
                return

            if tool == "job.create":
                model = str(args.get("model") or "").strip()
                upstream_channel = str(args.get("upstream_channel") or "").strip() or None
                statement_md = str(args.get("statement_md") or "")
                current_code_cpp = str(args.get("current_code_cpp") or "")
                tests_zip_b64 = str(args.get("tests_zip_b64") or "").strip()
                tests_format = str(args.get("tests_format") or "auto")
                compare_mode = str(args.get("compare_mode") or "tokens")
                run_if_no_expected = bool(args.get("run_if_no_expected", True))
                search_mode = str(args.get("search_mode") or jobs_router.SETTINGS.default_search_mode)
                reasoning_effort = str(args.get("reasoning_effort") or "medium")
                time_limit_ms = args.get("time_limit_ms")
                memory_limit_mb = args.get("memory_limit_mb")

                upload: UploadFile | None = None
                if tests_zip_b64:
                    try:
                        zip_bytes = base64.b64decode(tests_zip_b64.encode("ascii"), validate=True)
                    except Exception:
                        raise ValueError("invalid_tests_zip_b64") from None
                    upload = UploadFile(filename="tests.zip", file=io.BytesIO(zip_bytes))

                with SessionLocal() as db:
                    resp = jobs_router.create_job(
                        user=self._user,
                        db=db,
                        model=model,
                        upstream_channel=upstream_channel,
                        statement_md=statement_md,
                        current_code_cpp=current_code_cpp,
                        tests_zip=upload,
                        tests_format=tests_format,  # type: ignore[arg-type]
                        compare_mode=compare_mode,  # type: ignore[arg-type]
                        run_if_no_expected=run_if_no_expected,
                        search_mode=search_mode,  # type: ignore[arg-type]
                        reasoning_effort=reasoning_effort,  # type: ignore[arg-type]
                        time_limit_ms=time_limit_ms,
                        memory_limit_mb=memory_limit_mb,
                    )

                payload = resp.model_dump() if hasattr(resp, "model_dump") else resp.dict()
                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": payload},
                )
                return

            if tool == "job.start":
                job_id = str(args.get("job_id") or "").strip()
                jm = singletons.JOB_MANAGER
                if jm is None:
                    raise RuntimeError("job_manager_not_ready")
                result = jobs_router.start_job(self._user, job_id=job_id, jm=jm)
                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": result},
                )
                return

            if tool == "job.cancel":
                job_id = str(args.get("job_id") or "").strip()
                jm = singletons.JOB_MANAGER
                if jm is None:
                    raise RuntimeError("job_manager_not_ready")
                result = jobs_router.cancel_job(self._user, job_id=job_id, jm=jm)
                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": result},
                )
                return

            if tool == "job.get_state":
                job_id = str(args.get("job_id") or "").strip()
                state = jobs_router.get_job(self._user, job_id=job_id)
                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": state},
                )
                return

            if tool == "job.get_artifacts":
                job_id = str(args.get("job_id") or "").strip()
                names = args.get("names")
                want = [str(x) for x in names] if isinstance(names, list) else ["main.cpp", "solution.json", "report.json"]
                want_set = {x for x in want if x in {"main.cpp", "solution.json", "report.json"}}

                self._ensure_job_access(job_id=job_id)
                paths = get_job_paths(jobs_root=Path(jobs_router.SETTINGS.jobs_root), job_id=job_id)
                result: dict[str, Any] = {}
                for name in ("main.cpp", "solution.json", "report.json"):
                    if name not in want_set:
                        continue
                    file_path = paths.output_dir / name
                    if not file_path.exists():
                        continue
                    if name.endswith(".json"):
                        try:
                            result[name] = json.loads(file_path.read_text(encoding="utf-8"))
                        except Exception:
                            continue
                    else:
                        result[name] = file_path.read_text(encoding="utf-8", errors="replace")

                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": {"items": result}},
                )
                return

            if tool == "job.get_tests":
                job_id = str(args.get("job_id") or "").strip()
                self._ensure_job_access(job_id=job_id)
                paths = get_job_paths(jobs_root=Path(jobs_router.SETTINGS.jobs_root), job_id=job_id)
                metas = list_job_tests(job_json_path=paths.job_json, tests_dir=paths.tests_dir)
                items = [
                    {
                        "name": m.name,
                        "group": m.group,
                        "input_rel": m.input_rel,
                        "expected_rel": m.expected_rel,
                        "expected_present": m.expected_present,
                    }
                    for m in metas
                ]
                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": {"items": items, "total": len(items)}},
                )
                return

            if tool == "job.get_test_preview":
                job_id = str(args.get("job_id") or "").strip()
                input_rel = str(args.get("input_rel") or "").strip()
                expected_rel = args.get("expected_rel")
                expected_rel_s = str(expected_rel).strip() if isinstance(expected_rel, str) else None
                max_bytes = int(args.get("max_bytes") or 0)

                self._ensure_job_access(job_id=job_id)
                paths = get_job_paths(jobs_root=Path(jobs_router.SETTINGS.jobs_root), job_id=job_id)
                payload = read_job_test_preview(
                    tests_dir=paths.tests_dir,
                    input_rel=input_rel,
                    expected_rel=expected_rel_s,
                    max_bytes=max_bytes,
                )
                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": payload},
                )
                return

            if tool == "job.subscribe":
                job_id = str(args.get("job_id") or "").strip()
                streams = args.get("streams")
                stream_list = [str(x) for x in streams] if isinstance(streams, list) else ["agent_status"]
                want_agent = "agent_status" in stream_list
                want_terminal = "terminal" in stream_list

                self._ensure_job_access(job_id=job_id)

                if want_agent:
                    agent_offset = int(args.get("agent_status_offset") or 0)
                    self._cancel_subscription(job_id=job_id, stream="agent_status")
                    task = asyncio.create_task(self._tail_agent_status(job_id=job_id, offset=agent_offset))
                    self._subscriptions[(job_id, "agent_status")] = _Subscription(job_id=job_id, stream="agent_status", task=task)

                if want_terminal:
                    terminal_offset = int(args.get("terminal_offset") or 0)
                    self._cancel_subscription(job_id=job_id, stream="terminal")
                    task = asyncio.create_task(self._tail_terminal(job_id=job_id, offset=terminal_offset))
                    self._subscriptions[(job_id, "terminal")] = _Subscription(job_id=job_id, stream="terminal", task=task)

                subscribed = [s for s in ("agent_status", "terminal") if (job_id, s) in self._subscriptions]
                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": {"job_id": job_id, "streams": subscribed}},
                )
                return

            if tool == "job.unsubscribe":
                job_id = str(args.get("job_id") or "").strip()
                streams = args.get("streams")
                stream_list = [str(x) for x in streams] if isinstance(streams, list) else ["agent_status", "terminal"]
                for stream in stream_list:
                    if stream not in {"agent_status", "terminal"}:
                        continue
                    self._cancel_subscription(job_id=job_id, stream=stream)
                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": {"job_id": job_id, "streams": stream_list}},
                )
                return

        except FileNotFoundError:
            await self.send_error(msg_id=msg_id, code=404, message="not_found")
            return
        except ValueError as e:
            await self.send_error(msg_id=msg_id, code=422, message=str(e))
            return
        except Exception as e:
            await self.send_error(msg_id=msg_id, code=500, message=f"{type(e).__name__}: {e}")
            return

        await self.send_error(msg_id=msg_id, code=-32601, message="Tool not found")

    async def close(self) -> None:
        self._cancel_all_subscriptions()


@router.websocket("/ws")
async def mcp_ws(ws: WebSocket):
    token = _read_token_from_ws(ws)
    judge_token = str(SETTINGS.judge_mcp_token or "").strip()
    is_judge = bool(judge_token and token == judge_token)

    if is_judge:
        await ws.accept()
        session: Any = McpJudgeWebSocketSession(ws=ws)
    else:
        try:
            user_id = _authenticate_token(token=token)
        except Exception:
            await ws.accept()
            await ws.send_text(
                json.dumps({"jsonrpc": "2.0", "error": _ws_error(code=401, message="unauthorized")}, ensure_ascii=False)
            )
            await ws.close(code=1008)
            return

        user = _load_user(user_id=user_id)
        if user is None:
            await ws.accept()
            await ws.send_text(
                json.dumps({"jsonrpc": "2.0", "error": _ws_error(code=403, message="forbidden")}, ensure_ascii=False)
            )
            await ws.close(code=1008)
            return

        await ws.accept()
        session = McpWebSocketSession(ws=ws, user=user)

    try:
        while True:
            try:
                raw = await ws.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:
                break

            try:
                msg = json.loads(raw)
            except Exception:
                continue

            msg_id = msg.get("id")
            method = msg.get("method")
            params = msg.get("params") if isinstance(msg.get("params"), dict) else {}

            if method == "initialize":
                await session.send_result(
                    msg_id=msg_id,
                    result={
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "realmoi-mcp", "version": "0.1.0", "role": "judge" if is_judge else "user"},
                    },
                )
                continue

            if method == "ping":
                await session.send_result(msg_id=msg_id, result={})
                continue

            if method == "tools/list":
                await session.tool_list(msg_id=msg_id)
                continue

            if method == "tools/call":
                tool_name = str(params.get("name") or "")
                arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
                await session.tool_call(msg_id=msg_id, name=tool_name, arguments=arguments)
                continue

            if msg_id is not None:
                await session.send_error(msg_id=msg_id, code=-32601, message="Method not found")
    finally:
        try:
            await session.close()
        except Exception:
            pass
