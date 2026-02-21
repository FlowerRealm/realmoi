from __future__ import annotations

"""
realmoi MCP status sidecar.

This module implements a minimal JSON-RPC server over stdin/stdout using MCP's
Content-Length framing (LSP-style). It exposes a few tools used by the RealmOI
runner/UI to stream status updates and to run a local self-test.
"""

import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _fd_io import close_fd_best_effort, write_fd_best_effort

try:
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

# 约定：
# - stdout 只用于协议输出（Content-Length + JSON）
# - stderr 只用于日志（避免破坏 JSON-RPC framing）
# - 文件写入尽量 best-effort：写得进去就写，写不进去也不阻塞主流程
# - 对外返回一律 JSON-RPC result/error，避免把异常泄漏到协议层


STAGES = {"analysis", "plan", "search", "coding", "test", "repair", "done", "error"}
LEVELS = {"info", "warn", "error"}
JOB_DIR = Path(os.environ.get("REALMOI_JOB_DIR") or "/job")
SERVER_INFO = {"name": "realmoi-status", "version": "0.1.0"}

# ----------------------------
# Common helpers
# ----------------------------


def format_exc(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def utc_iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def load_json_object(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("json_not_object")
    return obj


# ----------------------------
# Job directory helpers
# ----------------------------

def job_path(*parts: str) -> Path:
    """Join `parts` under the RealmOI job directory."""
    return JOB_DIR.joinpath(*parts)


def read_job_id_fallback() -> str:
    """Best-effort read of job_id from `{JOB_DIR}/input/job.json`."""
    # The status sidecar can be launched before job.json exists; treat that as "unknown job".
    try:
        job = load_json_object(job_path("input", "job.json"))
        return str(job.get("job_id") or "")
    except (FileNotFoundError, IsADirectoryError):
        return ""
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        log_warn(f"job_id_read_failed: {format_exc(exc)}")
        return ""

# ----------------------------
# MCP protocol framing
# ----------------------------

# MCP framing 与 LSP 相同：
# - 读 headers 直到空行
# - 按 Content-Length 读取 JSON body
# - 所有输出必须走 stdout（stderr 会破坏 framing）

def recv_headers() -> dict[str, str] | None:
    # 读取 LSP 风格的 headers；直到空行结束。
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        line_s = line.decode("utf-8", errors="replace").strip()
        if not line_s:
            break
        if ":" not in line_s:
            continue
        key, value = line_s.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


def parse_content_length(headers: dict[str, str]) -> int | None:
    # 约束：Content-Length 必须是可解析的整数，否则丢弃该消息继续读下一条。
    length_s = headers.get("content-length")
    if not length_s:
        log_warn("protocol_error: missing Content-Length")
        return None
    try:
        return int(length_s)
    except ValueError as exc:
        log_warn(f"protocol_error: invalid Content-Length: {length_s} ({format_exc(exc)})")
        return None


def recv_json_body(length: int) -> dict[str, Any] | None:
    # 注意：这里必须按 Content-Length 精确读取；不能 readline()，否则会破坏 framing。
    body = sys.stdin.buffer.read(length)
    try:
        decoded = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        log_warn(f"protocol_error: invalid utf-8 body ({format_exc(exc)})")
        return None
    try:
        msg = json.loads(decoded)
    except json.JSONDecodeError as exc:
        log_warn(f"protocol_error: invalid json body ({format_exc(exc)})")
        return None
    if not isinstance(msg, dict):
        log_warn("protocol_error: json body is not an object")
        return None
    return msg


def recv_message() -> dict[str, Any] | None:
    """Receive a single MCP JSON-RPC message from stdin."""
    # MCP uses Content-Length framing (LSP-style): headers until an empty line, then raw JSON bytes.
    while True:
        headers = recv_headers()
        if headers is None:
            return None
        length = parse_content_length(headers)
        if length is None:
            continue
        msg = recv_json_body(length)
        if msg is None:
            continue
        return msg


def send_message(obj: dict[str, Any]) -> None:
    """Send a single MCP JSON-RPC message to stdout."""
    # Protocol output must only go to stdout; any logging must go to stderr.
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    payload = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8") + body
    written = write_fd_best_effort(fd=1, payload=payload, label="stdout", log_warn=log_warn)
    if written < 0:
        raise SystemExit(0)


def log_warn(message: str) -> None:
    """Best-effort stderr logging without affecting protocol output."""
    try:
        print(f"[realmoi-status] {message}", file=sys.stderr, flush=True)
    except Exception:
        return

# ----------------------------
# Status log writer
# ----------------------------

# agent_status.jsonl 是 UI 的流式来源之一：
# - 每行一个 JSON 对象（尽量小）
# - 允许多进程并发 append（Linux 下用 flock）

def serialize_jsonl_line(line: dict[str, Any]) -> bytes:
    # JSONL：每行一个 JSON object，末尾必须带换行符。
    return (json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8")


@contextmanager
def open_append_fd(path: Path):
    # 打开并返回可 append 的 fd；关闭由 close_fd_best_effort 兜底处理。
    file_descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        yield file_descriptor
    finally:
        close_fd_best_effort(fd=file_descriptor, label="append", log_warn=log_warn)


def lock_fd(file_descriptor: int) -> None:
    # Linux 下用 flock 避免并发写交错；非 Linux 下直接跳过（best-effort）。
    if fcntl is None:
        return
    fcntl.flock(file_descriptor, fcntl.LOCK_EX)


def unlock_fd(file_descriptor: int) -> None:
    # unlock 失败不影响主流程（只记录告警）。
    if fcntl is None:
        return
    try:
        fcntl.flock(file_descriptor, fcntl.LOCK_UN)
    except OSError as exc:
        log_warn(f"unlock_failed: {format_exc(exc)}")


@contextmanager
def open_locked_append_fd(path: Path):
    # 合并 open + lock + unlock，降低 append_status_line 的嵌套深度。
    with open_append_fd(path) as file_descriptor:
        lock_fd(file_descriptor)
        try:
            yield file_descriptor
        finally:
            unlock_fd(file_descriptor)


def append_status_line(line: dict[str, Any]) -> int:
    """Append one status line into `logs/agent_status.jsonl` (best-effort locked)."""
    log_path = job_path("logs", "agent_status.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = serialize_jsonl_line(line)
        with open_locked_append_fd(log_path) as file_descriptor:
            if write_fd_best_effort(fd=file_descriptor, payload=payload, label="append", log_warn=log_warn) < 0:
                raise RuntimeError("append_write_failed")
    except Exception as exc:
        log_warn(f"append_status_failed: {format_exc(exc)}")
        return -1
    return 0


def resolve_runner_test_script() -> Path:
    # realmoi_status_mcp.py lives next to runner_test.py both locally and in runner image (/app).
    return Path(__file__).resolve().parent / "runner_test.py"

# ----------------------------
# Local self-test runner
# ----------------------------

# 自测目标：
# - 在 runner 容器内复用 runner_test.py 做一次编译+执行
# - 只返回“对 UI 有用”的摘要字段（stdout/stderr 仅截断尾部）
# - workspace 固定在 job 目录下，避免权限问题

def tail_text(text: str, max_chars: int) -> str:
    """Tail `text` to at most `max_chars` characters."""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def prepare_self_test_workspace(*, temp_root: Path, main_cpp: str) -> tuple[Path, Path, Path]:
    # 目录布局：
    # - input: 指向 job/input（符号链接优先，否则 copytree）
    # - output: runner_test.py 的输出目录（main.cpp 写在这里）
    # - .tmp_work: runner_test.py 的临时工作区（编译产物等）
    input_link = temp_root / "input"
    output_dir = temp_root / "output"
    work_dir = temp_root / ".tmp_work"

    temp_root.mkdir(parents=True, exist_ok=True)
    try:
        # Symlink is faster; fallback to copy on filesystems without symlink support.
        input_link.symlink_to(job_path("input").resolve(), target_is_directory=True)
    except OSError as exc:
        log_warn(f"self_test_symlink_failed: {format_exc(exc)}")
        shutil.copytree(job_path("input"), input_link, dirs_exist_ok=True)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "main.cpp").write_text(main_cpp.rstrip() + "\n", encoding="utf-8")
    return input_link, output_dir, work_dir


def run_self_test_process(*, temp_root: Path, work_dir: Path, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-X", "utf8", str(resolve_runner_test_script())]
    environment = os.environ.copy()
    environment.update(
        {
            "ATTEMPT": "1",
            "REALMOI_JOB_DIR": str(temp_root.resolve()),
            "REALMOI_WORK_DIR": str(work_dir.resolve()),
        }
    )
    return subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        timeout=max(1, int(timeout_seconds)),
    )


def load_self_test_report(temp_root: Path) -> dict[str, Any]:
    report_path = temp_root / "output" / "artifacts" / "attempt_1" / "test_output" / "report.json"
    if not report_path.exists():
        raise RuntimeError("self_test_report_missing")
    return load_json_object(report_path)


def load_self_test_report_safe(temp_root: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return load_self_test_report(temp_root), None
    except OSError as exc:
        return None, f"report_read_failed:{format_exc(exc)}"
    except json.JSONDecodeError as exc:
        return None, f"report_json_invalid:{format_exc(exc)}"
    except Exception as exc:
        return None, f"report_load_failed:{format_exc(exc)}"


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_self_test_summary(*, completed: subprocess.CompletedProcess[str], report: dict[str, Any]) -> dict[str, Any]:
    # report.json 是 runner_test.py 的输出；这里只提取 UI 需要的字段，避免回传过大 payload。
    summary = dict_or_empty(report.get("summary"))
    compile_info = dict_or_empty(report.get("compile"))

    status = str(report.get("status") or "failed")
    compile_ok = bool(compile_info.get("ok") is True)

    first_failure = summary["first_failure"] if "first_failure" in summary else None
    first_failure_verdict = summary["first_failure_verdict"] if "first_failure_verdict" in summary else None
    first_failure_message = summary["first_failure_message"] if "first_failure_message" in summary else None

    return {
        "ok": status == "succeeded",
        "status": status,
        "runner_exit_code": int(completed.returncode),
        "compile_ok": compile_ok,
        "first_failure": first_failure,
        "first_failure_verdict": first_failure_verdict,
        "first_failure_message": first_failure_message,
        "stdout_tail": tail_text(str(completed.stdout or ""), 4000),
        "stderr_tail": tail_text(str(completed.stderr or ""), 4000),
    }


def run_local_self_test(*, main_cpp: str, timeout_seconds: int) -> dict[str, Any]:
    """Run a local RealmOI self-test using `runner_test.py` in an isolated temp workspace."""
    if not main_cpp.strip():
        raise ValueError("empty_main_cpp")

    # Keep the self-test workspace under the job dir so the runner image has write permissions.
    temp_root = job_path(".self_test_tmp", secrets.token_hex(8))

    try:
        _, _, work_dir = prepare_self_test_workspace(temp_root=temp_root, main_cpp=main_cpp)
        completed = run_self_test_process(temp_root=temp_root, work_dir=work_dir, timeout_seconds=timeout_seconds)

        report, error = load_self_test_report_safe(temp_root)
        if error is not None or report is None:
            return {"ok": False, "status": "error", "error": error or "report_load_failed"}

        return build_self_test_summary(completed=completed, report=report)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

# ----------------------------
# JSON-RPC helpers and tool handlers
# ----------------------------

@dataclass
class StatusContext:
    """Mutable server context for sequencing and status de-dupe."""

    seq: int = 0
    last_sig: tuple[str, str] | None = None
    last_sig_ts: float = 0.0


def send_error(*, request_id: Any, code: int, message: str) -> None:
    send_message({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def send_ok(*, request_id: Any, structured: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"content": [{"type": "text", "text": "ok"}]}
    if structured is not None:
        payload["structuredContent"] = structured
    send_message({"jsonrpc": "2.0", "id": request_id, "result": payload})


def safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def clamp_timeout_seconds(timeout_seconds: Any) -> int:
    return max(10, min(safe_int(timeout_seconds, default=90), 600))


def normalize_stage(stage: Any) -> str:
    stage_s = str(stage or "")
    return stage_s if stage_s in STAGES else "analysis"


def normalize_level(level: Any) -> str:
    level_s = str(level or "info")
    return level_s if level_s in LEVELS else "info"


def normalize_attempt(attempt: Any) -> int:
    return max(1, safe_int(attempt, default=1))


def normalize_progress(progress: Any) -> int | None:
    if progress is None:
        return None
    try:
        return int(progress)
    except (TypeError, ValueError):
        return None


# MCP tools schema（静态）：避免每次请求都构造 dict，且降低单函数长度扣分。
TOOLS_LIST_RESULT: dict[str, Any] = {
    "tools": [
        {
            "name": "status.update",
            "description": "Write a short status update for realmoi UI (<=200 chars).",
            "inputSchema": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "job_id": {"type": "string"},
                    "attempt": {"type": "integer"},
                    "stage": {"type": "string"},
                    "level": {"type": "string"},
                    "progress": {"type": "integer"},
                    "summary": {"type": "string"},
                    "meta": {"type": "object"},
                },
                "required": ["stage", "summary"],
            },
        },
        {
            "name": "agent.delta",
            "description": "Append a structured agent delta line for realmoi UI streaming.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "job_id": {"type": "string"},
                    "attempt": {"type": "integer"},
                    "stage": {"type": "string"},
                    "level": {"type": "string"},
                    "kind": {"type": "string"},
                    "delta": {"type": "string"},
                    "meta": {"type": "object"},
                },
                "required": ["stage", "kind"],
            },
        },
        {
            "name": "judge.self_test",
            "description": (
                "Run a local self-test (compile + run provided tests) in an isolated temp workspace, "
                "and return a compact summary."
            ),
            "inputSchema": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "main_cpp": {"type": "string"},
                    "timeout_seconds": {"type": "integer"},
                },
                "required": ["main_cpp"],
            },
        },
    ]
}


