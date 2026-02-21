from __future__ import annotations

# MCP WebSocket client used by the independent judge daemon.
#
# Design goals:
# - Best-effort connectivity: the judge runs in a long-lived background loop.
# - Minimal dependencies: only `websockets` if available.
# - No business logic: job execution remains in judge_daemon.py.

import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote, urlencode, urlparse, urlunparse

try:
    from websockets.sync.client import connect  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    connect = None  # type: ignore[assignment]


WarnFn = Callable[..., None]


class McpJudgeClientError(RuntimeError):
    pass


def _normalize_api_base(value: str) -> str:
    # Normalize a configured API base URL to the `/api` root.
    base = str(value or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith("/api"):
        return base
    return f"{base}/api"


def _to_ws_base(api_base_url: str) -> str:
    # Convert API base url to WS base (http->ws, https->wss).
    if api_base_url.startswith("https://"):
        return "wss://" + api_base_url.removeprefix("https://")
    if api_base_url.startswith("http://"):
        return "ws://" + api_base_url.removeprefix("http://")
    if api_base_url.startswith("ws://") or api_base_url.startswith("wss://"):
        return api_base_url
    return "ws://" + api_base_url


def resolve_mcp_ws_urls(*, token: str, api_base_url: str, fallback_bases: list[str] | None = None) -> list[str]:
    # Resolve candidate MCP WebSocket URLs based on configured token and base.
    tok = str(token or "").strip()
    if not tok:
        return []

    bases: list[str] = []
    configured = _normalize_api_base(str(api_base_url or ""))
    if configured:
        bases.append(configured)
    if fallback_bases:
        bases.extend(fallback_bases)

    seen: set[str] = set()
    urls: list[str] = []
    for base in bases:
        base = _normalize_api_base(base)
        if not base or base in seen:
            continue
        seen.add(base)
        ws_base = _to_ws_base(base).rstrip("/")
        # Use `quote` because token may contain '+' or '/'.
        urls.append(f"{ws_base}/mcp/ws?token={quote(tok)}")
    return urls


def build_mcp_ws_url(*, api_base: str, token: str) -> str:
    # Build one MCP WS URL from an api_base that may be a bare host or include /api.
    base = str(api_base or "").strip().rstrip("/")
    if not base:
        raise McpJudgeClientError("mcp: empty api_base")

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


def _try_parse_json_dict(raw: str) -> dict[str, Any] | None:
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


@dataclass
class _ConnState:
    ws: Any | None = None
    connected_url: str = ""
    next_id: int = 0


class McpJudgeClient:
    def __init__(self, *, ws_urls: list[str], warn: WarnFn | None = None):
        self._ws_urls = ws_urls
        self._warn = warn
        self._state = _ConnState()
        # websockets sync client is thread-safe for a single consumer; we still
        # serialize access because the judge uses background threads.
        import threading

        self._lock = threading.RLock()

    def _log_warn(self, *, key: str, message: str, interval_s: float = 2.0) -> None:
        if self._warn is None:
            return
        try:
            self._warn(key=key, message=message, interval_s=interval_s)
        except TypeError:
            # If a different callable is provided, fall back to positional usage.
            self._warn(message)  # type: ignore[misc]

    def ensure_connected(self) -> None:
        if self._state.ws is not None:
            return
        if connect is None:
            raise McpJudgeClientError("websockets_not_installed")

        last_exc: Exception | None = None
        for url in self._ws_urls:
            try:
                self._state.ws = connect(url, open_timeout=2)  # type: ignore[misc]
                self._state.connected_url = url
                self._state.next_id = 0
                self._request("initialize", {})
                print(f"[judge] mcp connected url={url}", flush=True)
                return
            except (OSError, TimeoutError, RuntimeError, ValueError) as e:
                last_exc = e
                self._state.ws = None
                self._state.connected_url = ""
                self._log_warn(key="mcp_connect", message=f"mcp connect failed url={url}: {e}", interval_s=1.0)
                continue

        raise McpJudgeClientError(f"mcp_connect_failed:{last_exc}")

    def close(self) -> None:
        if self._state.ws is None:
            return
        try:
            self._state.ws.close()
        except OSError as e:
            self._log_warn(key="mcp_close", message=f"mcp close failed: {e}")
        self._state.ws = None
        self._state.connected_url = ""

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self.ensure_connected()
            ws = self._state.ws
            if ws is None:
                raise McpJudgeClientError("mcp_disconnected")

            self._state.next_id += 1
            msg_id = self._state.next_id
            payload = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}
            try:
                ws.send(json.dumps(payload, ensure_ascii=False))
            except (OSError, RuntimeError, ValueError) as e:
                self.close()
                raise McpJudgeClientError(f"mcp_send_failed:{e}") from e

            while True:
                try:
                    raw = ws.recv()
                except (OSError, TimeoutError, RuntimeError) as e:
                    self.close()
                    raise McpJudgeClientError(f"mcp_recv_failed:{e}") from e

                if isinstance(raw, bytes):
                    raw_text = raw.decode("utf-8", errors="replace")
                else:
                    raw_text = str(raw)

                msg = _try_parse_json_dict(raw_text)
                if msg is None:
                    # Ignore junk/partial frames but keep a breadcrumb for diagnosis.
                    self._log_warn(key="mcp_decode", message="mcp recv: invalid json frame")
                    continue
                if msg.get("id") != msg_id:
                    continue
                if "error" in msg:
                    raise McpJudgeClientError(f"mcp_error:{msg.get('error')}")
                result = msg.get("result")
                return result if isinstance(result, dict) else {}

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        return self.request(method, params)

    def call_tool(self, *, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})

