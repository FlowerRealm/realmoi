from __future__ import annotations

"""IO helpers for `codex exec` subprocess streaming."""

import subprocess
from pathlib import Path
from typing import Callable


def write_prompt_and_close(*, proc: subprocess.Popen[bytes], prompt: str) -> None:
    stdin = proc.stdin
    if stdin is None:
        raise RuntimeError("codex_exec_stdin_missing")
    stdin.write(prompt.encode("utf-8"))
    stdin.close()


def stream_stdout_to_jsonl(
    *,
    proc: subprocess.Popen[bytes],
    jsonl_path: Path,
    handle_line: Callable[[str], None],
) -> int:
    stdout = proc.stdout
    if stdout is None:
        raise RuntimeError("codex_exec_stdout_missing")

    with jsonl_path.open("wb") as out:
        while True:
            chunk = stdout.readline()
            if not chunk:
                if proc.poll() is not None:
                    break
                continue
            out.write(chunk)
            out.flush()
            handle_line(chunk.decode("utf-8", errors="replace"))

    return int(proc.wait() or 0)

