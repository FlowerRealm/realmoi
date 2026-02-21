from __future__ import annotations

import os
import socket
import time
from pathlib import Path
from typing import Any

from ..settings import SETTINGS


_log_last_ts: dict[str, float] = {}


def log_warn(*, key: str, message: str, interval_s: float = 2.0) -> None:
    # Rate-limited warnings for background loops.
    now = time.time()
    last = _log_last_ts.get(key, 0.0)
    if now - last < interval_s:
        return
    _log_last_ts[key] = now
    msg = str(message or "").strip()
    if len(msg) > 300:
        msg = msg[:300] + "..."
    print(f"[judge] warn: {msg}", flush=True)


def resolve_machine_id() -> str:
    # Resolve stable id for the current judge worker.
    value = str(SETTINGS.judge_machine_id or "").strip()
    if value:
        return value
    return f"{socket.gethostname()}-{os.getpid()}"


def resolve_work_root() -> Path:
    # Resolve local job workspace root for judge worker.
    raw = str(SETTINGS.judge_work_root or "").strip()
    if raw:
        return Path(raw)
    if SETTINGS.runner_executor == "docker":
        return Path(SETTINGS.jobs_root) / ".judge-work"
    return Path("/tmp/realmoi-judge-work")


def structured_content(result: dict[str, Any]) -> dict[str, Any]:
    # Extract MCP `structuredContent` payload as dict.
    payload = result.get("structuredContent") or {}
    return payload if isinstance(payload, dict) else {}

