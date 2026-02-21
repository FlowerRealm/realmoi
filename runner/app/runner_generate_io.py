from __future__ import annotations

import difflib
import json
import os
from pathlib import Path
from typing import Any

JOB_DIR = Path(os.environ.get("REALMOI_JOB_DIR") or "/job")


def job_path(*parts: str) -> Path:
    return JOB_DIR.joinpath(*parts)


def read_job() -> dict[str, Any]:
    return json.loads(job_path("input", "job.json").read_text(encoding="utf-8"))


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, obj: Any) -> None:
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def build_full_unified_diff(*, old_text: str, new_text: str, fromfile: str, tofile: str) -> str:
    old_norm = str(old_text or "").replace("\r\n", "\n").replace("\r", "\n")
    new_norm = str(new_text or "").replace("\r\n", "\n").replace("\r", "\n")
    old_lines = old_norm.splitlines(keepends=True)
    new_lines = new_norm.splitlines(keepends=True)
    n = max(len(old_lines), len(new_lines))
    return "".join(difflib.unified_diff(old_lines, new_lines, fromfile=fromfile, tofile=tofile, n=n))

