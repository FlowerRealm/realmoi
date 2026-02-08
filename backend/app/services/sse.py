from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator


@dataclass(frozen=True)
class TailChunk:
    offset: int
    next_offset: int
    chunk: bytes


def _read_from_offset(path: Path, offset: int, max_bytes: int = 64 * 1024) -> TailChunk:
    if not path.exists():
        return TailChunk(offset=offset, next_offset=offset, chunk=b"")
    with path.open("rb") as f:
        f.seek(offset)
        data = f.read(max_bytes)
        next_offset = f.tell()
        return TailChunk(offset=offset, next_offset=next_offset, chunk=data)


async def tail_file_sse(
    *,
    path: Path,
    offset: int,
    event: str,
    heartbeat_seconds: int = 15,
) -> AsyncIterator[str]:
    """
    Async generator that yields SSE lines.
    """

    last_heartbeat = asyncio.get_event_loop().time()
    current_offset = offset
    while True:
        chunk = _read_from_offset(path, current_offset)
        if chunk.chunk:
            current_offset = chunk.next_offset
            payload = {
                "offset": current_offset,
                "chunk_b64": base64.b64encode(chunk.chunk).decode("ascii"),
            }
            yield f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            continue

        now = asyncio.get_event_loop().time()
        if now - last_heartbeat >= heartbeat_seconds:
            last_heartbeat = now
            yield f"event: heartbeat\ndata: {json.dumps({'ts': now}, ensure_ascii=False)}\n\n"

        await asyncio.sleep(0.25)


async def tail_jsonl_sse(
    *,
    path: Path,
    offset: int,
    event: str,
    heartbeat_seconds: int = 15,
) -> AsyncIterator[str]:
    last_heartbeat = asyncio.get_event_loop().time()
    current_offset = offset
    buf = b""

    while True:
        if path.exists():
            with path.open("rb") as f:
                f.seek(current_offset)
                chunk = f.read(64 * 1024)
                if chunk:
                    current_offset = f.tell()
                    buf += chunk

                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            item = json.loads(line.decode("utf-8"))
                        except Exception:
                            continue
                        payload = {"offset": current_offset - len(buf), "item": item}
                        yield f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    continue

        now = asyncio.get_event_loop().time()
        if now - last_heartbeat >= heartbeat_seconds:
            last_heartbeat = now
            yield f"event: heartbeat\ndata: {json.dumps({'ts': now}, ensure_ascii=False)}\n\n"

        await asyncio.sleep(0.25)
