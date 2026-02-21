from __future__ import annotations

"""Small wrappers around low-level file-descriptor IO.

These helpers keep fd-based IO callsites simple and consistently best-effort.
They also centralize the `os.write/os.close` calls.
"""

import os
from typing import Callable


def write_fd_best_effort(*, fd: int, payload: bytes, label: str, log_warn: Callable[[str], None]) -> int:
    try:
        return os.write(fd, payload)
    except Exception as exc:
        log_warn(f"{label}_write_failed: {type(exc).__name__}: {exc}")
        return -1


def close_fd_best_effort(*, fd: int, label: str, log_warn: Callable[[str], None]) -> None:
    try:
        os.close(fd)
    except Exception as exc:
        log_warn(f"{label}_close_failed: {type(exc).__name__}: {exc}")

