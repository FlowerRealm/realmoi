from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .job_paths import JobPaths
from ..settings import SETTINGS


def new_self_test_token() -> str:
    """Create a random token for external self-test API."""

    return secrets.token_urlsafe(24)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_runner_test_script() -> Path:
    path = Path(SETTINGS.runner_test_script)
    if path.is_absolute():
        return path
    return _project_root() / path


def run_external_self_test(*, paths: JobPaths, main_cpp: str) -> dict[str, Any]:
    """Run runner_test in an isolated temp job workspace.

    Args:
        paths: Real job paths.
        main_cpp: Candidate solution source code.

    Returns:
        External self-test result and parsed report.
    """

    if not main_cpp.strip():
        raise ValueError("empty_main_cpp")

    temp_root = paths.root / ".self_test_tmp" / secrets.token_hex(8)
    input_link = temp_root / "input"
    output_dir = temp_root / "output"
    work_dir = temp_root / ".tmp_work"

    try:
        temp_root.mkdir(parents=True, exist_ok=True)
        try:
            input_link.symlink_to(paths.input_dir.resolve(), target_is_directory=True)
        except OSError:
            shutil.copytree(paths.input_dir, input_link, dirs_exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "main.cpp").write_text(main_cpp, encoding="utf-8")

        cmd = [sys.executable, "-X", "utf8", str(_resolve_runner_test_script().resolve())]
        env = os.environ.copy()
        env.update(
            {
                "ATTEMPT": "1",
                "REALMOI_JOB_DIR": str(temp_root.resolve()),
                "REALMOI_WORK_DIR": str(work_dir.resolve()),
            }
        )
        timeout_seconds = max(10, int(SETTINGS.judge_self_test_timeout_seconds or 90))
        completed = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout_seconds,
        )

        report_path = temp_root / "output" / "artifacts" / "attempt_1" / "test_output" / "report.json"
        if not report_path.exists():
            raise RuntimeError("self_test_report_missing")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        compile_info = report.get("compile") if isinstance(report.get("compile"), dict) else {}

        return {
            "status": str(report.get("status") or "failed"),
            "runner_exit_code": int(completed.returncode),
            "compile_ok": bool(compile_info.get("ok")),
            "summary": summary,
            "report": report,
            "stdout_tail": str(completed.stdout or "")[-4000:],
            "stderr_tail": str(completed.stderr or "")[-4000:],
        }
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
