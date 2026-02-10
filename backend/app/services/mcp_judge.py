from __future__ import annotations

# 独立测评机（judge worker）通过统一 MCP WS（/api/mcp/ws）调用这些 tools。

import asyncio
import base64
import json
import os
from pathlib import Path
from typing import cast
from typing import Any

from fastapi import WebSocket

from ..db import SessionLocal
from ..models import ModelPricing, UserCodexSettings
from ..services import singletons
from ..services.codex_config import build_effective_config
from ..services.job_paths import JobPaths, get_job_paths
from ..services.upstream_channels import resolve_upstream_target
from ..services.usage_records import ingest_usage_payload
from ..settings import SETTINGS
from ..utils.fs import read_json, write_json

try:
    import fcntl  # type: ignore
except Exception:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]


def _ws_error(*, code: int, message: str) -> dict[str, Any]:
    return {"code": code, "message": message}


class McpJudgeWebSocketSession:
    def __init__(self, *, ws: WebSocket):
        self._ws = ws
        self._send_lock = asyncio.Lock()

    async def _send_json(self, payload: dict[str, Any]) -> None:
        async with self._send_lock:
            await self._ws.send_text(json.dumps(payload, ensure_ascii=False))

    async def send_result(self, *, msg_id: Any, result: dict[str, Any]) -> None:
        await self._send_json({"jsonrpc": "2.0", "id": msg_id, "result": result})

    async def send_error(self, *, msg_id: Any, code: int, message: str) -> None:
        await self._send_json({"jsonrpc": "2.0", "id": msg_id, "error": _ws_error(code=code, message=message)})

    async def tool_list(self, *, msg_id: Any) -> None:
        tools = [
            {
                "name": "judge.claim_next",
                "description": "Claim one queued job for independent judge worker.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {"machine_id": {"type": "string"}},
                    "required": ["machine_id"],
                },
            },
            {
                "name": "judge.release_claim",
                "description": "Release claim lock for a previously claimed job.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {"job_id": {"type": "string"}, "claim_id": {"type": "string"}},
                    "required": ["job_id", "claim_id"],
                },
            },
            {
                "name": "judge.job.get_state",
                "description": "Get job state.json payload (requires claim_id).",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {"job_id": {"type": "string"}, "claim_id": {"type": "string"}},
                    "required": ["job_id", "claim_id"],
                },
            },
            {
                "name": "judge.input.list",
                "description": "List files under job input/ (requires claim_id).",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {"job_id": {"type": "string"}, "claim_id": {"type": "string"}},
                    "required": ["job_id", "claim_id"],
                },
            },
            {
                "name": "judge.input.read_chunk",
                "description": "Read a chunk of an input file. Returns chunk_b64 + next_offset + eof (requires claim_id).",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {
                        "job_id": {"type": "string"},
                        "claim_id": {"type": "string"},
                        "path": {"type": "string"},
                        "offset": {"type": "integer"},
                        "max_bytes": {"type": "integer"},
                    },
                    "required": ["job_id", "claim_id", "path"],
                },
            },
            {
                "name": "judge.job.patch_state",
                "description": "Patch backend state.json (deep-merge) (requires claim_id).",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {
                        "job_id": {"type": "string"},
                        "claim_id": {"type": "string"},
                        "patch": {"type": "object"},
                    },
                    "required": ["job_id", "claim_id", "patch"],
                },
            },
            {
                "name": "judge.job.append_terminal",
                "description": "Append bytes to logs/terminal.log with offset check (requires claim_id).",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {
                        "job_id": {"type": "string"},
                        "claim_id": {"type": "string"},
                        "offset": {"type": "integer"},
                        "chunk_b64": {"type": "string"},
                    },
                    "required": ["job_id", "claim_id", "offset", "chunk_b64"],
                },
            },
            {
                "name": "judge.job.append_agent_status",
                "description": "Append bytes to logs/agent_status.jsonl with offset check (requires claim_id).",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {
                        "job_id": {"type": "string"},
                        "claim_id": {"type": "string"},
                        "offset": {"type": "integer"},
                        "chunk_b64": {"type": "string"},
                    },
                    "required": ["job_id", "claim_id", "offset", "chunk_b64"],
                },
            },
            {
                "name": "judge.job.put_artifacts",
                "description": "Write output artifacts main.cpp/solution.json/report.json (requires claim_id).",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {
                        "job_id": {"type": "string"},
                        "claim_id": {"type": "string"},
                        "main_cpp": {"type": "string"},
                        "solution_json": {"type": "object"},
                        "report_json": {"type": "object"},
                    },
                    "required": ["job_id", "claim_id"],
                },
            },
            {
                "name": "judge.prepare_generate",
                "description": "Prepare generate bundle (effective config + auth + upstream base url) (requires claim_id).",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {"job_id": {"type": "string"}, "claim_id": {"type": "string"}},
                    "required": ["job_id", "claim_id"],
                },
            },
            {
                "name": "judge.usage.ingest",
                "description": "Ingest usage.json payload into usage_records and persist usage artifacts (requires claim_id).",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {
                        "job_id": {"type": "string"},
                        "claim_id": {"type": "string"},
                        "attempt": {"type": "integer"},
                        "usage": {"type": "object"},
                    },
                    "required": ["job_id", "claim_id", "attempt", "usage"],
                },
            },
        ]
        await self.send_result(msg_id=msg_id, result={"tools": tools})

    def _get_paths(self, *, job_id: str) -> JobPaths:
        paths = get_job_paths(jobs_root=Path(SETTINGS.jobs_root), job_id=job_id)
        if not paths.state_json.exists():
            raise FileNotFoundError(job_id)
        return paths

    def _load_state(self, *, paths: JobPaths) -> dict[str, Any]:
        obj = read_json(paths.state_json)
        if not isinstance(obj, dict):
            raise ValueError("invalid_state")
        return cast(dict[str, Any], obj)

    def _ensure_claim(self, *, paths: JobPaths, claim_id: str) -> dict[str, Any]:
        state = self._load_state(paths=paths)
        expected = str(((state.get("judge") or {}).get("claim_id")) or "")
        if not expected or expected != claim_id:
            raise ValueError("claim_mismatch")
        return state

    def _deep_merge(self, dst: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(dst.get(key), dict):
                dst[key] = self._deep_merge(cast(dict[str, Any], dst.get(key) or {}), cast(dict[str, Any], value))
            else:
                dst[key] = value
        return dst

    def _resolve_input_file(self, *, paths: JobPaths, rel_path: str) -> Path:
        rel_path = str(rel_path or "").strip().replace("\\", "/")
        if not rel_path:
            raise ValueError("missing_path")
        if rel_path.startswith("/"):
            raise ValueError("invalid_path")
        parts = [p for p in rel_path.split("/") if p]
        if any(p in {".", ".."} for p in parts):
            raise ValueError("invalid_path")

        candidate = paths.input_dir.joinpath(*parts)
        try:
            candidate.resolve().relative_to(paths.input_dir.resolve())
        except Exception:
            raise ValueError("invalid_path") from None
        if not candidate.exists() or not candidate.is_file():
            raise FileNotFoundError(rel_path)
        return candidate

    def _append_with_offset_check(
        self,
        *,
        path: Path,
        offset: int,
        chunk: bytes,
        max_bytes: int,
    ) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("ab") as fp:
            try:
                if fcntl is not None:
                    fcntl.flock(fp.fileno(), fcntl.LOCK_EX)
                current_offset = int(fp.tell())
                if current_offset != int(offset or 0):
                    return {"ok": False, "code": "offset_mismatch", "current_offset": current_offset}
                if current_offset >= max_bytes:
                    return {"ok": True, "next_offset": current_offset, "written_bytes": 0}
                remaining = max_bytes - current_offset
                out = chunk[:remaining]
                fp.write(out)
                fp.flush()
                return {"ok": True, "next_offset": current_offset + len(out), "written_bytes": len(out)}
            finally:
                if fcntl is not None:
                    try:
                        fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
                    except Exception:
                        pass

    async def tool_call(self, *, msg_id: Any, name: str, arguments: dict[str, Any]) -> None:
        tool = str(name or "")
        args = arguments if isinstance(arguments, dict) else {}

        jm = singletons.JOB_MANAGER
        if jm is None:
            await self.send_error(msg_id=msg_id, code=500, message="job_manager_not_ready")
            return

        try:
            if tool == "judge.claim_next":
                machine_id = str(args.get("machine_id") or "").strip()
                if not machine_id:
                    raise ValueError("missing_machine_id")
                claimed = jm.claim_next_queued_job(machine_id=machine_id)
                if claimed is None:
                    payload: dict[str, Any] = {"claimed": False}
                else:
                    payload = {
                        "claimed": True,
                        "job_id": claimed.get("job_id"),
                        "owner_user_id": claimed.get("owner_user_id"),
                        "claim_id": claimed.get("claim_id"),
                    }
                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": payload},
                )
                return

            if tool == "judge.release_claim":
                job_id = str(args.get("job_id") or "").strip()
                claim_id = str(args.get("claim_id") or "").strip()
                if not job_id:
                    raise ValueError("missing_job_id")
                if not claim_id:
                    raise ValueError("missing_claim_id")
                released = jm.release_judge_claim(job_id=job_id, claim_id=claim_id)
                if not released:
                    await self.send_error(msg_id=msg_id, code=409, message="claim_mismatch")
                    return
                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": {"released": True}},
                )
                return

            if tool == "judge.job.get_state":
                job_id = str(args.get("job_id") or "").strip()
                claim_id = str(args.get("claim_id") or "").strip()
                if not job_id:
                    raise ValueError("missing_job_id")
                if not claim_id:
                    raise ValueError("missing_claim_id")
                paths = self._get_paths(job_id=job_id)
                state = self._ensure_claim(paths=paths, claim_id=claim_id)
                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": state},
                )
                return

            if tool == "judge.input.list":
                job_id = str(args.get("job_id") or "").strip()
                claim_id = str(args.get("claim_id") or "").strip()
                if not job_id:
                    raise ValueError("missing_job_id")
                if not claim_id:
                    raise ValueError("missing_claim_id")
                paths = self._get_paths(job_id=job_id)
                self._ensure_claim(paths=paths, claim_id=claim_id)

                base = paths.input_dir
                items: list[dict[str, Any]] = []
                for root, _dirs, files in os.walk(base):
                    root_path = Path(root)
                    for name in files:
                        p = root_path / name
                        try:
                            rel = p.relative_to(base).as_posix()
                        except Exception:
                            continue
                        try:
                            size = int(p.stat().st_size)
                        except OSError:
                            size = 0
                        items.append({"path": rel, "size": size})
                items.sort(key=lambda x: str(x.get("path") or ""))

                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": {"items": items}},
                )
                return

            if tool == "judge.input.read_chunk":
                job_id = str(args.get("job_id") or "").strip()
                claim_id = str(args.get("claim_id") or "").strip()
                rel_path = str(args.get("path") or "")
                offset = int(args.get("offset") or 0)
                max_bytes = int(args.get("max_bytes") or 0)
                max_bytes = max(1, min(max_bytes, 1024 * 1024))
                if not job_id:
                    raise ValueError("missing_job_id")
                if not claim_id:
                    raise ValueError("missing_claim_id")

                paths = self._get_paths(job_id=job_id)
                self._ensure_claim(paths=paths, claim_id=claim_id)
                file_path = self._resolve_input_file(paths=paths, rel_path=rel_path)

                with file_path.open("rb") as fp:
                    fp.seek(max(0, offset))
                    chunk = fp.read(max_bytes)
                    next_offset = int(fp.tell())
                eof = next_offset >= int(file_path.stat().st_size)
                payload = {
                    "path": rel_path.replace("\\", "/"),
                    "chunk_b64": base64.b64encode(chunk).decode("ascii"),
                    "next_offset": next_offset,
                    "eof": eof,
                }
                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": payload},
                )
                return

            if tool == "judge.job.patch_state":
                job_id = str(args.get("job_id") or "").strip()
                claim_id = str(args.get("claim_id") or "").strip()
                patch = args.get("patch")
                if not job_id:
                    raise ValueError("missing_job_id")
                if not claim_id:
                    raise ValueError("missing_claim_id")
                if not isinstance(patch, dict):
                    raise ValueError("invalid_patch")

                paths = self._get_paths(job_id=job_id)
                state = self._ensure_claim(paths=paths, claim_id=claim_id)
                current_status = str(state.get("status") or "")
                merged = self._deep_merge(state, cast(dict[str, Any], patch))
                if current_status == "cancelled":
                    merged["status"] = "cancelled"
                write_json(paths.state_json, merged)
                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": {"ok": True}},
                )
                return

            if tool == "judge.job.append_terminal":
                job_id = str(args.get("job_id") or "").strip()
                claim_id = str(args.get("claim_id") or "").strip()
                offset = int(args.get("offset") or 0)
                chunk_b64 = str(args.get("chunk_b64") or "").strip()
                if not job_id:
                    raise ValueError("missing_job_id")
                if not claim_id:
                    raise ValueError("missing_claim_id")
                if not chunk_b64:
                    raise ValueError("missing_chunk_b64")

                paths = self._get_paths(job_id=job_id)
                state = self._ensure_claim(paths=paths, claim_id=claim_id)
                max_bytes = int(
                    ((state.get("resource_limits") or {}).get("max_terminal_log_bytes"))
                    or SETTINGS.default_max_terminal_log_bytes
                )
                try:
                    chunk = base64.b64decode(chunk_b64.encode("ascii"), validate=True)
                except Exception:
                    raise ValueError("invalid_base64") from None

                payload = self._append_with_offset_check(
                    path=paths.terminal_log,
                    offset=offset,
                    chunk=chunk,
                    max_bytes=max_bytes,
                )
                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": payload},
                )
                return

            if tool == "judge.job.append_agent_status":
                job_id = str(args.get("job_id") or "").strip()
                claim_id = str(args.get("claim_id") or "").strip()
                offset = int(args.get("offset") or 0)
                chunk_b64 = str(args.get("chunk_b64") or "").strip()
                if not job_id:
                    raise ValueError("missing_job_id")
                if not claim_id:
                    raise ValueError("missing_claim_id")
                if not chunk_b64:
                    raise ValueError("missing_chunk_b64")

                paths = self._get_paths(job_id=job_id)
                state = self._ensure_claim(paths=paths, claim_id=claim_id)
                max_bytes = int(
                    ((state.get("resource_limits") or {}).get("max_terminal_log_bytes"))
                    or SETTINGS.default_max_terminal_log_bytes
                )
                try:
                    chunk = base64.b64decode(chunk_b64.encode("ascii"), validate=True)
                except Exception:
                    raise ValueError("invalid_base64") from None

                payload = self._append_with_offset_check(
                    path=paths.agent_status_jsonl,
                    offset=offset,
                    chunk=chunk,
                    max_bytes=max_bytes,
                )
                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": payload},
                )
                return

            if tool == "judge.job.put_artifacts":
                job_id = str(args.get("job_id") or "").strip()
                claim_id = str(args.get("claim_id") or "").strip()
                main_cpp = str(args.get("main_cpp") or "")
                solution_json = args.get("solution_json")
                report_json = args.get("report_json")
                if not job_id:
                    raise ValueError("missing_job_id")
                if not claim_id:
                    raise ValueError("missing_claim_id")

                paths = self._get_paths(job_id=job_id)
                state = self._ensure_claim(paths=paths, claim_id=claim_id)

                paths.output_dir.mkdir(parents=True, exist_ok=True)
                if main_cpp:
                    (paths.output_dir / "main.cpp").write_text(main_cpp.rstrip() + "\n", encoding="utf-8")
                    (state.setdefault("artifacts", {}))["main_cpp"] = True
                if isinstance(solution_json, dict):
                    write_json(paths.output_dir / "solution.json", solution_json)
                    (state.setdefault("artifacts", {}))["solution_json"] = True
                if isinstance(report_json, dict):
                    write_json(paths.output_dir / "report.json", report_json)
                    (state.setdefault("artifacts", {}))["report_json"] = True
                write_json(paths.state_json, state)

                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": {"ok": True}},
                )
                return

            if tool == "judge.prepare_generate":
                job_id = str(args.get("job_id") or "").strip()
                claim_id = str(args.get("claim_id") or "").strip()
                if not job_id:
                    raise ValueError("missing_job_id")
                if not claim_id:
                    raise ValueError("missing_claim_id")

                paths = self._get_paths(job_id=job_id)
                state = self._ensure_claim(paths=paths, claim_id=claim_id)
                owner_user_id = str(state.get("owner_user_id") or "").strip()
                if not owner_user_id:
                    raise ValueError("invalid_state")

                upstream_channel = str(state.get("upstream_channel") or "").strip()
                model = str(state.get("model") or "").strip()

                target = None
                with SessionLocal() as db:
                    row = db.get(UserCodexSettings, owner_user_id)
                    overrides = row.overrides_toml if row else ""
                    model_pricing = db.get(ModelPricing, model) if model else None
                    if not upstream_channel:
                        upstream_channel = (model_pricing.upstream_channel if model_pricing else "") or ""
                    if not SETTINGS.mock_mode:
                        try:
                            target = resolve_upstream_target(upstream_channel, db=db)
                        except ValueError as e:
                            raise ValueError(f"upstream_config_error:{e}") from None

                cfg = build_effective_config(user_overrides_toml=overrides)
                if SETTINGS.mock_mode:
                    openai_base_url = str(SETTINGS.openai_base_url or "")
                    auth_bytes = b"{}\n"
                else:
                    if target is None:
                        raise ValueError("upstream_config_error:missing_target")
                    openai_base_url = str(target.base_url or "")
                    auth_bytes = (json.dumps({"OPENAI_API_KEY": target.api_key}, ensure_ascii=False) + "\n").encode("utf-8")

                if not openai_base_url:
                    raise ValueError("upstream_config_error:missing_base_url")

                payload = {
                    "effective_config_toml": cfg.effective_config_toml,
                    "auth_json_b64": base64.b64encode(auth_bytes).decode("ascii"),
                    "openai_base_url": openai_base_url,
                    "mock_mode": bool(SETTINGS.mock_mode),
                }
                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": payload},
                )
                return

            if tool == "judge.usage.ingest":
                job_id = str(args.get("job_id") or "").strip()
                claim_id = str(args.get("claim_id") or "").strip()
                attempt = int(args.get("attempt") or 0)
                usage = args.get("usage")
                if not job_id:
                    raise ValueError("missing_job_id")
                if not claim_id:
                    raise ValueError("missing_claim_id")
                if attempt < 1:
                    raise ValueError("invalid_attempt")
                if not isinstance(usage, dict):
                    raise ValueError("invalid_usage")

                paths = self._get_paths(job_id=job_id)
                state = self._ensure_claim(paths=paths, claim_id=claim_id)
                owner_user_id = str(state.get("owner_user_id") or "").strip()
                if not owner_user_id:
                    raise ValueError("invalid_state")

                attempt_dir = paths.output_dir / "artifacts" / f"attempt_{attempt}"
                attempt_dir.mkdir(parents=True, exist_ok=True)
                write_json(attempt_dir / "usage.json", usage)
                write_json(paths.output_dir / "usage.json", usage)
                ingest_usage_payload(job_id=job_id, owner_user_id=owner_user_id, attempt=attempt, payload=cast(dict[str, Any], usage))

                await self.send_result(
                    msg_id=msg_id,
                    result={"content": [{"type": "text", "text": "ok"}], "structuredContent": {"ok": True}},
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
