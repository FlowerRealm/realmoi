from __future__ import annotations

# MCP 状态上报（尽力而为）。
#
# runner_test 在编译/测试过程中会把进度写回后端 UI。该能力不应影响实际测试结果：
# - 失败时禁用 MCP，避免反复抛错/阻塞
# - 相同摘要在短时间内去抖，减少噪声

import atexit
import os
import time
from typing import Any

try:
    from realmoi_mcp_client import McpClientError, McpStdioClient
except ModuleNotFoundError:  # pragma: no cover
    from runner.app.realmoi_mcp_client import McpClientError, McpStdioClient


MCP_CLIENT: McpStdioClient | None = None
MCP_DISABLED: bool = False
STATUS_LAST_SIG: tuple[str, str] | None = None
STATUS_LAST_TS: float = 0.0


def close_mcp_client() -> None:
    global MCP_CLIENT, MCP_DISABLED
    if MCP_CLIENT is None:
        return
    try:
        close_result = MCP_CLIENT.close()
        if close_result is not None:
            _ = close_result
    except (McpClientError, OSError, RuntimeError, ValueError) as exc:
        # MCP 只用于“尽力而为”的状态上报；关闭失败时直接禁用，避免反复报错。
        if not MCP_DISABLED:
            print(f"[test] warn: close MCP client failed ({exc}); disabling MCP", flush=True)
        MCP_DISABLED = True
    MCP_CLIENT = None


ATEXIT_CLOSE = atexit.register(close_mcp_client)


def get_mcp_client() -> McpStdioClient | None:
    global MCP_CLIENT, MCP_DISABLED
    if MCP_DISABLED:
        return None
    if MCP_CLIENT is not None:
        return MCP_CLIENT
    try:
        MCP_CLIENT = McpStdioClient(module_name="realmoi_status_mcp", env=os.environ.copy())
        return MCP_CLIENT
    except (McpClientError, OSError, ValueError) as exc:
        if not MCP_DISABLED:
            print(f"[test] warn: init MCP client failed ({exc}); disabling MCP", flush=True)
        MCP_DISABLED = True
        return None


def status_update(*, stage: str, summary: str, level: str = "info", progress: int | None = None) -> None:
    global STATUS_LAST_SIG, STATUS_LAST_TS, MCP_DISABLED

    stage = str(stage or "").strip() or "test"
    summary = str(summary or "").strip()
    if len(summary) > 200:
        summary = summary[:200]

    sig = (stage, summary)
    now = time.time()
    if STATUS_LAST_SIG == sig and now - STATUS_LAST_TS < 1.0:
        return
    STATUS_LAST_SIG = sig
    STATUS_LAST_TS = now

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
    except (McpClientError, OSError, RuntimeError, ValueError) as exc:
        # 状态上报失败不影响测试执行；为避免后续每次都触发异常，这里直接禁用 MCP。
        if not MCP_DISABLED:
            print(f"[test] warn: MCP status.update failed ({exc}); disabling MCP", flush=True)
        MCP_DISABLED = True
        close_mcp_client()
