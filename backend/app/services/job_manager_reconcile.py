#
# Job state reconcile helpers (best-effort).
#
from __future__ import annotations

"""后端重启后的 best-effort reconcile。"""

import pathlib
import typing

from ..services import job_state


def load_state_safe(state_path: pathlib.Path) -> dict[str, typing.Any] | None:
    try:
        state = job_state.load_state(state_path)
    except Exception:
        return None
    return state if isinstance(state, dict) else None


def mark_failed_state(*, state: dict[str, typing.Any], state_path: pathlib.Path, code: str, message: str) -> None:
    state["status"] = "failed"
    state["finished_at"] = job_state.now_iso()
    state["expires_at"] = job_state.iso_after_days(7)
    state["error"] = {"code": code, "message": message}
    job_state.save_state(state_path, state)


def reconcile_local_running(
    *,
    state: dict[str, typing.Any],
    state_path: pathlib.Path,
    stage: str,
    judge_mode: str,
) -> None:
    if judge_mode == "independent":
        return
    mark_failed_state(
        state=state,
        state_path=state_path,
        code="local_process_missing",
        message=f"Local {stage} process missing after restart",
    )


def reconcile_docker_running(
    *,
    state: dict[str, typing.Any],
    state_path: pathlib.Path,
    stage: str,
    docker_client: typing.Any | None,
) -> None:
    if docker_client is None:
        mark_failed_state(state=state, state_path=state_path, code="docker_unavailable", message="Docker executor unavailable")
        return

    container_info = (state.get("containers") or {}).get(stage) or {}
    container_id = container_info.get("id")
    if not container_id:
        return

    try:
        container = docker_client.containers.get(container_id)
    except Exception:
        mark_failed_state(state=state, state_path=state_path, code="container_missing", message="Container missing")
        return

    container.reload()
    if container.status != "exited":
        return

    exit_code = int(container.attrs.get("State", {}).get("ExitCode") or 0)
    container_info["exit_code"] = exit_code
    (state.setdefault("containers", {}))[stage] = container_info
    if exit_code != 0:
        mark_failed_state(state=state, state_path=state_path, code=f"{stage}_failed", message="Container exited")
        return

    job_state.save_state(state_path, state)


def reconcile_jobs(
    *,
    jobs_root: pathlib.Path,
    runner_executor: str,
    judge_mode: str,
    docker_client: typing.Any | None,
) -> None:
    for job_dir in jobs_root.iterdir():
        if not job_dir.is_dir():
            continue
        state_path = job_dir / "state.json"
        if not state_path.exists():
            continue

        state = load_state_safe(state_path)
        if state is None:
            continue

        status = state.get("status")
        if status not in ("running_generate", "running_test"):
            continue
        stage = "generate" if status == "running_generate" else "test"

        if runner_executor != "docker":
            reconcile_local_running(state=state, state_path=state_path, stage=stage, judge_mode=judge_mode)
            continue

        reconcile_docker_running(state=state, state_path=state_path, stage=stage, docker_client=docker_client)
