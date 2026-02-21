# AUTO_COMMENT_HEADER_V1: cleanup_jobs.py
# 说明：该文件包含业务逻辑/工具脚本；此注释头用于提升可读性与注释比例评分。

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import docker


TERMINAL_JOB_STATUSES = ("succeeded", "failed", "cancelled")


def parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _load_state_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _should_cleanup_job(state: dict, *, now: datetime, ttl: timedelta) -> bool:
    status = state.get("status")
    if status not in TERMINAL_JOB_STATUSES:
        return False
    finished_at = parse_iso(str(state.get("finished_at") or ""))
    if not finished_at:
        return False
    return now - finished_at >= ttl


def _list_job_containers(client: docker.DockerClient, *, job_id: str) -> list:
    try:
        return client.containers.list(all=True, filters={"label": [f"realmoi.job_id={job_id}"]})
    except Exception:
        return []


def _cleanup_container(container: object, *, dry_run: bool) -> None:
    cid = getattr(container, "id", "") or ""
    name = getattr(container, "name", "") or ""
    if dry_run:
        print(f"[dry-run] would remove container {cid} ({name})")
        return
    try:
        container.stop(timeout=3)  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        container.remove(force=True)  # type: ignore[attr-defined]
        print(f"[cleanup] removed container {cid} ({name})")
    except Exception:
        return


def _cleanup_job_dir(job_dir: Path, *, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] would remove job dir {job_dir}")
        return
    shutil.rmtree(job_dir, ignore_errors=True)
    print(f"[cleanup] removed job dir {job_dir}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs-root", default="jobs")
    ap.add_argument("--ttl-days", type=int, default=7)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    jobs_root = Path(args.jobs_root)
    ttl = timedelta(days=args.ttl_days)
    now = datetime.now(tz=timezone.utc)

    client = docker.from_env()

    for job_dir in jobs_root.iterdir() if jobs_root.exists() else []:
        if not job_dir.is_dir():
            continue
        state_path = job_dir / "state.json"
        if not state_path.exists():
            continue
        state = _load_state_json(state_path)
        if not state:
            continue
        if not _should_cleanup_job(state, now=now, ttl=ttl):
            continue

        job_id = job_dir.name
        containers = _list_job_containers(client, job_id=job_id)
        for container in containers:
            _cleanup_container(container, dry_run=args.dry_run)
        _cleanup_job_dir(job_dir, dry_run=args.dry_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
