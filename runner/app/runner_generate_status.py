from __future__ import annotations

import atexit
import os
import time
from typing import Any

try:
    from realmoi_mcp_client import McpClientError, McpStdioClient
except ModuleNotFoundError:  # pragma: no cover
    from runner.app.realmoi_mcp_client import McpClientError, McpStdioClient  # type: ignore

_STATUS_LAST_SIG: tuple[str, str] | None = None
_STATUS_LAST_TS: float = 0.0

_MCP_CLIENT: McpStdioClient | None = None
_MCP_DISABLED: bool = False


def close_mcp_client() -> None:
    global _MCP_CLIENT
    if _MCP_CLIENT is None:
        return
    try:
        close_result = _MCP_CLIENT.close()
        if close_result is not None:
            _ = close_result
    except Exception:
        pass
    _MCP_CLIENT = None


_ATEXIT_CLOSE = atexit.register(close_mcp_client)


def get_mcp_client() -> McpStdioClient | None:
    global _MCP_CLIENT, _MCP_DISABLED
    if _MCP_DISABLED:
        return None
    if _MCP_CLIENT is not None:
        return _MCP_CLIENT
    try:
        _MCP_CLIENT = McpStdioClient(module_name="realmoi_status_mcp", env=os.environ.copy())
        return _MCP_CLIENT
    except (McpClientError, OSError, ValueError):
        _MCP_DISABLED = True
        return None


def status_update(*, stage: str, summary: str, level: str = "info", progress: int | None = None) -> None:
    """
    Append a status line for UI consumption (via MCP job.subscribe).

    Args:
        stage: One of analysis/plan/search/coding/repair/done/error.
        summary: Short message (<=200 chars).
        level: info/warn/error.
        progress: Optional 0-100 progress.
    """

    global _STATUS_LAST_SIG, _STATUS_LAST_TS

    stage = str(stage or "").strip() or "analysis"
    summary = str(summary or "").strip()
    if len(summary) > 200:
        summary = summary[:200]

    sig = (stage, summary)
    now = time.time()
    if _STATUS_LAST_SIG == sig and now - _STATUS_LAST_TS < 1.0:
        return
    _STATUS_LAST_SIG = sig
    _STATUS_LAST_TS = now

    client = get_mcp_client()
    if client is None:
        return

    args: dict[str, Any] = {
        "stage": stage,
        "summary": summary,
        "level": level,
        "attempt": int(os.getenv("ATTEMPT") or "1"),
    }
    if progress is not None:
        args["progress"] = progress
    try:
        _ = client.call_tool(name="status.update", arguments=args)
    except Exception:
        return


def agent_delta_update(
    *,
    kind: str,
    delta: str,
    stage: str,
    level: str = "info",
    meta: dict[str, Any] | None = None,
) -> None:
    if not delta and kind != "reasoning_summary_boundary":
        return
    client = get_mcp_client()
    if client is None:
        return
    args: dict[str, Any] = {
        "stage": stage,
        "level": level,
        "kind": str(kind or "").strip() or "other",
        "delta": str(delta or ""),
        "attempt": int(os.getenv("ATTEMPT") or "1"),
        "meta": meta or {},
    }
    try:
        _ = client.call_tool(name="agent.delta", arguments=args)
    except Exception:
        return