def send_structured_result(*, request_id: Any, structured: dict[str, Any]) -> None:
    # MCP result: 同时包含 text content 与 structuredContent（便于兼容仅展示文本的 client）。
    send_message(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False)}],
                "structuredContent": structured,
            },
        }
    )


def next_seq(context: StatusContext) -> str:
    context.seq += 1
    return f"mcp-{context.seq}"


def append_status(context: StatusContext, line: dict[str, Any]) -> str:
    seq = next_seq(context)
    line_with_seq = dict(line)
    line_with_seq["seq"] = seq
    append_status_line(line_with_seq)
    return seq


def append_status_and_ack(*, context: StatusContext, request_id: Any, line: dict[str, Any]) -> None:
    seq = append_status(context, line)
    send_ok(request_id=request_id, structured={"seq": seq})


def should_dedupe(*, context: StatusContext, stage: str, summary: str, now: float) -> bool:
    # Avoid flooding the UI: if the same (stage, summary) repeats within 1s, drop it.
    sig = (stage, summary)
    if context.last_sig != sig:
        context.last_sig = sig
        context.last_sig_ts = now
        return False
    if now - context.last_sig_ts >= 1.0:
        context.last_sig_ts = now
        return False
    return True


def handle_tool_agent_delta(*, context: StatusContext, request_id: Any, tool_args: dict[str, Any]) -> None:
    stage = normalize_stage(tool_args.get("stage"))
    level = normalize_level(tool_args.get("level"))
    kind = str(tool_args.get("kind") or "").strip() or "other"
    delta = str(tool_args.get("delta") or "")
    attempt = normalize_attempt(tool_args.get("attempt"))
    metadata = tool_args.get("meta") if isinstance(tool_args.get("meta"), dict) else {}

    if len(delta) > 20000:
        delta = delta[:20000]

    now = time.time()
    job_id = str(tool_args.get("job_id") or read_job_id_fallback() or "")
    summary = (delta.strip() or kind)[:200]

    append_status_and_ack(
        context=context,
        request_id=request_id,
        line={
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "job_id": job_id,
            "attempt": attempt,
            "stage": stage,
            "level": level,
            "progress": None,
            "summary": summary,
            "kind": kind,
            "delta": delta,
            "meta": metadata,
        },
    )


