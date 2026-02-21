from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


CompareMode = Literal["tokens", "trim_ws", "exact"]


@dataclass(frozen=True)
class Case:
    name: str
    group: str
    input_rel: str
    expected_rel: str | None
    compare_mode: CompareMode


@dataclass(frozen=True)
class RunLimits:
    time_limit_ms: int
    memory_limit_mb: int
    cpus: Any
    pids_limit: Any
    max_output_bytes_per_test: int
    max_terminal_log_bytes: int


@dataclass(frozen=True)
class CompileResult:
    cmd: list[str]
    returncode: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True)
class CaseEvaluation:
    case: Case
    expected_present: bool
    verdict: str
    diff: dict[str, Any]


@dataclass(frozen=True)
class TestRecordData:
    evaluation: CaseEvaluation
    run_result: dict[str, Any]
    stdout_b64: str
    stderr_b64: str
    stdout_truncated: bool
    stderr_truncated: bool

