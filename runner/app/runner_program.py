from __future__ import annotations

# Minimal subprocess runner for compiled solutions.
#
# This module is intentionally self-contained so it can be reused by different
# runner entrypoints (test/generate/etc.) without creating a single mega-file.

import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def setsid_preexec() -> None:
    # Start program in a dedicated process group so we can SIGKILL the group on timeout/OLE.
    os.setsid()


@dataclass
class RunProgramState:
    # Mutable state used by run_program() and its helpers.
    reaped: bool = False
    exit_code: int | None = None
    signal_no: int | None = None
    peak_rss_kb: int | None = None
    timeout: bool = False
    output_limit_exceeded: bool = False
    reap_error: str | None = None


@dataclass(frozen=True)
class DrainReadyStreamsArgs:
    sel: selectors.BaseSelector
    proc: subprocess.Popen[bytes]
    stdout: bytearray
    stderr: bytearray
    output_limit_bytes: int
    state: RunProgramState


def kill_process_group(proc: subprocess.Popen[bytes]) -> None:
    # Best-effort: prefer killing the process group; fall back to proc.kill().
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        # Process already exited.
        return
    except PermissionError:
        proc.kill()


def extract_peak_rss_kb(ru: Any) -> int:
    raw = getattr(ru, "ru_maxrss", 0) or 0
    if isinstance(raw, bool):
        maxrss = 0
    elif isinstance(raw, int):
        maxrss = raw
    elif isinstance(raw, float):
        maxrss = int(raw)
    elif isinstance(raw, str) and raw.strip().isdigit():
        maxrss = int(raw.strip())
    else:
        maxrss = 0
    return max(0, maxrss)


def try_reap_nohang(proc: subprocess.Popen[bytes], state: RunProgramState) -> None:
    # Read exit status and ru_maxrss (Linux) without blocking.
    if state.reaped:
        return

    try:
        pid, status, ru = os.wait4(proc.pid, os.WNOHANG)
    except ChildProcessError:
        state.reaped = True
        if state.exit_code is None:
            state.exit_code = int(proc.returncode) if proc.returncode is not None else 0
        return
    except OSError as e:
        # Reaping失败时不终止测试；记录原因供上层诊断。
        state.reap_error = str(e)
        return

    if pid == 0:
        return

    state.reaped = True
    if os.WIFEXITED(status):
        state.exit_code = os.WEXITSTATUS(status)
    elif os.WIFSIGNALED(status):
        state.signal_no = os.WTERMSIG(status)
        state.exit_code = -int(state.signal_no)
    else:
        state.exit_code = 0
    state.peak_rss_kb = extract_peak_rss_kb(ru)


def reap_blocking(proc: subprocess.Popen[bytes], state: RunProgramState) -> None:
    if state.reaped:
        return
    try:
        _pid, status, ru = os.wait4(proc.pid, 0)
        state.reaped = True
        if os.WIFEXITED(status):
            state.exit_code = os.WEXITSTATUS(status)
        elif os.WIFSIGNALED(status):
            state.signal_no = os.WTERMSIG(status)
            state.exit_code = -int(state.signal_no)
        else:
            state.exit_code = 0
        state.peak_rss_kb = extract_peak_rss_kb(ru)
    except (ChildProcessError, OSError) as e:
        state.reap_error = str(e)
        try:
            state.exit_code = int(proc.wait(timeout=1))
        except subprocess.TimeoutExpired:
            state.exit_code = int(proc.returncode) if proc.returncode is not None else 0
        except OSError:
            state.exit_code = int(proc.returncode) if proc.returncode is not None else 0
        state.reaped = True


def spawn_program(exe_path: Path, *, work_dir: Path) -> subprocess.Popen[bytes]:
    proc = subprocess.Popen(
        [str(exe_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(work_dir),
        preexec_fn=setsid_preexec,
    )
    assert proc.stdin and proc.stdout and proc.stderr
    return proc


def feed_stdin(proc: subprocess.Popen[bytes], input_bytes: bytes) -> None:
    assert proc.stdin
    written = proc.stdin.write(input_bytes)
    if written is None:
        raise RuntimeError("stdin_write_failed")
    if written != len(input_bytes):
        remaining = memoryview(input_bytes)[written:]
        while remaining:
            n = proc.stdin.write(remaining)
            if not isinstance(n, int) or n <= 0:
                break
            remaining = remaining[n:]
    proc.stdin.flush()
    close_result = proc.stdin.close()
    if close_result is not None:
        _ = close_result


def init_selector(proc: subprocess.Popen[bytes]) -> selectors.BaseSelector:
    assert proc.stdout and proc.stderr
    sel = selectors.DefaultSelector()
    _ = sel.register(proc.stdout, selectors.EVENT_READ, data="stdout")
    _ = sel.register(proc.stderr, selectors.EVENT_READ, data="stderr")
    return sel


def enforce_deadline(proc: subprocess.Popen[bytes], state: RunProgramState, *, now: float, deadline: float) -> None:
    if now < deadline:
        return
    if state.reaped:
        return
    state.timeout = True
    kill_process_group(proc)
    try_reap_nohang(proc, state)


def drain_ready_streams(args: DrainReadyStreamsArgs) -> None:
    if not args.sel.get_map():
        return
    events = args.sel.select(timeout=0.05)
    for key, _mask in events:
        stream_name = key.data
        data = key.fileobj.read1(4096)  # type: ignore[attr-defined]
        if not data:
            args.sel.unregister(key.fileobj)
            continue
        if stream_name == "stdout":
            args.stdout.extend(data)
        else:
            args.stderr.extend(data)

        if len(args.stdout) + len(args.stderr) > args.output_limit_bytes and not args.state.reaped:
            args.state.output_limit_exceeded = True
            kill_process_group(args.proc)
            try_reap_nohang(args.proc, args.state)
            return


def run_program(
    *,
    exe_path: Path,
    input_bytes: bytes,
    time_limit_ms: int,
    output_limit_bytes: int,
    work_dir: Path,
) -> dict[str, Any]:
    # Run compiled program once with limits and capture output.

    start = time.monotonic()
    proc = spawn_program(exe_path, work_dir=work_dir)
    feed_stdin(proc, input_bytes)

    sel = init_selector(proc)

    stdout = bytearray()
    stderr = bytearray()
    state = RunProgramState()
    drain_args = DrainReadyStreamsArgs(
        sel=sel,
        proc=proc,
        stdout=stdout,
        stderr=stderr,
        output_limit_bytes=output_limit_bytes,
        state=state,
    )

    deadline = start + (time_limit_ms / 1000.0)
    while True:
        now = time.monotonic()
        try_reap_nohang(proc, state)
        enforce_deadline(proc, state, now=now, deadline=deadline)
        drain_ready_streams(drain_args)

        if state.reaped and not sel.get_map():
            break

        if not sel.get_map() and not state.reaped:
            time.sleep(0.02)

    end = time.monotonic()
    reap_blocking(proc, state)
    if state.exit_code is None:
        state.exit_code = 0
    return {
        "exit_code": int(state.exit_code),
        "timeout": state.timeout,
        "output_limit_exceeded": state.output_limit_exceeded,
        "time_ms": int((end - start) * 1000),
        "memory_kb": state.peak_rss_kb,
        "stdout": bytes(stdout),
        "stderr": bytes(stderr),
    }
