from __future__ import annotations

import os
import socket
import time
from pathlib import Path

from .services.job_manager import JobManager
from .settings import SETTINGS


def _resolve_machine_id() -> str:
    value = str(SETTINGS.judge_machine_id or "").strip()
    if value:
        return value
    return f"{socket.gethostname()}-{os.getpid()}"


def main() -> int:
    manager = JobManager(jobs_root=Path(SETTINGS.jobs_root))
    machine_id = _resolve_machine_id()
    interval = max(100, int(SETTINGS.judge_poll_interval_ms or 1000)) / 1000.0

    print(
        f"[judge] machine_id={machine_id} mode={SETTINGS.judge_mode} executor={SETTINGS.runner_executor} poll={interval:.3f}s",
        flush=True,
    )
    if SETTINGS.judge_mode != "independent":
        print("[judge] warning: REALMOI_JUDGE_MODE is not independent", flush=True)

    while True:
        claimed = manager.claim_next_queued_job(machine_id=machine_id)
        if claimed is None:
            time.sleep(interval)
            continue

        job_id = claimed["job_id"]
        print(f"[judge] claimed job_id={job_id}", flush=True)
        manager.run_claimed_job(
            job_id=job_id,
            owner_user_id=claimed["owner_user_id"],
            lock_path=claimed["lock_path"],
        )


if __name__ == "__main__":
    raise SystemExit(main())
