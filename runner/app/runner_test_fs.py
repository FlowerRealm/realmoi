from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any


JOB_DIR = Path(os.environ.get("REALMOI_JOB_DIR") or "/job")
WORK_DIR = Path(os.environ.get("REALMOI_WORK_DIR") or "/tmp/work")


def job_path(*parts: str) -> Path:
    return JOB_DIR.joinpath(*parts)


def read_text(path: Path, *, encoding: str = "utf-8", errors: str | None = None) -> str:
    # Small wrapper so IO failures are reported consistently.
    try:
        if errors is None:
            return path.read_text(encoding=encoding)
        return path.read_text(encoding=encoding, errors=errors)
    except Exception as exc:
        raise RuntimeError(f"read_text_failed:{path}:{exc}") from exc


def read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except Exception as exc:
        raise RuntimeError(f"read_bytes_failed:{path}:{exc}") from exc


def write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding=encoding)
    except Exception as exc:
        raise RuntimeError(f"write_text_failed:{path}:{exc}") from exc


def write_json(path: Path, obj: Any) -> None:
    # Persist JSON with stable formatting for backend/UI consumption.
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def prepare_dirs(*, attempt: int) -> tuple[Path, Path]:
    # Prepare clean output + work directories.
    out_root = job_path("output") / "artifacts" / f"attempt_{attempt}" / "test_output"
    try:
        shutil.rmtree(out_root)
    except FileNotFoundError:
        pass
    except OSError:
        pass
    try:
        shutil.rmtree(WORK_DIR)
    except FileNotFoundError:
        pass
    except OSError:
        pass
    out_root.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    return out_root, WORK_DIR

