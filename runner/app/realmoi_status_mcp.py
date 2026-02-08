from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


STAGES = {"analysis", "plan", "search", "coding", "repair", "done", "error"}
LEVELS = {"info", "warn", "error"}


def _read_job_id_fallback() -> str:
    try:
        job = json.loads(Path("/job/input/job.json").read_text(encoding="utf-8"))
        return str(job.get("job_id") or "")
    except Exception:
        return ""


def _recv_message() -> dict[str, Any] | None:
    # MCP uses Content-Length framing (LSP-style).
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        line = line.decode("utf-8", errors="replace").strip()
        if not line:
            break
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()

    length_s = headers.get("content-length")
    if not length_s:
        return None
    length = int(length_s)
    body = sys.stdin.buffer.read(length)
    return json.loads(body.decode("utf-8"))


def _send_message(obj: dict[str, Any]) -> None:
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def _append_status_line(line: dict[str, Any]) -> int:
    log_path = Path("/job/logs/agent_status.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # best-effort: read last seq
    seq = int(line.get("seq") or 0)
    with log_path.open("ab") as f:
        f.write((json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))
    return seq


def main() -> int:
    seq = 0
    last_sig: tuple[str, str] | None = None
    last_sig_ts = 0.0

    while True:
        msg = _recv_message()
        if msg is None:
            return 0

        msg_id = msg.get("id")
        method = msg.get("method")

        if method == "initialize":
            _send_message(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "realmoi-status", "version": "0.1.0"},
                    },
                }
            )
            continue

        if method == "ping":
            _send_message({"jsonrpc": "2.0", "id": msg_id, "result": {}})
            continue

        if method == "tools/list":
            _send_message(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "tools": [
                            {
                                "name": "realmoi_status_update",
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
                            }
                        ]
                    },
                }
            )
            continue

        if method == "tools/call":
            params = msg.get("params") or {}
            tool_name = params.get("name")
            args = params.get("arguments") or {}
            if tool_name != "realmoi_status_update":
                _send_message(
                    {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32601, "message": "Tool not found"},
                    }
                )
                continue

            stage = str(args.get("stage") or "")
            level = str(args.get("level") or "info")
            summary = str(args.get("summary") or "")
            attempt = int(args.get("attempt") or 1)
            progress = args.get("progress")
            try:
                progress_int = int(progress) if progress is not None else None
            except Exception:
                progress_int = None

            if stage not in STAGES:
                stage = "analysis"
            if level not in LEVELS:
                level = "info"
            summary = summary.strip()
            if len(summary) > 200:
                summary = summary[:200]
            if attempt < 1:
                attempt = 1

            # Dedupe: 1s same stage+summary
            sig = (stage, summary)
            now = time.time()
            if last_sig == sig and now - last_sig_ts < 1.0:
                _send_message(
                    {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "content": [{"type": "text", "text": "ok"}],
                            "structuredContent": {"deduped": True},
                        },
                    }
                )
                continue
            last_sig = sig
            last_sig_ts = now

            seq += 1
            job_id = str(args.get("job_id") or _read_job_id_fallback() or "")

            line = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                "seq": seq,
                "job_id": job_id,
                "attempt": attempt,
                "stage": stage,
                "level": level,
                "progress": progress_int,
                "summary": summary,
                "meta": args.get("meta") if isinstance(args.get("meta"), dict) else {},
            }
            _append_status_line(line)

            _send_message(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": "ok"}],
                        "structuredContent": {"seq": seq},
                    },
                }
            )
            continue

        # Ignore notifications
        if msg_id is None:
            continue

        _send_message({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}})


if __name__ == "__main__":
    raise SystemExit(main())
