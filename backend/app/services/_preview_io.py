from __future__ import annotations

"""Small IO helpers for test preview reads."""

from pathlib import Path
from typing import Any


def safe_read_preview_text(path: Path, *, max_bytes: int) -> dict[str, Any]:
    """Best-effort preview read; IO errors should not crash the caller."""
    try:
        size_bytes = int(path.stat().st_size)
    except Exception:
        size_bytes = 0
    try:
        with path.open("rb") as fp:
            raw = fp.read(max_bytes)
    except Exception:
        raw = b""
    return {
        "text": raw.decode("utf-8", errors="replace"),
        "truncated": size_bytes > max_bytes,
        "bytes": size_bytes,
    }

