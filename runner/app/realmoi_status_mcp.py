from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import fcntl  # type: ignore
except Exception:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]


STAGES = {"analysis", "plan", "search", "coding", "test", "repair", "done", "error"}
LEVELS = {"info", "warn", "error"}
JOB_DIR = Path(os.environ.get("REALMOI_JOB_DIR") or "/job")


def job_path(*parts: str) -> Path:
    return JOB_DIR.joinpath(*parts)


def _read_job_id_fallback() -> str:
    try:
        job = json.loads(job_path("input", "job.json").read_text(encoding="utf-8"))
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
    log_path = job_path("logs", "agent_status.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as f:
        try:
            if fcntl is not None:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write((json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))
            f.flush()
        finally:
            if fcntl is not None:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
    return 0


def _resolve_runner_test_script() -> Path:
    # realmoi_status_mcp.py lives next to runner_test.py both locally and in runner image (/app).
    return Path(__file__).resolve().parent / "runner_test.py"


def _tail_text(text: str, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _run_local_self_test(*, main_cpp: str, timeout_seconds: int) -> dict[str, Any]:
    if not main_cpp.strip():
        raise ValueError("empty_main_cpp")

    temp_root = job_path(".self_test_tmp", secrets.token_hex(8))
    input_link = temp_root / "input"
    output_dir = temp_root / "output"
    work_dir = temp_root / ".tmp_work"

    try:
        temp_root.mkdir(parents=True, exist_ok=True)
        try:
            input_link.symlink_to(job_path("input").resolve(), target_is_directory=True)
        except OSError:
            shutil.copytree(job_path("input"), input_link, dirs_exist_ok=True)

        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "main.cpp").write_text(main_cpp.rstrip() + "\n", encoding="utf-8")

        cmd = [sys.executable, "-X", "utf8", str(_resolve_runner_test_script())]
        env = os.environ.copy()
        env.update(
            {
                "ATTEMPT": "1",
                "REALMOI_JOB_DIR": str(temp_root.resolve()),
                "REALMOI_WORK_DIR": str(work_dir.resolve()),
            }
        )
        completed = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=max(1, int(timeout_seconds)),
        )

        report_path = temp_root / "output" / "artifacts" / "attempt_1" / "test_output" / "report.json"
        if not report_path.exists():
            raise RuntimeError("self_test_report_missing")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        compile_info = report.get("compile") if isinstance(report.get("compile"), dict) else {}

        return {
            "ok": str(report.get("status") or "") == "succeeded",
            "status": str(report.get("status") or "failed"),
            "runner_exit_code": int(completed.returncode),
            "compile_ok": bool(compile_info.get("ok")),
            "first_failure": summary.get("first_failure"),
            "first_failure_verdict": summary.get("first_failure_verdict"),
            "first_failure_message": summary.get("first_failure_message"),
            "stdout_tail": _tail_text(str(completed.stdout or ""), 4000),
            "stderr_tail": _tail_text(str(completed.stderr or ""), 4000),
        }
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


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
                                "name": "status.update",
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
                            ,
                            {
                                "name": "agent.delta",
                                "description": "Append a structured agent delta line for realmoi UI streaming.",
                                "inputSchema": {
                                    "type": "object",
                                    "additionalProperties": True,
                                    "properties": {
                                        "job_id": {"type": "string"},
                                        "attempt": {"type": "integer"},
                                        "stage": {"type": "string"},
                                        "level": {"type": "string"},
                                        "kind": {"type": "string"},
                                        "delta": {"type": "string"},
                                        "meta": {"type": "object"},
                                    },
                                    "required": ["stage", "kind"],
                                },
                            },
                            {
                                "name": "judge.self_test",
                                "description": "Run a local self-test (compile + run provided tests) in an isolated temp workspace, and return a compact summary.",
                                "inputSchema": {
                                    "type": "object",
                                    "additionalProperties": True,
                                    "properties": {
                                        "main_cpp": {"type": "string"},
                                        "timeout_seconds": {"type": "integer"},
                                    },
                                    "required": ["main_cpp"],
                                },
                            },
                        ]
                    },
                }
            )
            continue

        if method == "tools/call":
            params = msg.get("params") or {}
            tool_name = params.get("name")
            args = params.get("arguments") or {}
            if tool_name not in {"status.update", "agent.delta", "judge.self_test"}:
                _send_message(
                    {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32601, "message": "Tool not found"},
                    }
                )
                continue

            if tool_name == "agent.delta":
                stage = str(args.get("stage") or "")
                level = str(args.get("level") or "info")
                kind = str(args.get("kind") or "").strip()
                delta = str(args.get("delta") or "")
                attempt = int(args.get("attempt") or 1)
                meta = args.get("meta") if isinstance(args.get("meta"), dict) else {}

                if stage not in STAGES:
                    stage = "analysis"
                if level not in LEVELS:
                    level = "info"
                if attempt < 1:
                    attempt = 1
                if not kind:
                    kind = "other"

                # Cap single delta to keep jsonl reasonable.
                if len(delta) > 20000:
                    delta = delta[:20000]

                seq += 1
                job_id = str(args.get("job_id") or _read_job_id_fallback() or "")
                now = time.time()
                summary = (delta.strip() or kind)[:200]

                _append_status_line(
                    {
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                        "seq": f"mcp-{seq}",
                        "job_id": job_id,
                        "attempt": attempt,
                        "stage": stage,
                        "level": level,
                        "progress": None,
                        "summary": summary,
                        "kind": kind,
                        "delta": delta,
                        "meta": meta,
                    }
                )

                _send_message(
                    {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "content": [{"type": "text", "text": "ok"}],
                            "structuredContent": {"seq": f"mcp-{seq}"},
                        },
                    }
                )
                continue

            if tool_name == "judge.self_test":
                main_cpp = str(args.get("main_cpp") or "")
                timeout_seconds = args.get("timeout_seconds")
                try:
                    timeout_int = int(timeout_seconds) if timeout_seconds is not None else 90
                except Exception:
                    timeout_int = 90
                timeout_int = max(10, min(timeout_int, 600))

                try:
                    result = _run_local_self_test(main_cpp=main_cpp, timeout_seconds=timeout_int)
                except ValueError as e:
                    _send_message(
                        {
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "error": {"code": -32602, "message": f"Invalid params: {e}"},
                        }
                    )
                    continue
                except Exception as e:
                    payload = {
                        "ok": False,
                        "status": "error",
                        "error": f"{type(e).__name__}: {e}",
                    }
                    try:
                        seq += 1
                        _append_status_line(
                            {
                                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())),
                                "seq": f"mcp-{seq}",
                                "job_id": _read_job_id_fallback(),
                                "attempt": int(args.get("attempt") or 1),
                                "stage": "error",
                                "level": "error",
                                "progress": None,
                                "summary": f"自测失败：{payload['error']}"[:200],
                                "meta": {},
                            }
                        )
                    except Exception:
                        pass
                    _send_message(
                        {
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "result": {
                                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
                                "structuredContent": payload,
                            },
                        }
                    )
                    continue

                # Emit a short UI hint line (best-effort, no numeric seq).
                try:
                    summary = "自测通过" if result.get("ok") else "自测未通过"
                    detail = ""
                    if not result.get("ok"):
                        verdict = str(result.get("first_failure_verdict") or "")
                        case = str(result.get("first_failure") or "")
                        msg_ = str(result.get("first_failure_message") or "")
                        bits = [x for x in (verdict, case, msg_) if x]
                        if bits:
                            detail = "：" + " ".join(bits)
                    seq += 1
                    _append_status_line(
                        {
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())),
                            "seq": f"mcp-{seq}",
                            "job_id": _read_job_id_fallback(),
                            "attempt": int(args.get("attempt") or 1),
                            "stage": "done" if result.get("ok") else "repair",
                            "level": "info" if result.get("ok") else "warn",
                            "progress": None,
                            "summary": (summary + detail)[:200],
                            "meta": {},
                        }
                    )
                except Exception:
                    pass

                _send_message(
                    {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                            "structuredContent": result,
                        },
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
                "seq": f"mcp-{seq}",
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
                        "structuredContent": {"seq": f"mcp-{seq}"},
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
