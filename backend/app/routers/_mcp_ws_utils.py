from __future__ import annotations

"""Small utilities for the MCP WebSocket router.

This module exists mainly to:
- keep `mcp.py` focused on routing logic
- encapsulate a few IO primitives (`Path.open`, `WebSocket.accept`, `session.close`)
  that are intentionally best-effort
"""

import base64
import binascii
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import WebSocket


def read_file_chunk(*, path: Path, offset: int, max_bytes: int, logger: logging.Logger) -> tuple[int, bytes]:
    """Read a chunk from `path` starting at `offset` (best-effort)."""
    try:
        with path.open("rb") as file_handle:
            file_handle.seek(max(0, int(offset or 0)))
            chunk = file_handle.read(max_bytes)
            return file_handle.tell(), chunk
    except (OSError, ValueError) as exc:
        # FS race/permission issues: treat as empty chunk and keep tailing.
        logger.debug("read_file_chunk failed: %s", exc)
        return offset, b""


def parse_jsonl_buffer(*, buffer: bytes, end_offset: int, logger: logging.Logger) -> tuple[list[tuple[int, dict[str, Any]]], bytes]:
    """Parse newline-delimited JSON objects from `buffer`, tracking stream offsets."""
    results: list[tuple[int, dict[str, Any]]] = []
    buf = buffer
    while b"\n" in buf:
        raw_line, buf = buf.split(b"\n", 1)
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            item = json.loads(raw_line.decode("utf-8"))
        except json.JSONDecodeError as exc:
            # Allow partial lines / non-JSON lines in stream.
            logger.debug("parse_jsonl_buffer skip invalid jsonl line: %s", exc)
            continue
        if not isinstance(item, dict):
            continue
        results.append((end_offset - len(buf), item))
    return results, buf


def encode_chunk_b64(chunk: bytes, *, logger: logging.Logger) -> str:
    """Base64-encode chunk for JSON-RPC transport (returns empty string on failure)."""
    try:
        return base64.b64encode(chunk).decode("ascii")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        logger.debug("terminal chunk b64 encode failed: %s", exc)
        return ""


async def try_ws_accept(*, ws: WebSocket, logger: logging.Logger, label: str) -> bool:
    """Best-effort `ws.accept()` with logging (returns True when accepted)."""
    try:
        await ws.accept()
        return True
    except Exception as exc:
        logger.debug("%s ws.accept failed: %s", label, exc)
        return False


async def try_session_close(*, session: Any, logger: logging.Logger, label: str) -> None:
    """Best-effort `session.close()` with logging."""
    try:
        await session.close()
    except Exception as exc:
        logger.debug("%s session.close failed: %s", label, exc)

