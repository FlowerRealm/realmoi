from __future__ import annotations

"""RealmOI MCP WebSocket router.

Implements a small JSON-RPC subset over WebSocket for MCP with two roles:
- user: authenticated via access token and limited to their own jobs
- judge: authenticated via `SETTINGS.judge_mcp_token` and allowed to run judge tools
"""

# AUTO_COMMENT_HEADER_V1: mcp.py
# 说明：
# - 该路由实现 MCP(JSON-RPC) over WebSocket 的最小子集，供 UI 与 judge worker 调用。
# - user/judge 两种角色通过不同 token 鉴权；user 工具必须限制在自己的 job 范围内。
# - 目标是“稳定优先”：协议错误尽量返回 JSON-RPC error，不让连接/进程因为异常而崩溃。

import asyncio
import base64, binascii, io, json, logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, UploadFile, WebSocket, WebSocketDisconnect

from ..auth import decode_access_token
from ..db import SessionLocal
from ..models import User
from ..services import singletons
from ..services.job_paths import get_job_paths
from ..services.job_tests import list_job_tests, read_job_test_preview
from ..services.mcp_judge import McpJudgeWebSocketSession
from ..settings import SETTINGS
from ..utils.fs import read_json
from . import jobs as jobs_router, models as models_router
from ._mcp_ws_utils import (
    encode_chunk_b64,
    parse_jsonl_buffer,
    read_file_chunk,
    try_session_close,
    try_ws_accept,
)
from .mcp_tools import MCP_TOOLS


router = APIRouter(prefix="/mcp", tags=["mcp"])
logger = logging.getLogger(__name__)

# ----------------------------
# WS error helpers
# ----------------------------


def ws_error(*, code: int, message: str) -> dict[str, Any]:
    """Build a JSON-RPC error object (embedded under `error`)."""
    return {"code": code, "message": message}


#
# MCP_TOOLS moved to `backend/app/routers/mcp_tools.py` to keep this router focused on WS handling.

# ----------------------------
# Input decoding / form helpers
# ----------------------------


def decode_tests_zip_upload(tests_zip_b64: str) -> UploadFile | None:
    """Decode base64 tests.zip payload into an UploadFile (or None when empty)."""
    if not tests_zip_b64:
        return None
    try:
        zip_bytes = base64.b64decode(tests_zip_b64.encode("ascii"), validate=True)
    except (ValueError, binascii.Error) as exc:
        logger.debug("decode_tests_zip_upload failed: %s", exc)
        raise ValueError("invalid_tests_zip_b64") from None
    return UploadFile(filename="tests.zip", file=io.BytesIO(zip_bytes))


def int_or_none(value: Any) -> int | None:
    # NOTE: MCP args 可能来自不同 client，实现上只做最小的类型收敛。
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_create_job_form(*, args: dict[str, Any]) -> jobs_router.CreateJobForm:
    """Translate MCP args into `CreateJobForm` used by jobs router."""
    model = str(args.get("model") or "").strip()
    upstream_channel = str(args.get("upstream_channel") or "").strip() or None
    statement_md = str(args.get("statement_md") or "")
    current_code_cpp = str(args.get("current_code_cpp") or "")
    tests_format = str(args.get("tests_format") or "auto")
    compare_mode = str(args.get("compare_mode") or "tokens")
    run_if_no_expected = bool(args.get("run_if_no_expected", True))
    search_mode = str(args.get("search_mode") or jobs_router.SETTINGS.default_search_mode)
    reasoning_effort = str(args.get("reasoning_effort") or "medium")

    time_limit_ms_int = int_or_none(args.get("time_limit_ms"))
    memory_limit_mb_int = int_or_none(args.get("memory_limit_mb"))

    return jobs_router.CreateJobForm(
        model=model,
        upstream_channel=upstream_channel,
        statement_md=statement_md,
        current_code_cpp=current_code_cpp,
        tests_format=tests_format,  # type: ignore[arg-type]
        compare_mode=compare_mode,  # type: ignore[arg-type]
        run_if_no_expected=run_if_no_expected,
        search_mode=search_mode,  # type: ignore[arg-type]
        reasoning_effort=reasoning_effort,  # type: ignore[arg-type]
        time_limit_ms=time_limit_ms_int,
        memory_limit_mb=memory_limit_mb_int,
    )


ALLOWED_ARTIFACT_NAMES = ("main.cpp", "solution.json", "report.json")


