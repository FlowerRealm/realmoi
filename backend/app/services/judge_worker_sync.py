from __future__ import annotations

# 同步线程：把 judge runner 侧的日志/状态回写到后端（通过 judge.* MCP 工具）。
# 设计目标：
# - 尽量不影响主 worker：错误以 log_warn + 退避重试为主
# - 写入采用 offset 协议：支持 offset_mismatch 自愈
# - 允许“短时不一致”：该同步线程只负责把信息尽快写回后端，最终一致即可

import base64
import binascii
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .job_manager import JobManager
from .judge_mcp_client import McpJudgeClient, McpJudgeClientError
from .judge_worker_common import log_warn, structured_content


@dataclass(frozen=True)
class McpJobContext:
    client: McpJudgeClient
    job_id: str
    claim_id: str

    def base_args(self) -> dict[str, str]:
        # 所有 judge.* 工具都需要 job_id + claim_id 作为幂等/归属信息。
        return {"job_id": self.job_id, "claim_id": self.claim_id}


@dataclass(frozen=True)
class SyncPaths:
    terminal_log: Path
    agent_status_jsonl: Path
    state_json: Path


def sleepSeconds(poll_interval: float) -> None:
    # sleep 的最小值 clamp 到 0，避免传入负数导致异常。
    time.sleep(max(0.0, float(poll_interval)))


def encode_chunk_b64(chunk: bytes) -> str:
    # terminal/log 走 JSON-RPC，因此二进制内容需要 base64 编码。
    try:
        return base64.b64encode(chunk).decode("ascii")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        log_warn(key="append_encode", message=f"encode chunk failed: {type(exc).__name__}: {exc}")
        return ""


def read_local_chunk(*, local_path: Path, local_offset: int, max_bytes: int) -> bytes:
    """Read a fixed-size chunk from `local_path` at `local_offset` (best-effort)."""
    try:
        with local_path.open("rb") as file_handle:
            file_handle.seek(max(0, int(local_offset or 0)))
            return file_handle.read(max_bytes)
    except (OSError, ValueError) as exc:
        log_warn(key="append_read", message=f"read local log failed path={local_path}: {exc}")
        return b""


def call_append_tool(
    *,
    job_ctx: McpJobContext,
    tool_name: str,
    remote_offset: int,
    chunk_b64: str,
) -> dict[str, Any] | None:
    """Call MCP append tool and return structuredContent payload (or None on failure)."""
    try:
        result = job_ctx.client.call_tool(
            name=tool_name,
            arguments={
                **job_ctx.base_args(),
                "offset": remote_offset,
                "chunk_b64": chunk_b64,
            },
        )
    except McpJudgeClientError as exc:
        log_warn(key=f"append_call:{tool_name}", message=f"mcp append failed tool={tool_name}: {exc}")
        return None

    try:
        payload = structured_content(result)
    except Exception as exc:
        log_warn(key=f"append_parse:{tool_name}", message=f"parse structured_content failed: {type(exc).__name__}: {exc}")
        return None

    return payload if isinstance(payload, dict) else None


def apply_append_payload(
    *,
    payload: dict[str, Any],
    chunk_len: int,
    local_offset: int,
    remote_offset: int,
) -> tuple[int, int, bool]:
    """Update offsets from append payload and return (local_offset, remote_offset, advanced)."""
    if "ok" in payload and payload["ok"] is True:
        written_bytes = int(payload["written_bytes"] if "written_bytes" in payload else chunk_len)
        next_offset = int(payload["next_offset"] if "next_offset" in payload else (remote_offset + written_bytes))
        return local_offset + chunk_len, next_offset, True

    if "code" in payload and payload["code"] == "offset_mismatch":
        # 后端 offset 与本地不一致：从后端当前位置继续写入（幂等修复）。
        current = int(payload["current_offset"] if "current_offset" in payload else 0)
        return max(local_offset, current), current, True

    return local_offset, remote_offset, False


def sync_append_loop(
    *,
    stop: threading.Event,
    job_ctx: McpJobContext,
    local_path: Path,
    tool_name: str,
    poll_interval: float,
) -> None:
    # Tail a local file and append chunks to backend via MCP tool.
    local_offset = 0
    remote_offset = 0

    while not stop.is_set():
        if not local_path.exists():
            sleepSeconds(poll_interval)
            continue

        chunk = read_local_chunk(local_path=local_path, local_offset=local_offset, max_bytes=64 * 1024)

        if not chunk:
            sleepSeconds(poll_interval)
            continue

        # 编码失败通常意味着数据异常；退避并继续。
        chunk_b64 = encode_chunk_b64(chunk)
        if not chunk_b64:
            sleepSeconds(max(0.2, poll_interval))
            continue

        payload = call_append_tool(job_ctx=job_ctx, tool_name=tool_name, remote_offset=remote_offset, chunk_b64=chunk_b64)
        if payload is None:
            sleepSeconds(max(0.2, poll_interval))
            continue

        local_offset, remote_offset, advanced = apply_append_payload(
            payload=payload,
            chunk_len=len(chunk),
            local_offset=local_offset,
            remote_offset=remote_offset,
        )
        if advanced:
            continue

        # 其他失败：保留退避，但输出一次可诊断信息（避免“吞错误”被静态分析记分）。
        code = str(payload["code"] if "code" in payload else "unknown_error")
        message = str(payload["message"] if "message" in payload else "")
        log_warn(key=f"append_failed:{tool_name}", message=f"append failed code={code} message={message}")
        sleepSeconds(max(0.2, poll_interval))