def handle_tool_status_update(*, context: StatusContext, request_id: Any, tool_args: dict[str, Any]) -> None:
    stage = normalize_stage(tool_args.get("stage"))
    level = normalize_level(tool_args.get("level"))
    summary = str(tool_args.get("summary") or "").strip()
    attempt = normalize_attempt(tool_args.get("attempt"))
    progress_int = normalize_progress(tool_args.get("progress"))

    if len(summary) > 200:
        summary = summary[:200]

    now = time.time()
    if should_dedupe(context=context, stage=stage, summary=summary, now=now):
        send_ok(request_id=request_id, structured={"deduped": True})
        return

    job_id = str(tool_args.get("job_id") or read_job_id_fallback() or "")
    metadata = tool_args.get("meta") if isinstance(tool_args.get("meta"), dict) else {}

    append_status_and_ack(
        context=context,
        request_id=request_id,
        line={
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "job_id": job_id,
            "attempt": attempt,
            "stage": stage,
            "level": level,
            "progress": progress_int,
            "summary": summary,
            "meta": metadata,
        },
    )


def emit_self_test_hint(*, context: StatusContext, result: dict[str, Any], attempt: int) -> None:
    ok, summary = build_self_test_hint(result)

    append_status(
        context,
        {
            "ts": utc_iso(time.time()),
            "job_id": read_job_id_fallback(),
            "attempt": attempt,
            "stage": "done" if ok else "repair",
            "level": "info" if ok else "warn",
            "progress": None,
            "summary": summary[:200],
            "meta": {},
        },
    )


