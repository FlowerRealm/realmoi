from __future__ import annotations

"""Job 执行阶段（generate + test）的 attempt 循环。

将 `JobManager.run_job_thread` 的核心逻辑拆出，降低 `job_manager.py` 的复杂度与文件体积。
该逻辑保持 best-effort：失败会写回 state.json，避免 UI 卡死在 running 状态。
"""

import json
import pathlib
import typing

from ..services import job_paths, job_state
from ..settings import SETTINGS
from . import job_manager_utils

if typing.TYPE_CHECKING:  # pragma: no cover
    from .job_manager import JobManager


def is_cancelled(*, paths: job_paths.JobPaths) -> bool:
    # Cancellation is stored in state.json and can be triggered from the UI or via MCP.
    return job_state.load_state(paths.state_json).get("status") == "cancelled"


def report_is_success(*, report_path: pathlib.Path) -> bool:
    if not report_path.exists():
        return False
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(report, dict) and report.get("status") == "succeeded"


def mark_failed_state(*, paths: job_paths.JobPaths, message: str) -> None:
    state = job_state.load_state(paths.state_json)
    if state.get("status") == "cancelled":
        return
    state["status"] = "failed"
    state["finished_at"] = job_state.now_iso()
    state["expires_at"] = job_state.iso_after_days(7)
    state["error"] = {"code": "failed", "message": message}
    job_state.save_state(paths.state_json, state)


def append_retry_terminal(*, paths: job_paths.JobPaths, attempt: int) -> None:
    job_manager_utils.append_terminal(paths, f"[backend] attempt {attempt} failed, retrying (repair)...\n")


def run_job_attempts(*, manager: "JobManager", jobs_root: pathlib.Path, job_id: str, owner_user_id: str) -> None:
    paths = job_paths.get_job_paths(jobs_root=jobs_root, job_id=job_id)
    attempts_total = 1 + max(0, int(SETTINGS.quality_max_retries))

    try:
        for attempt in range(1, attempts_total + 1):
            if is_cancelled(paths=paths):
                return

            # After a failed attempt, switch to repair prompt mode.
            prompt_mode = "generate" if attempt == 1 else "repair"
            manager.run_generate(paths=paths, owner_user_id=owner_user_id, attempt=attempt, prompt_mode=prompt_mode)
            manager.run_test(paths=paths, owner_user_id=owner_user_id, attempt=attempt)

            if report_is_success(report_path=paths.output_dir / "report.json"):
                manager.finalize_success(paths=paths)
                return

            if attempt < attempts_total:
                append_retry_terminal(paths=paths, attempt=attempt)
                continue

            raise RuntimeError("quality_retries_exhausted")
    except Exception as error:
        mark_failed_state(paths=paths, message=str(error))
