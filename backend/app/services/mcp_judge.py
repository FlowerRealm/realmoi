from __future__ import annotations

# 独立测评机（judge worker）通过统一 MCP WS（/api/mcp/ws）调用这些 tools。
# 本模块是 judge 侧 tools 的服务端实现，给 `backend/app/judge_daemon.py` 使用。
# AUTO_COMMENT_HEADER_V1: mcp_judge.py
# 说明：
# - 该模块实现 judge.* tools（服务端侧），用于 runner/judge 与后端之间的最小协议面。
# - 所有 tool 都以 job_id 定位 job 目录，并要求 claim_id 匹配以避免并发写冲突。
# - 返回统一用 JSON-RPC result/error；不把 Python 异常透传为协议崩溃。

import asyncio
import base64
import binascii
import json
import os
from pathlib import Path
from typing import Any, cast

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
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

from ..services.mcp_judge_tools import JUDGE_TOOLS


def try_rel_posix(*, path: Path, base: Path) -> str | None:
    try:
        return path.relative_to(base).as_posix()
    except Exception:
        return None


def stat_size_or_zero(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0


def walk_files(base: Path) -> list[Path]:
    # NOTE: os.walk 在这里足够；不需要处理 symlink 等复杂情况（输入目录由后端/runner 控制）。
    out: list[Path] = []
    for root, _dirs, files in os.walk(base):
        root_path = Path(root)
        for name in files:
            out.append(root_path / name)
    return out


def ws_error(*, code: int, message: str) -> dict[str, Any]:
    # JSON-RPC error payload（嵌入到 {"error": ...} 中）
    return {"code": code, "message": message}


class ToolCallError(Exception):
    # 业务层 tool 错误：会被映射成 JSON-RPC error 返回给 judge。
    def __init__(self, *, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class McpJudgeWebSocketSession:
    # 说明：每个 WS 连接对应一个 session；send_json 通过锁保证不会帧交错。
    def __init__(self, *, ws: WebSocket):
        self._ws = ws
        # 避免多个并发 task 同时写 ws 导致帧交错。
        self._send_lock = asyncio.Lock()

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

    async def tool_list(self, *, msg_id: Any) -> None:
        await self.send_result(msg_id=msg_id, result={"tools": JUDGE_TOOLS})

    def get_paths(self, *, job_id: str) -> JobPaths:
        # judge.* tools 都以 job_id 定位 job 目录；不存在时统一按 not_found 处理。
        paths = get_job_paths(jobs_root=Path(SETTINGS.jobs_root), job_id=job_id)
        if not paths.state_json.exists():
            raise FileNotFoundError(job_id)
        return paths

    def load_state(self, *, paths: JobPaths) -> dict[str, Any]:
        # state.json 是后端与 runner/judge 的共享 SSOT；这里做最小类型校验。
        obj = read_json(paths.state_json)
        if not isinstance(obj, dict):
            raise ValueError("invalid_state")
        return cast(dict[str, Any], obj)

    def ensure_claim(self, *, paths: JobPaths, claim_id: str) -> dict[str, Any]:
        # claim_id 用于保证独立 judge 只操作自己认领的 job（避免并发写冲突）。
        state = self.load_state(paths=paths)
        expected = str(((state.get("judge") or {}).get("claim_id")) or "")
        if not expected or expected != claim_id:
            raise ValueError("claim_mismatch")
        return state

    def require_job_and_claim(self, *, args: dict[str, Any]) -> tuple[str, str]:
        # tool args 的基础校验：缺失字段直接返回 422/invalid_params。
        job_id = str(args.get("job_id") or "").strip()
        claim_id = str(args.get("claim_id") or "").strip()
        if not job_id:
            raise ValueError("missing_job_id")
        if not claim_id:
            raise ValueError("missing_claim_id")
        return job_id, claim_id

    def require_job_claim_paths_state(
        self, *, args: dict[str, Any]
    ) -> tuple[str, str, JobPaths, dict[str, Any]]:
        # 常见工具的入口：拿到 (job_id, claim_id, paths, state) 这四件套。
        job_id, claim_id = self.require_job_and_claim(args=args)
        paths, state = self.get_paths_and_state(job_id=job_id, claim_id=claim_id)
        return job_id, claim_id, paths, state

    def get_paths_and_state(self, *, job_id: str, claim_id: str) -> tuple[JobPaths, dict[str, Any]]:
        paths = self.get_paths(job_id=job_id)
        state = self.ensure_claim(paths=paths, claim_id=claim_id)
        return paths, state

    def deep_merge(self, dst: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        # 递归 merge：用于 patch_state（尽量保留未覆盖字段）。
        for key, value in patch.items():
            dst_value = dst.get(key)
            if isinstance(value, dict) and isinstance(dst_value, dict):
                dst[key] = self.deep_merge(cast(dict[str, Any], dst_value or {}), cast(dict[str, Any], value))
            else:
                dst[key] = value
        return dst

    def normalize_rel_path(self, rel_path: str) -> str:
        # 统一成 POSIX 样式，避免 Windows runner 写入反斜杠导致后端路径判断出错。
        return str(rel_path or "").strip().replace("\\", "/")

    def split_rel_parts(self, rel_path: str) -> list[str]:
        # 防止绝对路径 / .. 穿越：所有操作都限制在 job 工作目录内。
        if not rel_path:
            raise ValueError("missing_path")
        if rel_path.startswith("/"):
            raise ValueError("invalid_path")
        parts = [p for p in rel_path.split("/") if p]
        if any(p in {".", ".."} for p in parts):
            raise ValueError("invalid_path")
        return parts

    def resolve_safe_child(self, *, base: Path, parts: list[str]) -> Path:
        candidate = base.joinpath(*parts)
        try:
            candidate.resolve().relative_to(base.resolve())
        except (RuntimeError, ValueError):
            raise ValueError("invalid_path") from None
        return candidate

    def resolve_input_file(self, *, paths: JobPaths, rel_path: str) -> Path:
        rel_path = self.normalize_rel_path(rel_path)
        parts = self.split_rel_parts(rel_path)
        candidate = self.resolve_safe_child(base=paths.input_dir, parts=parts)
        if not candidate.exists() or not candidate.is_file():
            raise FileNotFoundError(rel_path)
        return candidate

    def append_with_offset_check(
        self,
        *,
        path: Path,
        offset: int,
        chunk: bytes,
        max_bytes: int,
    ) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)

        file_handle = path.open("ab")
        with file_handle as file_obj:
            if fcntl is not None:
                fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX)
            current_offset = int(file_obj.tell())
            if current_offset != int(offset or 0):
                return {"ok": False, "code": "offset_mismatch", "current_offset": current_offset}
            if current_offset >= max_bytes:
                return {"ok": True, "next_offset": current_offset, "written_bytes": 0}
            remaining = max_bytes - current_offset
            out = chunk[:remaining]
            written_bytes = file_obj.write(out)
            file_obj.flush()
            return {"ok": True, "next_offset": current_offset + len(out), "written_bytes": int(written_bytes)}

    def max_terminal_log_bytes(self, *, state: dict[str, Any]) -> int:
        limits = state.get("resource_limits") or {}
        return int(limits.get("max_terminal_log_bytes") or SETTINGS.default_max_terminal_log_bytes)

    async def tool_claim_next(self, *, msg_id: Any, args: dict[str, Any], job_manager: Any) -> None:
        machine_id = str(args.get("machine_id") or "").strip()
        if not machine_id:
            raise ValueError("missing_machine_id")
        claimed = job_manager.claim_next_queued_job(machine_id=machine_id)
        if claimed is None:
            payload: dict[str, Any] = {"claimed": False}
        else:
            claimed_job_id = claimed.get("job_id")
            claimed_owner_user_id = claimed.get("owner_user_id")
            claimed_claim_id = claimed.get("claim_id")
            payload = {
                "claimed": True,
                "job_id": claimed_job_id,
                "owner_user_id": claimed_owner_user_id,
                "claim_id": claimed_claim_id,
            }
        await self.send_ok(msg_id=msg_id, structured=payload)

    async def tool_release_claim(self, *, msg_id: Any, args: dict[str, Any], job_manager: Any) -> None:
        job_id, claim_id = self.require_job_and_claim(args=args)
        released = job_manager.release_judge_claim(job_id=job_id, claim_id=claim_id)
        if not released:
            raise ToolCallError(code=409, message="claim_mismatch")
        await self.send_ok(msg_id=msg_id, structured={"released": True})

    async def tool_job_get_state(self, *, msg_id: Any, args: dict[str, Any], job_manager: Any) -> None:  # noqa: ARG002
        job_id, claim_id = self.require_job_and_claim(args=args)
        _paths, state = self.get_paths_and_state(job_id=job_id, claim_id=claim_id)
        await self.send_ok(msg_id=msg_id, structured=state)

    async def tool_input_list(self, *, msg_id: Any, args: dict[str, Any], job_manager: Any) -> None:  # noqa: ARG002
        _job_id, _claim_id, paths, _state = self.require_job_claim_paths_state(args=args)
        base = paths.input_dir
        items: list[dict[str, Any]] = []
        for file_path in walk_files(base):
            rel = try_rel_posix(path=file_path, base=base)
            if rel is None:
                continue
            items.append({"path": rel, "size": stat_size_or_zero(file_path)})
        items.sort(key=lambda x: str(x.get("path") or ""))
        await self.send_ok(msg_id=msg_id, structured={"items": items})

    async def tool_input_read_chunk(self, *, msg_id: Any, args: dict[str, Any], job_manager: Any) -> None:  # noqa: ARG002
        job_id, claim_id = self.require_job_and_claim(args=args)
        rel_path = str(args.get("path") or "")
        offset = int(args.get("offset") or 0)
        max_bytes = int(args.get("max_bytes") or 0)
        max_bytes = max(1, min(max_bytes, 1024 * 1024))

        paths, _state = self.get_paths_and_state(job_id=job_id, claim_id=claim_id)
        file_path = self.resolve_input_file(paths=paths, rel_path=rel_path)

        file_handle = file_path.open("rb")
        with file_handle as file_obj:
            file_obj.seek(max(0, offset))
            chunk = file_obj.read(max_bytes)
            next_offset = int(file_obj.tell())
        eof = next_offset >= int(file_path.stat().st_size)
        chunk_b64 = base64.b64encode(chunk).decode("ascii")
        payload = {
            "path": rel_path.replace("\\", "/"),
            "chunk_b64": chunk_b64,
            "next_offset": next_offset,
            "eof": eof,
        }
        await self.send_ok(msg_id=msg_id, structured=payload)

    async def tool_job_patch_state(self, *, msg_id: Any, args: dict[str, Any], job_manager: Any) -> None:  # noqa: ARG002
        _job_id, _claim_id, paths, state = self.require_job_claim_paths_state(args=args)
        patch = args.get("patch")
        if not isinstance(patch, dict):
            raise ValueError("invalid_patch")

        current_status = str(state.get("status") or "")
        merged = self.deep_merge(state, cast(dict[str, Any], patch))
        if current_status == "cancelled":
            merged["status"] = "cancelled"
        write_json(paths.state_json, merged)
        await self.send_ok(msg_id=msg_id, structured={"ok": True})

    async def tool_job_append_log(
        self,
        *,
        msg_id: Any,
        args: dict[str, Any],
        log_path: Path,
        max_bytes: int,
    ) -> None:
        offset = int(args.get("offset") or 0)
        chunk_b64 = str(args.get("chunk_b64") or "").strip()
        if not chunk_b64:
            raise ValueError("missing_chunk_b64")
        try:
            chunk = base64.b64decode(chunk_b64.encode("ascii"), validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("invalid_base64") from None

        payload = self.append_with_offset_check(
            path=log_path,
            offset=offset,
            chunk=chunk,
            max_bytes=max_bytes,
        )
        await self.send_ok(msg_id=msg_id, structured=payload)

    async def tool_job_append_terminal(self, *, msg_id: Any, args: dict[str, Any], job_manager: Any) -> None:  # noqa: ARG002
        _job_id, _claim_id, paths, state = self.require_job_claim_paths_state(args=args)
        max_bytes = self.max_terminal_log_bytes(state=state)
        await self.tool_job_append_log(msg_id=msg_id, args=args, log_path=paths.terminal_log, max_bytes=max_bytes)

    async def tool_job_append_agent_status(self, *, msg_id: Any, args: dict[str, Any], job_manager: Any) -> None:  # noqa: ARG002
        _job_id, _claim_id, paths, state = self.require_job_claim_paths_state(args=args)
        max_bytes = self.max_terminal_log_bytes(state=state)
        await self.tool_job_append_log(
            msg_id=msg_id,
            args=args,
            log_path=paths.agent_status_jsonl,
            max_bytes=max_bytes,
        )

    async def tool_job_put_artifacts(self, *, msg_id: Any, args: dict[str, Any], job_manager: Any) -> None:  # noqa: ARG002
        _job_id, _claim_id, paths, state = self.require_job_claim_paths_state(args=args)
        main_cpp = str(args.get("main_cpp") or "")
        solution_json = args.get("solution_json")
        report_json = args.get("report_json")

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

        await self.send_ok(msg_id=msg_id, structured={"ok": True})

    def require_owner_user_id(self, *, state: dict[str, Any]) -> str:
        owner_user_id = str(state.get("owner_user_id") or "").strip()
        if not owner_user_id:
            raise ValueError("invalid_state")
        return owner_user_id

    def read_model_and_channel(self, *, state: dict[str, Any]) -> tuple[str, str]:
        upstream_channel = str(state.get("upstream_channel") or "").strip()
        model = str(state.get("model") or "").strip()
        return upstream_channel, model

    def load_overrides_and_target(
        self,
        *,
        owner_user_id: str,
        upstream_channel: str,
        model: str,
    ) -> tuple[str, str, Any]:
        # 返回：用户 overrides、最终 upstream_channel、以及解析后的 upstream target（mock_mode 下为 None）。
        resolved_channel = str(upstream_channel or "").strip()
        with SessionLocal() as db:
            row = db.get(UserCodexSettings, owner_user_id)
            overrides = row.overrides_toml if row else ""

            model_pricing = db.get(ModelPricing, model) if model else None
            if not resolved_channel:
                resolved_channel = str((model_pricing.upstream_channel if model_pricing else "") or "").strip()

            if SETTINGS.mock_mode:
                return overrides, resolved_channel, None

            return overrides, resolved_channel, self.resolve_upstream_target_or_error(upstream_channel=resolved_channel, db=db)

    def resolve_upstream_target_or_error(self, *, upstream_channel: str, db: Any) -> Any:
        # NOTE: resolve_upstream_target 可能抛 ValueError；统一映射成 upstream_config_error 前缀。
        try:
            return resolve_upstream_target(upstream_channel, db=db)
        except ValueError as exc:
            raise ValueError(f"upstream_config_error:{exc}") from None

    def build_openai_auth(self, *, target: Any) -> tuple[str, bytes]:
        if SETTINGS.mock_mode:
            openai_base_url = str(SETTINGS.openai_base_url or "")
            auth_bytes = b"{}\n"
            return openai_base_url, auth_bytes

        if target is None:
            raise ValueError("upstream_config_error:missing_target")
        openai_base_url = str(target.base_url or "")
        auth_bytes = (json.dumps({"OPENAI_API_KEY": target.api_key}, ensure_ascii=False) + "\n").encode("utf-8")
        return openai_base_url, auth_bytes

    def load_prepare_generate_payload(self, *, state: dict[str, Any]) -> dict[str, Any]:
        """Build generate bundle payload for judge worker.

        返回：
        - effective_config_toml: 合并后的配置
        - auth_json_b64: OpenAI SDK 可用的环境变量 JSON（base64）
        - openai_base_url: 上游 Base URL
        """

        owner_user_id = self.require_owner_user_id(state=state)
        upstream_channel, model = self.read_model_and_channel(state=state)
        overrides, _resolved_channel, target = self.load_overrides_and_target(
            owner_user_id=owner_user_id,
            upstream_channel=upstream_channel,
            model=model,
        )

        cfg = build_effective_config(user_overrides_toml=overrides)
        openai_base_url, auth_bytes = self.build_openai_auth(target=target)
        if not openai_base_url:
            raise ValueError("upstream_config_error:missing_base_url")

        auth_json_b64 = base64.b64encode(auth_bytes).decode("ascii")
        return {
            "effective_config_toml": cfg.effective_config_toml,
            "auth_json_b64": auth_json_b64,
            "openai_base_url": openai_base_url,
            "mock_mode": bool(SETTINGS.mock_mode),
        }

    async def tool_prepare_generate(self, *, msg_id: Any, args: dict[str, Any], job_manager: Any) -> None:  # noqa: ARG002
        _job_id, _claim_id, _paths, state = self.require_job_claim_paths_state(args=args)
        payload = self.load_prepare_generate_payload(state=state)
        await self.send_ok(msg_id=msg_id, structured=payload)

    async def tool_usage_ingest(self, *, msg_id: Any, args: dict[str, Any], job_manager: Any) -> None:  # noqa: ARG002
        job_id, claim_id = self.require_job_and_claim(args=args)
        attempt = int(args.get("attempt") or 0)
        usage = args.get("usage")
        if attempt < 1:
            raise ValueError("invalid_attempt")
        if not isinstance(usage, dict):
            raise ValueError("invalid_usage")

        paths, state = self.get_paths_and_state(job_id=job_id, claim_id=claim_id)
        owner_user_id = str(state.get("owner_user_id") or "").strip()
        if not owner_user_id:
            raise ValueError("invalid_state")

        attempt_dir = paths.output_dir / "artifacts" / f"attempt_{attempt}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        write_json(attempt_dir / "usage.json", usage)
        write_json(paths.output_dir / "usage.json", usage)
        ingest_usage_payload(
            job_id=job_id,
            owner_user_id=owner_user_id,
            attempt=attempt,
            payload=cast(dict[str, Any], usage),
        )
        await self.send_ok(msg_id=msg_id, structured={"ok": True})

    async def tool_call(self, *, msg_id: Any, name: str, arguments: dict[str, Any]) -> None:
        tool = str(name or "")
        args = arguments if isinstance(arguments, dict) else {}

        job_manager = singletons.JOB_MANAGER
        if job_manager is None:
            await self.send_error(msg_id=msg_id, code=500, message="job_manager_not_ready")
            return

        handlers = {
            "judge.claim_next": self.tool_claim_next,
            "judge.release_claim": self.tool_release_claim,
            "judge.job.get_state": self.tool_job_get_state,
            "judge.input.list": self.tool_input_list,
            "judge.input.read_chunk": self.tool_input_read_chunk,
            "judge.job.patch_state": self.tool_job_patch_state,
            "judge.job.append_terminal": self.tool_job_append_terminal,
            "judge.job.append_agent_status": self.tool_job_append_agent_status,
            "judge.job.put_artifacts": self.tool_job_put_artifacts,
            "judge.prepare_generate": self.tool_prepare_generate,
            "judge.usage.ingest": self.tool_usage_ingest,
        }

        handler = handlers.get(tool)
        if handler is None:
            await self.send_error(msg_id=msg_id, code=-32601, message="Tool not found")
            return

        try:
            await handler(msg_id=msg_id, args=args, job_manager=job_manager)
        except ToolCallError as e:
            await self.send_error(msg_id=msg_id, code=e.code, message=e.message)
            return
        except FileNotFoundError:
            await self.send_error(msg_id=msg_id, code=404, message="not_found")
            return
        except ValueError as e:
            await self.send_error(msg_id=msg_id, code=422, message=str(e))
            return
        except (OSError, RuntimeError, TypeError) as e:
            await self.send_error(msg_id=msg_id, code=500, message=f"{type(e).__name__}: {e}")
            return
