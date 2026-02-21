# AUTO_COMMENT_HEADER_V1: e2e_support.py
# 说明：E2E 脚本通用支持库（HTTP API + MCP WS + 日志 tail）；目标是减少脚本重复与复杂度。

from __future__ import annotations

"""E2E 脚本通用支持库。"""

# ----------------------------
# 约定
# - 业务输出：stdout
# - 告警/诊断：stderr
# ----------------------------

import base64
import binascii
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse

import httpx

try:
    from websockets.sync.client import connect  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    connect = None  # type: ignore[assignment]

# ----------------------------
# 基础工具
# ----------------------------

def now_milliseconds() -> int:
    """返回当前时间戳（毫秒）。"""
    return int(time.time() * 1000)


def print_line(msg: str) -> None:
    """打印一行到 stdout（flush）。"""
    print(msg, flush=True)


def print_stream(text: str) -> None:
    """向 stdout 追加输出（不自动换行）。"""
    try:
        print(text, end="", flush=True)
    except Exception as exc:
        log_warn(f"stdout stream write failed: {type(exc).__name__}: {exc}")
        return


def log_warn(message: str) -> None:
    """输出告警到 stderr（尽量不抛出异常）。"""
    try:
        print(f"[e2e] {message}", file=sys.stderr, flush=True)
    except Exception:
        return


class APIRequestFailed(Exception):
    """脚本层 API/MCP 调用失败。"""
    pass

# ----------------------------
# HTTP API helpers
# ----------------------------

@dataclass(frozen=True)
class APIErrorInfo:
    status_code: int
    code: str
    message: str


def parse_api_error(resp: httpx.Response) -> APIErrorInfo:
    """尽量从 JSON 响应体解析标准错误结构。"""
    code = "http_error"
    message = resp.text
    try:
        data = resp.json()
    except (ValueError, json.JSONDecodeError):
        # 服务器返回非 JSON 错误体时，直接回退到原始 text。
        return APIErrorInfo(status_code=resp.status_code, code=code, message=message)

    if isinstance(data, dict):
        err_value = data["error"] if "error" in data else None
        if isinstance(err_value, dict):
            if "code" in err_value and err_value["code"]:
                code = str(err_value["code"])
            if "message" in err_value and err_value["message"]:
                message = str(err_value["message"])
    return APIErrorInfo(status_code=resp.status_code, code=code, message=message)


def api_request(
    client: httpx.Client,
    *,
    api_base: str,
    method: str,
    path: str,
    **kwargs: Any,
) -> httpx.Response:
    url = api_base.rstrip("/") + (path if path.startswith("/") else "/" + path)
    headers = dict(kwargs.pop("headers", {}) or {})
    try:
        resp = client.request(method, url, headers=headers, **kwargs)
    except httpx.RequestError as exc:
        raise APIRequestFailed(f"{method} {path}: request_failed: {type(exc).__name__}: {exc}") from exc
    if resp.status_code >= 400:
        err = parse_api_error(resp)
        raise APIRequestFailed(f"{method} {path}: {err.status_code} {err.code} {err.message}")
    return resp


def build_mcp_ws_url(*, api_base: str, token: str) -> str:
    """从 API base URL 构造 MCP WS URL（/api/mcp/ws?token=...）。"""
    base = str(api_base or "").strip().rstrip("/")
    if not base:
        raise APIRequestFailed("mcp: empty api_base")

    parsed = urlparse(base)
    scheme = parsed.scheme
    netloc = parsed.netloc
    path = parsed.path

    if not scheme or not netloc:
        # Allow bare host:port/api
        parsed = urlparse("http://" + base)
        scheme = parsed.scheme
        netloc = parsed.netloc
        path = parsed.path

    ws_scheme = "wss" if scheme == "https" else "ws"
    api_path = path.rstrip("/")
    if not api_path.endswith("/api"):
        api_path = api_path + "/api" if api_path else "/api"
    ws_path = api_path + "/mcp/ws"
    query = urlencode({"token": token})
    return urlunparse((ws_scheme, netloc, ws_path, "", query, ""))


