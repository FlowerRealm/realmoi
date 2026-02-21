from __future__ import annotations

from typing import Any

from ..deps import DbDep
from ..utils.errors import http_error


def commit_db(db: DbDep) -> None:
    # Commit with rollback on failure (best-effort).
    try:
        commit_result = db.commit()
        if commit_result is not None:
            _ = commit_result
    except Exception as exc:
        rollback_error: str | None = None
        try:
            rollback_result = db.rollback()
            if rollback_result is not None:
                _ = rollback_result
        except Exception as rollback_exc:
            rollback_error = str(rollback_exc)
        details = f"Commit failed: {exc}"
        if rollback_error:
            details = f"{details}; rollback failed: {rollback_error}"
        http_error(500, "db_error", details)


def refresh_db(db: DbDep, obj: Any) -> None:
    try:
        refresh_result = db.refresh(obj)
        if refresh_result is not None:
            _ = refresh_result
    except Exception as exc:
        http_error(500, "db_error", f"Refresh failed: {exc}")
