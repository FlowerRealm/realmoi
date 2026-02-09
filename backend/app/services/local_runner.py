from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Callable


def stop_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Stop a local runner process and its process group.

    Args:
        process: Running process handle.
    """

    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except Exception:
        try:
            process.terminate()
        except Exception:
            return


def run_local_runner(
    *,
    script_path: Path,
    env: dict[str, str],
    log_path: Path,
    max_bytes: int,
    redact_secrets: list[str],
    on_started: Callable[[subprocess.Popen[bytes]], None] | None = None,
    on_finished: Callable[[], None] | None = None,
) -> tuple[int, int]:
    """Run a local runner script and stream logs into terminal.log.

    Args:
        script_path: Python script path to execute.
        env: Extra environment variables for the runner process.
        log_path: Terminal log file path.
        max_bytes: Max bytes to append to terminal log.
        redact_secrets: Secrets to redact from terminal output.
        on_started: Optional callback after process starts.
        on_finished: Optional callback before function returns.

    Returns:
        A tuple of (exit_code, pid).
    """

    merged_env = os.environ.copy()
    merged_env.update(env)
    cmd = [sys.executable, "-X", "utf8", str(script_path)]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=merged_env,
        preexec_fn=os.setsid,
    )
    if on_started:
        on_started(process)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0

    def _redact(data: bytes) -> bytes:
        output = data
        for secret in redact_secrets:
            if secret:
                output = output.replace(secret.encode("utf-8"), b"***")
        return output

    try:
        assert process.stdout is not None
        with log_path.open("ab") as log_file:
            for chunk in iter(process.stdout.readline, b""):
                safe_chunk = _redact(chunk)
                if written >= max_bytes:
                    continue
                remaining = max_bytes - written
                out = safe_chunk[:remaining]
                log_file.write(out)
                log_file.flush()
                written += len(out)
        exit_code = int(process.wait() or 0)
        return exit_code, process.pid
    finally:
        if on_finished:
            on_finished()
