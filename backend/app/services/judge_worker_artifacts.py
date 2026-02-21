from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .judge_mcp_client import McpJudgeClient, McpJudgeClientError
from .judge_worker_common import log_warn


def sync_final_state(*, client: McpJudgeClient, job_id: str, claim_id: str, state_path: Path) -> None:
    # Push final state.json snapshot back to backend best-effort.
    try:
        local_state = json.loads(state_path.read_text(encoding="utf-8"))
        if isinstance(local_state, dict):
            client.call_tool(
                name="judge.job.patch_state",
                arguments={"job_id": job_id, "claim_id": claim_id, "patch": local_state},
            )
    except (OSError, ValueError) as exc:
        log_warn(key="final_state_read", message=f"sync final state: read failed job_id={job_id}: {exc}")
    except McpJudgeClientError as exc:
        log_warn(key="final_state", message=f"sync final state failed job_id={job_id}: {exc}")


def read_artifacts(*, output_dir: Path) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    # Read output artifacts produced by runner.
    main_cpp = ""
    solution_json: dict[str, Any] | None = None
    report_json: dict[str, Any] | None = None
    try:
        main_path = output_dir / "main.cpp"
        if main_path.exists():
            main_cpp = main_path.read_text(encoding="utf-8", errors="replace")
        sol_path = output_dir / "solution.json"
        if sol_path.exists():
            loaded = json.loads(sol_path.read_text(encoding="utf-8"))
            solution_json = loaded if isinstance(loaded, dict) else None
        rep_path = output_dir / "report.json"
        if rep_path.exists():
            loaded = json.loads(rep_path.read_text(encoding="utf-8"))
            report_json = loaded if isinstance(loaded, dict) else None
    except (OSError, ValueError) as exc:
        log_warn(key="read_artifacts", message=f"read artifacts failed: {exc}")
        return main_cpp, None, None
    return main_cpp, solution_json, report_json


def upload_artifacts(
    *,
    client: McpJudgeClient,
    job_id: str,
    claim_id: str,
    main_cpp: str,
    solution_json: dict[str, Any] | None,
    report_json: dict[str, Any] | None,
) -> None:
    # Upload final artifacts back to backend.
    try:
        client.call_tool(
            name="judge.job.put_artifacts",
            arguments={
                "job_id": job_id,
                "claim_id": claim_id,
                "main_cpp": main_cpp,
                "solution_json": solution_json or {},
                "report_json": report_json or {},
            },
        )
    except McpJudgeClientError as exc:
        log_warn(key="upload_artifacts", message=f"upload artifacts failed job_id={job_id}: {exc}")


def cleanup_workspace(*, root: Path) -> None:
    try:
        shutil.rmtree(root)
    except OSError:
        shutil.rmtree(root, ignore_errors=True)

