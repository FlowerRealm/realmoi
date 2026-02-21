from __future__ import annotations

# AUTO_COMMENT_HEADER_V1: _codex_appserver_transport.py
# 说明：Codex app-server 传输层（子进程 JSONL stdin/stdout 协议）。
# - 负责 send_request / read_json_line / 落盘 jsonl
# - 负责 thread/start 与 turn/start 的请求发送与同步等待
# - 该模块不处理事件语义（由 _codex_appserver_events.py 负责）

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def send_request(proc: subprocess.Popen[str], *, request_id: int, method: str, params: dict[str, Any]) -> None:
    assert proc.stdin is not None
    try:
        proc.stdin.write(json.dumps({"id": request_id, "method": method, "params": params}, ensure_ascii=False) + "\n")
        proc.stdin.flush()
    except OSError as exc:
        raise RuntimeError(f"appserver_write_failed:{exc}") from exc


def read_json_line(proc: subprocess.Popen[str]) -> tuple[str, dict[str, Any] | None]:
    # 读取一行 JSONL；obj=None 表示进程已退出。
    assert proc.stdout is not None
    try:
        line = proc.stdout.readline()
    except OSError as exc:
        raise RuntimeError(f"appserver_read_failed:{exc}") from exc
    if not line:
        if proc.poll() is not None:
            return "", None
        return "", {}

    if not line.endswith("\n"):
        line = line + "\n"

    s = line.strip()
    if not s:
        return line, {}

    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        # Best-effort：保留原始行，解析失败时只透传到 stdout 以便定位协议异常。
        print(s, flush=True)
        return line, {}
    return line, obj if isinstance(obj, dict) else {}


def write_jsonl(out, raw_line: str) -> None:
    # 落盘原始 JSONL：raw_line 必须带换行符。
    if not raw_line:
        return
    try:
        written = out.write(raw_line)
        if written <= 0:
            return
        out.flush()
    except OSError as exc:
        raise RuntimeError(f"jsonl_write_failed:{exc}") from exc


def await_request_result(proc: subprocess.Popen[str], out, request_id: int) -> dict[str, Any]:
    # 等待指定 request_id 的同步 result/error。
    while True:
        raw_line, obj = read_json_line(proc)
        if raw_line:
            write_jsonl(out, raw_line)
        if obj is None:
            raise RuntimeError("appserver_exited")
        if not obj:
            continue
        if obj.get("id") != request_id:
            continue
        if "error" in obj:
            error_payload = obj.get("error")
            raise RuntimeError(f"appserver_request_error:{error_payload}")
        result = obj.get("result")
        return result if isinstance(result, dict) else {}


def start_appserver_process() -> subprocess.Popen[str]:
    return subprocess.Popen(
        ["codex", "app-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def read_schema_json(schema_path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"schema_read_failed:{exc}") from exc
    return obj if isinstance(obj, dict) else {}


def start_thread(proc: subprocess.Popen[str], out, *, model: str, request_id: int) -> tuple[str, str, int]:
    request_id += 1
    thread_req_id = request_id
    send_request(proc, request_id=thread_req_id, method="thread/start", params={"model": model})
    result = await_request_result(proc, out, thread_req_id)

    thread = result.get("thread") if isinstance(result.get("thread"), dict) else {}
    thread_id = str(thread.get("id") or "")
    model_from_result = str(result.get("model") or model)
    out.write(json.dumps({"type": "thread.started", "thread_id": thread_id, "model": model_from_result}, ensure_ascii=False) + "\n")
    out.flush()

    if not thread_id:
        raise RuntimeError("appserver_thread_id_missing")
    return thread_id, model_from_result, request_id


@dataclass(frozen=True)
class TurnStartRequest:
    thread_id: str
    prompt: str
    reasoning_effort: str
    schema_obj: dict[str, Any]


def start_turn(
    proc: subprocess.Popen[str],
    *,
    req: TurnStartRequest,
    request_id: int,
) -> tuple[int, int]:
    request_id += 1
    turn_req_id = request_id
    send_request(
        proc,
        request_id=turn_req_id,
        method="turn/start",
        params={
            "threadId": req.thread_id,
            "input": [{"type": "text", "text": req.prompt, "text_elements": []}],
            "cwd": None,
            "approvalPolicy": None,
            "sandboxPolicy": None,
            "model": None,
            "effort": req.reasoning_effort,
            "summary": None,
            "personality": None,
            "outputSchema": req.schema_obj,
            "collaborationMode": None,
        },
    )
    return turn_req_id, request_id


def terminate_process(proc: subprocess.Popen[str]) -> None:
    # Best-effort teardown: terminate → wait → kill.
    try:
        proc.terminate()
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
    except OSError:
        return

