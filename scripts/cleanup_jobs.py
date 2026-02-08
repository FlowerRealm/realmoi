from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import docker


def parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


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
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        status = state.get("status")
        if status not in ("succeeded", "failed", "cancelled"):
            continue
        finished_at = parse_iso(str(state.get("finished_at") or ""))
        if not finished_at:
            continue
        if now - finished_at < ttl:
            continue

        job_id = job_dir.name
        try:
            matched = client.containers.list(all=True, filters={"label": [f"realmoi.job_id={job_id}"]})
        except Exception:
            matched = []
        for c in matched:
            cid = getattr(c, "id", "") or ""
            name = getattr(c, "name", "") or ""
            if args.dry_run:
                print(f"[dry-run] would remove container {cid} ({name})")
                continue
            try:
                c.stop(timeout=3)
            except Exception:
                pass
            try:
                c.remove(force=True)
                print(f"[cleanup] removed container {cid} ({name})")
            except Exception:
                continue

        if args.dry_run:
            print(f"[dry-run] would remove job dir {job_dir}")
            continue
        shutil.rmtree(job_dir, ignore_errors=True)
        print(f"[cleanup] removed job dir {job_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
