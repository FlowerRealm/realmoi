#
# Job path helpers (filesystem layout).
#
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class JobPaths:
    root: Path
    input_dir: Path
    output_dir: Path
    logs_dir: Path
    state_json: Path
    job_json: Path
    tests_dir: Path
    terminal_log: Path
    agent_status_jsonl: Path


def get_job_paths(*, jobs_root: Path, job_id: str) -> JobPaths:
    root = jobs_root / job_id
    input_dir = root / "input"
    output_dir = root / "output"
    logs_dir = root / "logs"
    return JobPaths(
        root=root,
        input_dir=input_dir,
        output_dir=output_dir,
        logs_dir=logs_dir,
        state_json=root / "state.json",
        job_json=input_dir / "job.json",
        tests_dir=input_dir / "tests",
        terminal_log=logs_dir / "terminal.log",
        agent_status_jsonl=logs_dir / "agent_status.jsonl",
    )