def build_self_test_hint(result: dict[str, Any]) -> tuple[bool, str]:
    if bool(result.get("ok")):
        return True, "自测通过"

    bits = [str(result.get(k) or "").strip() for k in ("first_failure_verdict", "first_failure", "first_failure_message")]
    bits = [b for b in bits if b]
    detail = ("：" + " ".join(bits)) if bits else ""
    return False, "自测未通过" + detail


def append_self_test_failure_status_best_effort(
    *,
    context: StatusContext,
    attempt: int,
    error_message: str,
) -> None:
    # 自测异常时，也尽量写一条状态行，帮助 UI 展示“失败原因”。
    try:
        append_status(
            context,
            {
                "ts": utc_iso(time.time()),
                "job_id": read_job_id_fallback(),
                "attempt": attempt,
                "stage": "error",
                "level": "error",
                "progress": None,
                "summary": f"自测失败：{error_message}"[:200],
                "meta": {},
            },
        )
    except Exception as exc:
        log_warn(f"self_test_append_failed: {format_exc(exc)}")


def handle_tool_judge_self_test(*, context: StatusContext, request_id: Any, tool_args: dict[str, Any]) -> None:
    main_cpp = str(tool_args.get("main_cpp") or "")
    timeout_seconds = clamp_timeout_seconds(tool_args.get("timeout_seconds"))
    attempt = normalize_attempt(tool_args.get("attempt"))

    try:
        result = run_local_self_test(main_cpp=main_cpp, timeout_seconds=timeout_seconds)
    except ValueError as exc:
        send_error(request_id=request_id, code=-32602, message=f"Invalid params: {exc}")
        return
    except Exception as exc:
        error_message = format_exc(exc)
        payload = {"ok": False, "status": "error", "error": error_message}
        append_self_test_failure_status_best_effort(context=context, attempt=attempt, error_message=error_message)
        send_structured_result(request_id=request_id, structured=payload)
        return

    try:
        emit_self_test_hint(context=context, result=result, attempt=attempt)
    except Exception as exc:
        log_warn(f"self_test_hint_failed: {format_exc(exc)}")

    send_structured_result(request_id=request_id, structured=result)