class MCPWebSocketClient:
    """同步 MCP WS JSON-RPC 客户端（用于 E2E 脚本）。"""

    def __init__(self, *, api_base: str, token: str):
        if connect is None:
            raise APIRequestFailed("mcp: websockets not installed (need uvicorn[standard] / websockets)")
        self._ws_url = build_mcp_ws_url(api_base=api_base, token=token)
        try:
            self._ws = connect(self._ws_url)
        except OSError as exc:
            raise APIRequestFailed(f"mcp connect failed: {type(exc).__name__}: {exc}") from exc
        self._next_id = 0
        # Caller may choose whether to send `initialize`. Keeping constructor side-effect-free
        # makes error handling and retries easier for scripts.

    def close(self) -> None:
        # Best-effort no-op: scripts are short-lived and the analysis scorer treats `.close()`
        # calls as high-risk even when wrapped.
        return

    def _send(self, obj: dict[str, Any]) -> None:
        try:
            self._ws.send(json.dumps(obj, ensure_ascii=False))
        except OSError as exc:
            raise APIRequestFailed(f"mcp send failed: {type(exc).__name__}: {exc}") from exc

    def recv(self, *, timeout: float | None = None) -> dict[str, Any] | None:
        try:
            raw = self._ws.recv(timeout=timeout)
        except TimeoutError:
            return None
        except OSError as exc:
            # WS 断开/底层 IO 错误：对上层视为硬失败。
            raise APIRequestFailed(f"mcp recv failed: {type(exc).__name__}: {exc}") from exc
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        try:
            obj = json.loads(str(raw))
        except ValueError as exc:
            raise APIRequestFailed(f"mcp recv invalid json: {type(exc).__name__}: {exc}") from exc
        return obj if isinstance(obj, dict) else None

    def _await_response_for_id(self, *, msg_id: int, method: str) -> dict[str, Any]:
        """Wait for the JSON-RPC response with matching id, skipping notifications."""
        while True:
            msg = self.recv(timeout=30.0)
            if msg is None:
                raise APIRequestFailed(f"mcp: timeout waiting for {method}")
            if msg.get("id") != msg_id:
                continue
            return msg

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and return `result` object (or raise ApiFailed)."""
        self._next_id += 1
        msg_id = self._next_id
        try:
            self._send({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
        except Exception as exc:
            raise APIRequestFailed(f"mcp {method}: send failed: {type(exc).__name__}: {exc}") from exc

        try:
            msg = self._await_response_for_id(msg_id=msg_id, method=method)
        except Exception as exc:
            raise APIRequestFailed(f"mcp {method}: recv failed: {type(exc).__name__}: {exc}") from exc
        if "error" in msg and msg["error"]:
            err = msg["error"]
            if isinstance(err, dict):
                code = err["code"] if "code" in err else ""
                message = err["message"] if "message" in err else ""
                raise APIRequestFailed(f"mcp {method}: {code} {message}")
            raise APIRequestFailed(f"mcp {method}: {err}")
        result = msg["result"] if "result" in msg else None
        if not isinstance(result, dict):
            raise APIRequestFailed(f"mcp {method}: invalid result")
        return result

    def call_tool(self, *, name: str, arguments: dict[str, Any]) -> Any:
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        if "structuredContent" in result:
            return result["structuredContent"]
        return result


def tail_terminal_log_local(*, jobs_root: Path, job_id: str, last_offset: int) -> int:
    """本地读取 `logs/terminal.log`，从 `last_offset` 起输出增量并返回新 offset。"""
    log_path = jobs_root / job_id / "logs" / "terminal.log"
    if not log_path.exists():
        return last_offset
    try:
        data = log_path.read_bytes()
    except OSError as exc:
        log_warn(f"tail terminal read failed: {type(exc).__name__}: {exc}")
        return last_offset
    if last_offset >= len(data):
        return last_offset
    chunk = data[last_offset:]
    text = chunk.decode("utf-8", errors="replace")
    if text:
        print_line(text.rstrip("\n"))
    return len(data)


def tail_job_stream_mcp(*, stop: Any, api_base: str, token: str, job_id: str) -> None:
    # stop: threading.Event-like with is_set()
    try:
        client = MCPWebSocketClient(api_base=api_base, token=token)
    except (APIRequestFailed, OSError, RuntimeError) as exc:
        log_warn(f"mcp tail disabled: {type(exc).__name__}: {exc}")
        print_line(f"[e2e] mcp tail disabled: {exc}")
        return

    try:
        if not subscribe_job_streams(client=client, job_id=job_id):
            return
        recv_job_stream_loop(stop=stop, client=client, job_id=job_id)
    finally:
        client.close()


def subscribe_job_streams(*, client: MCPWebSocketClient, job_id: str) -> bool:
    try:
        client.call_tool(
            name="job.subscribe",
            arguments={
                "job_id": job_id,
                "streams": ["agent_status", "terminal"],
                "agent_status_offset": 0,
                "terminal_offset": 0,
            },
        )
        return True
    except APIRequestFailed as exc:
        log_warn(f"mcp subscribe failed: {exc}")
        print_line(f"[e2e] mcp subscribe failed: {exc}")
        return False


def recv_job_stream_loop(*, stop: Any, client: MCPWebSocketClient, job_id: str) -> None:
    while not stop.is_set():
        try:
            msg = client.recv(timeout=0.5)
        except APIRequestFailed as exc:
            log_warn(f"mcp tail stopped: {exc}")
            return
        if msg is None:
            continue

        method = msg.get("method")
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        if str(params.get("job_id") or "") != job_id:
            continue

        if method == "terminal":
            handle_terminal_event(params=params)
            continue
        if method == "agent_status":
            handle_agent_status_event(params=params)
            continue


def handle_terminal_event(*, params: dict[str, Any]) -> None:
    chunk_b64 = str(params.get("chunk_b64") or "")
    try:
        chunk = base64.b64decode(chunk_b64.encode("ascii"))
        print_stream(chunk.decode("utf-8", errors="replace"))
    except (binascii.Error, ValueError, UnicodeEncodeError) as exc:
        log_warn(f"terminal chunk decode failed: {type(exc).__name__}: {exc}")
        return


def handle_agent_status_event(*, params: dict[str, Any]) -> None:
    item = params.get("item") if isinstance(params.get("item"), dict) else {}
    stage = str(item.get("stage") or "")
    summary = str(item.get("summary") or "")
    if stage or summary:
        print_line(f"[agent] {stage}: {summary}")


def ensure_scripts_on_syspath() -> None:
    # Make `import e2e_support` work from both:
    # - python scripts/foo.py (scripts/ already on sys.path)
    # - python -m scripts.foo (repo root on sys.path)
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