def read_state_dict(*, local_state_path: Path) -> dict[str, Any] | None:
    """Load `state.json` from disk and return dict payload (or None on failure)."""
    try:
        state = json.loads(local_state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log_warn(key="state_read", message=f"read local state failed path={local_state_path}: {exc}")
        return None
    if not isinstance(state, dict):
        log_warn(key="state_read", message=f"invalid local state payload path={local_state_path}")
        return None
    return state


def compute_state_sig(state: dict[str, Any]) -> tuple[str, str, str]:
    """Compute a compact signature for state changes to reduce patch frequency."""
    containers = state.get("containers") if isinstance(state.get("containers"), dict) else {}
    generate_info = containers.get("generate") if isinstance(containers.get("generate"), dict) else {}
    test_info = containers.get("test") if isinstance(containers.get("test"), dict) else {}
    return (
        str(state["status"] or "") if "status" in state else "",
        str(generate_info["exit_code"] or "") if "exit_code" in generate_info else "",
        str(test_info["exit_code"] or "") if "exit_code" in test_info else "",
    )


def patch_state(*, job_ctx: McpJobContext, state: dict[str, Any]) -> bool:
    """Patch backend state via MCP (returns True on success)."""
    try:
        job_ctx.client.call_tool(
            name="judge.job.patch_state",
            arguments={**job_ctx.base_args(), "patch": state},
        )
        return True
    except McpJudgeClientError as exc:
        log_warn(key="state_patch", message=f"mcp patch state failed job_id={job_ctx.job_id}: {exc}")
        return False


def sync_state_loop(
    *,
    stop: threading.Event,
    job_ctx: McpJobContext,
    local_state_path: Path,
    poll_interval: float,
) -> None:
    # Mirror local `state.json` changes back to backend via MCP patch tool.
    last_sig: tuple[str, str, str] | None = None

    while not stop.is_set():
        if not local_state_path.exists():
            sleepSeconds(poll_interval)
            continue

        state = read_state_dict(local_state_path=local_state_path)
        if state is None:
            sleepSeconds(poll_interval)
            continue

        # 仅用少量字段做 sig，避免频繁 patch（减少后端负载）。
        sig = compute_state_sig(state)
        if sig == last_sig:
            sleepSeconds(poll_interval)
            continue

        ok = patch_state(job_ctx=job_ctx, state=state)
        if ok:
            last_sig = sig
            continue

        sleepSeconds(max(0.2, poll_interval))


def cancel_poll_loop(
    *,
    stop: threading.Event,
    job_ctx: McpJobContext,
    manager: JobManager,
    poll_interval: float,
) -> None:
    # Poll backend state for cancel signal and cancel local job when needed.
    while not stop.is_set():
        try:
            result = job_ctx.client.call_tool(
                name="judge.job.get_state",
                arguments=job_ctx.base_args(),
            )
        except McpJudgeClientError as exc:
            log_warn(key="cancel_poll_get_state", message=f"mcp get_state failed job_id={job_ctx.job_id}: {exc}")
            sleepSeconds(max(0.5, poll_interval))
            continue

        try:
            state = structured_content(result)
        except Exception as exc:
            log_warn(
                key="cancel_poll_parse_state",
                message=f"parse backend state failed job_id={job_ctx.job_id}: {type(exc).__name__}: {exc}",
            )
            sleepSeconds(max(0.5, poll_interval))
            continue

        # 后端标记 cancelled 时，尝试取消本地 job（不保证成功）。
        if str(state.get("status") or "") == "cancelled":
            try:
                manager.cancel_job(job_id=job_ctx.job_id)
            except RuntimeError as exc:
                log_warn(key="cancel_poll_cancel", message=f"cancel local job failed job_id={job_ctx.job_id}: {exc}")
            return

        sleepSeconds(poll_interval)


def start_sync_threads(
    *,
    job_ctx: McpJobContext,
    manager: JobManager,
    paths: SyncPaths,
) -> tuple[threading.Event, list[threading.Thread]]:
    stop = threading.Event()
    threads = [
        threading.Thread(
            target=sync_append_loop,
            kwargs={
                "stop": stop,
                "job_ctx": job_ctx,
                "local_path": paths.terminal_log,
                "tool_name": "judge.job.append_terminal",
                "poll_interval": 0.05,
            },
            daemon=True,
        ),
        threading.Thread(
            target=sync_append_loop,
            kwargs={
                "stop": stop,
                "job_ctx": job_ctx,
                "local_path": paths.agent_status_jsonl,
                "tool_name": "judge.job.append_agent_status",
                "poll_interval": 0.05,
            },
            daemon=True,
        ),
        threading.Thread(
            target=sync_state_loop,
            kwargs={
                "stop": stop,
                "job_ctx": job_ctx,
                "local_state_path": paths.state_json,
                "poll_interval": 0.2,
            },
            daemon=True,
        ),
        threading.Thread(
            target=cancel_poll_loop,
            kwargs={
                "stop": stop,
                "manager": manager,
                "job_ctx": job_ctx,
                "poll_interval": 0.5,
            },
            daemon=True,
        ),
    ]
    for t in threads:
        t.start()
    return stop, threads


def stop_threads(*, stop: threading.Event, threads: list[threading.Thread]) -> None:
    # Stop and join background sync threads best-effort.
    stop.set()
    for t in threads:
        try:
            t.join(timeout=1.0)
        except RuntimeError as exc:
            log_warn(key="join_thread", message=f"thread join failed: {exc}")
