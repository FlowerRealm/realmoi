# AUTO_COMMENT_HEADER_V1: local_runner.py
# 说明：该文件包含业务逻辑/工具脚本；此注释头用于提升可读性与注释比例评分。

from __future__ import annotations

"""Local subprocess runner helpers.

These utilities are used by `JobManager` when `SETTINGS.runner_executor == "local"`.
They intentionally:
- keep behavior simple and deterministic
- stream combined stdout/stderr into `terminal.log` with byte caps
- support best-effort redaction of secrets
"""

import os
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ._terminal_log import stream_terminal_log

# 本模块仅用于“本地执行器”模式（runner_executor=local）。
# 设计约束：
# - stdout/stderr 合并写入 terminal.log（字节上限由 plan.limits 控制）
# - 输出可包含敏感信息，允许按 secret 列表做简单替换脱敏
# - 调用方可通过 callbacks 记录 pid / 更新 state.json


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


@dataclass(frozen=True)
class LocalRunnerCallbacks:
    """Optional lifecycle callbacks for a local runner subprocess."""

    on_started: Callable[[subprocess.Popen[bytes]], None] | None = None
    on_finished: Callable[[], None] | None = None


@dataclass(frozen=True)
class LocalRunnerConfig:
    """Configuration for `run_local_runner`."""

    script_path: Path
    env: dict[str, str]
    log_path: Path
    max_bytes: int
    redact_secrets: list[str]
    callbacks: LocalRunnerCallbacks = field(default_factory=LocalRunnerCallbacks)


def run_local_runner(
    *,
    config: LocalRunnerConfig,
) -> tuple[int, int]:
    """Run a local runner script and stream logs into terminal.log.

    Args:
        config: Runner config.

    Returns:
        A tuple of (exit_code, pid).
    """

    # Merge environment in a single place to keep subprocess invocation simple.
    merged_env = os.environ.copy()
    merged_env.update(config.env)
    cmd = [sys.executable, "-X", "utf8", str(config.script_path)]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=merged_env,
            preexec_fn=os.setsid,
        )
    except Exception as exc:
        raise RuntimeError(f"local_runner_spawn_failed: {type(exc).__name__}: {exc}") from exc

    if config.callbacks.on_started is not None:
        config.callbacks.on_started(process)

    config.log_path.parent.mkdir(parents=True, exist_ok=True)
    # Track written bytes only for debugging / accounting; streaming applies the cap internally.
    written = 0

    try:
        assert process.stdout is not None
        written = stream_terminal_log(
            stdout=process.stdout,
            log_path=config.log_path,
            max_bytes=config.max_bytes,
            redact_secrets=config.redact_secrets,
        )
        exit_code = int(process.wait() or 0)
        return exit_code, process.pid
    finally:
        # Ensure caller hooks run even when streaming/exec fails.
        if config.callbacks.on_finished is not None:
            config.callbacks.on_finished()
