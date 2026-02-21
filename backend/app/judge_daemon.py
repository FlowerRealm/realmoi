from __future__ import annotations

# Independent judge worker daemon entrypoint.
#
# The operational logic lives in `backend/app/services/judge_worker.py` so the
# entrypoint stays lightweight and metrics focus on the actual orchestration.

from .services.judge_worker import run_daemon


def main() -> int:
    return run_daemon()


if __name__ == "__main__":
    raise SystemExit(main())

