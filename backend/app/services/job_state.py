#
# Job state helpers.
#
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..utils.fs import read_json, write_json


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def iso_after_days(days: int) -> str:
    return (datetime.now(tz=timezone.utc) + timedelta(days=days)).isoformat()


def load_state(path: Path) -> dict[str, Any]:
    return read_json(path)


def save_state(path: Path, state: dict[str, Any]) -> None:
    write_json(path, state)