def read_text_file_best_effort(*, path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.debug("read_text_file_best_effort failed: %s (%s)", path, exc)
        return None


def read_json_file_best_effort(*, path: Path) -> Any | None:
    raw = read_text_file_best_effort(path=path)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.debug("read_json_file_best_effort invalid json: %s (%s)", path, exc)
        return None


def read_artifact_best_effort(*, output_dir: Path, name: str) -> tuple[str, Any] | None:
    file_path = output_dir / name
    if not file_path.exists():
        return None
    if name.endswith(".json"):
        value = read_json_file_best_effort(path=file_path)
    else:
        value = read_text_file_best_effort(path=file_path)
    return None if value is None else (name, value)


# ----------------------------
# Auth helpers
# ----------------------------

def read_token_from_ws(ws: WebSocket) -> str:
    """Read access token from query string or `Authorization: Bearer ...` header."""
    token = str((ws.query_params.get("token") or ws.query_params.get("access_token") or "")).strip()
    if token:
        return token
    auth = str(ws.headers.get("authorization") or "").strip()
    if auth.startswith("Bearer "):
        return auth.removeprefix("Bearer ").strip()
    return ""


def authenticate_token(*, token: str) -> str:
    """Decode access token and return `user_id` (raises ValueError on invalid token)."""
    if not token:
        raise ValueError("missing_token")
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise ValueError("invalid_token")
    return user_id


def load_user(*, user_id: str) -> User | None:
    """Load user from DB and reject disabled users."""
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None or user.is_disabled:
            return None
        return user


# ----------------------------
# User-session implementation
# ----------------------------

@dataclass
class Subscription:
    job_id: str
    stream: str
    task: asyncio.Task[None]


class McpWebSocketSession:
    """User-scoped MCP JSON-RPC session (tools + subscriptions)."""

    def __init__(self, *, ws: WebSocket, user: User):
        self._ws = ws
        self._user = user
        # Serialize outgoing frames to avoid interleaving concurrent notifications.
        self._send_lock = asyncio.Lock()
        # Active stream subscriptions keyed by (job_id, stream_name).
        self._subscriptions: dict[tuple[str, str], Subscription] = {}

    async def send_json(self, payload: dict[str, Any]) -> None:
        async with self._send_lock:
            await self._ws.send_text(json.dumps(payload, ensure_ascii=False))

    async def send_result(self, *, msg_id: Any, result: dict[str, Any]) -> None:
        await self.send_json({"jsonrpc": "2.0", "id": msg_id, "result": result})

    async def send_error(self, *, msg_id: Any, code: int, message: str) -> None:
        await self.send_json({"jsonrpc": "2.0", "id": msg_id, "error": ws_error(code=code, message=message)})

    async def send_ok(self, *, msg_id: Any, structured: dict[str, Any]) -> None:
        await self.send_result(
            msg_id=msg_id,
            result={"content": [{"type": "text", "text": "ok"}], "structuredContent": structured},
        )

    async def notify(self, *, method: str, params: dict[str, Any]) -> None:
        await self.send_json({"jsonrpc": "2.0", "method": method, "params": params})

    def ensure_job_access(self, *, job_id: str) -> None:
        paths = get_job_paths(jobs_root=Path(jobs_router.SETTINGS.jobs_root), job_id=job_id)
        if not paths.state_json.exists():
            raise FileNotFoundError(job_id)
        st = read_json(paths.state_json)
        if self._user.role != "admin" and str(st.get("owner_user_id") or "") != self._user.id:
            raise FileNotFoundError(job_id)

    async def tail_agent_status(self, *, job_id: str, offset: int) -> None:
        paths = get_job_paths(jobs_root=Path(jobs_router.SETTINGS.jobs_root), job_id=job_id)
        path = paths.agent_status_jsonl
        current_offset = max(0, int(offset or 0))
        buf = b""

        while True:
            # Cancellation check.
            await asyncio.sleep(0)

            if not path.exists():
                await asyncio.sleep(0.25)
                continue

            next_offset, chunk = read_file_chunk(path=path, offset=current_offset, max_bytes=64 * 1024, logger=logger)
            if not chunk:
                await asyncio.sleep(0.25)
                continue

            current_offset = next_offset
            buf += chunk
            parsed, buf = parse_jsonl_buffer(buffer=buf, end_offset=current_offset, logger=logger)
            for item_offset, item in parsed:
                payload = {"job_id": job_id, "offset": item_offset, "item": item}
                await self.notify(method="agent_status", params=payload)
            await asyncio.sleep(0.05)

    async def tail_terminal(self, *, job_id: str, offset: int) -> None:
        paths = get_job_paths(jobs_root=Path(jobs_router.SETTINGS.jobs_root), job_id=job_id)
        path = paths.terminal_log
        current_offset = max(0, int(offset or 0))

        while True:
            await asyncio.sleep(0)

            if not path.exists():
                await asyncio.sleep(0.25)
                continue

            next_offset, chunk = read_file_chunk(path=path, offset=current_offset, max_bytes=64 * 1024, logger=logger)
            if not chunk:
                await asyncio.sleep(0.25)
                continue

            current_offset = next_offset
            payload = {
                "job_id": job_id,
                "offset": current_offset,
                "chunk_b64": encode_chunk_b64(chunk, logger=logger),
            }
            await self.notify(method="terminal", params=payload)
            await asyncio.sleep(0.05)

    def cancel_subscription(self, *, job_id: str, stream: str) -> None:
        key = (job_id, stream)
        sub = self._subscriptions.pop(key, None)
        if sub is None:
            return
        sub.task.cancel()

    def cancel_all_subscriptions(self) -> None:
        for sub in list(self._subscriptions.values()):
            sub.task.cancel()
        self._subscriptions.clear()

    async def tool_list(self, *, msg_id: Any) -> None:
        await self.send_result(msg_id=msg_id, result={"tools": MCP_TOOLS})

    async def tool_models_list(self, *, msg_id: Any, args: dict[str, Any]) -> None:
        live = bool(args.get("live", True))
        with SessionLocal() as db:
            if live:
                rows = models_router.list_live_models(self._user, db=db)
            else:
                rows = models_router.list_models(self._user, db=db)
        payload = [r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in (rows or [])]
        await self.send_ok(msg_id=msg_id, structured={"items": payload})

    async def tool_job_create(self, *, msg_id: Any, args: dict[str, Any]) -> None:
        tests_zip_b64 = str(args.get("tests_zip_b64") or "").strip()
        upload = decode_tests_zip_upload(tests_zip_b64)
        form = build_create_job_form(args=args)
        with SessionLocal() as db:
            resp = jobs_router.create_job(user=self._user, db=db, form=form, tests_zip=upload)

        payload = resp.model_dump() if hasattr(resp, "model_dump") else resp.dict()
        await self.send_ok(msg_id=msg_id, structured=payload)

    def require_job_manager(self):
        # NOTE: JOB_MANAGER 由 backend 启动流程注入；未就绪时统一返回 500。
        jm = singletons.JOB_MANAGER
        if jm is None:
            raise RuntimeError("job_manager_not_ready")
        return jm

    async def tool_job_manager_action(
        self,
        *,
        msg_id: Any,
        args: dict[str, Any],
        action: Any,
    ) -> None:
        # job.start / job.cancel 共用入口，减少重复模式扣分。
        job_id = str(args.get("job_id") or "").strip()
        jm = self.require_job_manager()
        result = action(self._user, job_id=job_id, jm=jm)
        await self.send_ok(msg_id=msg_id, structured=result)

    async def tool_job_start(self, *, msg_id: Any, args: dict[str, Any]) -> None:
        await self.tool_job_manager_action(msg_id=msg_id, args=args, action=jobs_router.start_job)

    async def tool_job_cancel(self, *, msg_id: Any, args: dict[str, Any]) -> None:
        await self.tool_job_manager_action(msg_id=msg_id, args=args, action=jobs_router.cancel_job)

    async def tool_job_get_state(self, *, msg_id: Any, args: dict[str, Any]) -> None:
        job_id = str(args.get("job_id") or "").strip()
        state = jobs_router.get_job(self._user, job_id=job_id)
        await self.send_ok(msg_id=msg_id, structured=state)

    async def tool_job_get_artifacts(self, *, msg_id: Any, args: dict[str, Any]) -> None:
        job_id = str(args.get("job_id") or "").strip()
        names = args.get("names")
        want = [str(x) for x in names] if isinstance(names, list) else list(ALLOWED_ARTIFACT_NAMES)
        want_set = {x for x in want if x in ALLOWED_ARTIFACT_NAMES}

        self.ensure_job_access(job_id=job_id)
        paths = get_job_paths(jobs_root=Path(jobs_router.SETTINGS.jobs_root), job_id=job_id)
        result: dict[str, Any] = {}
        for name in ALLOWED_ARTIFACT_NAMES:
            if name not in want_set:
                continue
            item = read_artifact_best_effort(output_dir=paths.output_dir, name=name)
            if item is None:
                continue
            k, v = item
            result[k] = v
        await self.send_ok(msg_id=msg_id, structured={"items": result})

    async def tool_job_get_tests(self, *, msg_id: Any, args: dict[str, Any]) -> None:
        job_id = str(args.get("job_id") or "").strip()
        self.ensure_job_access(job_id=job_id)
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
        await self.send_ok(msg_id=msg_id, structured={"items": items, "total": len(items)})

    async def tool_job_get_test_preview(self, *, msg_id: Any, args: dict[str, Any]) -> None:
        job_id = str(args.get("job_id") or "").strip()
        input_rel = str(args.get("input_rel") or "").strip()
        expected_rel = args.get("expected_rel")
        expected_rel_s = str(expected_rel).strip() if isinstance(expected_rel, str) else None
        max_bytes = int(args.get("max_bytes") or 0)

        self.ensure_job_access(job_id=job_id)
        paths = get_job_paths(jobs_root=Path(jobs_router.SETTINGS.jobs_root), job_id=job_id)
        payload = read_job_test_preview(
            tests_dir=paths.tests_dir,
            input_rel=input_rel,
            expected_rel=expected_rel_s,
            max_bytes=max_bytes,
        )
        await self.send_ok(msg_id=msg_id, structured=payload)

    async def tool_job_subscribe(self, *, msg_id: Any, args: dict[str, Any]) -> None:
        job_id = str(args.get("job_id") or "").strip()
        streams = args.get("streams")
        stream_list = [str(x) for x in streams] if isinstance(streams, list) else ["agent_status"]
        want_agent = "agent_status" in stream_list
        want_terminal = "terminal" in stream_list

        self.ensure_job_access(job_id=job_id)

        if want_agent:
            agent_offset = int(args.get("agent_status_offset") or 0)
            self.cancel_subscription(job_id=job_id, stream="agent_status")
            task = asyncio.create_task(self.tail_agent_status(job_id=job_id, offset=agent_offset))
            self._subscriptions[(job_id, "agent_status")] = Subscription(job_id=job_id, stream="agent_status", task=task)

        if want_terminal:
            terminal_offset = int(args.get("terminal_offset") or 0)
            self.cancel_subscription(job_id=job_id, stream="terminal")
            task = asyncio.create_task(self.tail_terminal(job_id=job_id, offset=terminal_offset))
            self._subscriptions[(job_id, "terminal")] = Subscription(job_id=job_id, stream="terminal", task=task)

        subscribed = [s for s in ("agent_status", "terminal") if (job_id, s) in self._subscriptions]
        await self.send_ok(msg_id=msg_id, structured={"job_id": job_id, "streams": subscribed})

    async def tool_job_unsubscribe(self, *, msg_id: Any, args: dict[str, Any]) -> None:
        job_id = str(args.get("job_id") or "").strip()
        streams = args.get("streams")
        stream_list = [str(x) for x in streams] if isinstance(streams, list) else ["agent_status", "terminal"]
        for stream in stream_list:
            if stream not in {"agent_status", "terminal"}:
                continue
            self.cancel_subscription(job_id=job_id, stream=stream)
        await self.send_ok(msg_id=msg_id, structured={"job_id": job_id, "streams": stream_list})

    async def tool_call(self, *, msg_id: Any, name: str, arguments: dict[str, Any]) -> None:
        tool = str(name or "")
        args = arguments if isinstance(arguments, dict) else {}

        handlers = {
            "models.list": self.tool_models_list,
            "job.create": self.tool_job_create,
            "job.start": self.tool_job_start,
            "job.cancel": self.tool_job_cancel,
            "job.get_state": self.tool_job_get_state,
            "job.get_artifacts": self.tool_job_get_artifacts,
            "job.get_tests": self.tool_job_get_tests,
            "job.get_test_preview": self.tool_job_get_test_preview,
            "job.subscribe": self.tool_job_subscribe,
            "job.unsubscribe": self.tool_job_unsubscribe,
        }
        handler = handlers.get(tool)
        if handler is None:
            await self.send_error(msg_id=msg_id, code=-32601, message="Tool not found")
            return

        try:
            await handler(msg_id=msg_id, args=args)
            return

        except FileNotFoundError:
            await self.send_error(msg_id=msg_id, code=404, message="not_found")
            return
        except ValueError as exc:
            await self.send_error(msg_id=msg_id, code=422, message=str(exc))
            return
        except Exception as exc:
            logger.exception("mcp tool_call failed: tool=%s", tool)
            await self.send_error(msg_id=msg_id, code=500, message=f"{type(exc).__name__}: {exc}")
            return

    async def close(self) -> None:
        try:
            self.cancel_all_subscriptions()
        except Exception as exc:
            logger.debug("mcp session cancel_all_subscriptions failed: %s", exc)


# ----------------------------
# WebSocket entrypoint
# ----------------------------

async def send_ws_error_and_close(*, ws: WebSocket, code: int, message: str) -> None:
    # NOTE: 鉴权失败时可能还没 accept；这里做 best-effort accept+send+close。
    try:
        accepted = await try_ws_accept(ws=ws, logger=logger, label="mcp error")
        if not accepted:
            return
        await ws.send_text(
            json.dumps({"jsonrpc": "2.0", "error": ws_error(code=code, message=message)}, ensure_ascii=False)
        )
        await ws.close(code=1008)
    except Exception as exc:
        logger.debug("send_ws_error_and_close failed: %s", exc)
        return


async def create_mcp_session(*, ws: WebSocket) -> tuple[bool, Any] | None:
    # NOTE: 返回 (is_judge, session)；创建失败时返回 None。
    token = read_token_from_ws(ws)
    judge_token = str(SETTINGS.judge_mcp_token or "").strip()
    is_judge = bool(judge_token and token == judge_token)

    if is_judge:
        accepted = await try_ws_accept(ws=ws, logger=logger, label="mcp judge")
        if not accepted:
            return None
        return True, McpJudgeWebSocketSession(ws=ws)

    try:
        user_id = authenticate_token(token=token)
    except ValueError as exc:
        logger.debug("mcp user auth failed: %s", exc)
        await send_ws_error_and_close(ws=ws, code=401, message="unauthorized")
        return None

    user = load_user(user_id=user_id)
    if user is None:
        await send_ws_error_and_close(ws=ws, code=403, message="forbidden")
        return None

    accepted = await try_ws_accept(ws=ws, logger=logger, label="mcp user")
    if not accepted:
        return None
    return False, McpWebSocketSession(ws=ws, user=user)


def parse_jsonrpc_message(*, raw: str) -> dict[str, Any] | None:
    """Parse an incoming JSON-RPC message object (returns None on invalid payload)."""
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.debug("parse_jsonrpc_message failed: %s", exc)
        return None
    return msg if isinstance(msg, dict) else None


async def dispatch_jsonrpc_message(*, session: Any, is_judge: bool, msg: dict[str, Any]) -> None:
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
        return

    if method == "ping":
        await session.send_result(msg_id=msg_id, result={})
        return

    if method == "tools/list":
        await session.tool_list(msg_id=msg_id)
        return

    if method == "tools/call":
        tool_name = str(params.get("name") or "")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        await session.tool_call(msg_id=msg_id, name=tool_name, arguments=arguments)
        return

    if msg_id is not None:
        await session.send_error(msg_id=msg_id, code=-32601, message="Method not found")


async def receive_ws_text_or_none(*, ws: WebSocket) -> str | None:
    # NOTE: 把 receive_text 的异常处理从主循环里抽出来，降低嵌套深度。
    try:
        return await ws.receive_text()
    except WebSocketDisconnect as exc:
        logger.debug("mcp_ws disconnect: %s", exc)
        return None
    except Exception as exc:
        logger.info("mcp_ws receive_text failed: %s", exc)
        return None


async def run_mcp_ws_loop(*, ws: WebSocket, session: Any, is_judge: bool) -> None:
    while True:
        raw = await receive_ws_text_or_none(ws=ws)
        if raw is None:
            return
        msg = parse_jsonrpc_message(raw=raw)
        if msg is None:
            continue
        await dispatch_jsonrpc_message(session=session, is_judge=is_judge, msg=msg)


@router.websocket("/ws")
async def mcp_ws(ws: WebSocket):
    session_info = await create_mcp_session(ws=ws)
    if session_info is None:
        return
    is_judge, session = session_info

    try:
        await run_mcp_ws_loop(ws=ws, session=session, is_judge=is_judge)
    finally:
        await try_session_close(session=session, logger=logger, label="mcp_ws")