def handle_tools_call(*, context: StatusContext, request_id: Any, params: dict[str, Any]) -> None:
    tool_name = params.get("name")
    args = params.get("arguments") or {}
    if not isinstance(args, dict):
        send_error(request_id=request_id, code=-32602, message="Invalid params")
        return

    handlers = {
        "agent.delta": handle_tool_agent_delta,
        "judge.self_test": handle_tool_judge_self_test,
        "status.update": handle_tool_status_update,
    }
    handler = handlers.get(str(tool_name or ""))
    if handler is not None:
        handler(context=context, request_id=request_id, tool_args=args)
        return

    send_error(request_id=request_id, code=-32601, message="Tool not found")


def handle_initialize(*, request_id: Any) -> None:
    send_message(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"capabilities": {"tools": {}}, "serverInfo": SERVER_INFO},
        }
    )


def handle_ping(*, request_id: Any) -> None:
    send_message({"jsonrpc": "2.0", "id": request_id, "result": {}})


def handle_tools_list(*, request_id: Any) -> None:
    send_message({"jsonrpc": "2.0", "id": request_id, "result": TOOLS_LIST_RESULT})


def dispatch_request(*, context: StatusContext, msg: dict[str, Any]) -> None:
    request_id = msg.get("id")
    method = msg.get("method")

    handlers = {
        "initialize": handle_initialize,
        "ping": handle_ping,
        "tools/list": handle_tools_list,
    }
    handler = handlers.get(str(method or ""))
    if handler is not None:
        handler(request_id=request_id)
        return

    if method == "tools/call":
        params = msg.get("params") or {}
        if not isinstance(params, dict):
            send_error(request_id=request_id, code=-32602, message="Invalid params")
            return
        handle_tools_call(context=context, request_id=request_id, params=params)
        return

    # Ignore notifications
    if request_id is None:
        return

    send_error(request_id=request_id, code=-32601, message="Method not found")


def main() -> int:
    """Run the MCP JSON-RPC loop until stdin closes."""
    context = StatusContext()

    while True:
        msg = recv_message()
        if msg is None:
            return 0
        dispatch_request(context=context, msg=msg)


if __name__ == "__main__":
    raise SystemExit(main())
