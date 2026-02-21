from __future__ import annotations

# Test report builders (runner_test).

import base64
from typing import Any

from runner_test_cases import compare_output
from runner_test_models import Case, CaseEvaluation, CompareMode, CompileResult, RunLimits, TestRecordData


MAX_STREAM_BYTES = 65536


def b64encode_ascii(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64_trunc(data: bytes, max_bytes: int = MAX_STREAM_BYTES) -> tuple[str, bool]:
    if len(data) > max_bytes:
        truncated = data[:max_bytes]
        return b64encode_ascii(truncated), True
    return b64encode_ascii(data), False


def init_report(
    *,
    job: dict[str, Any],
    attempt: int,
    tests_present: bool,
    compare_mode: CompareMode,
    limits: RunLimits,
    compile_result: CompileResult,
) -> dict[str, Any]:
    c_stdout_b64, c_stdout_tr = b64_trunc(compile_result.stdout)
    c_stderr_b64, c_stderr_tr = b64_trunc(compile_result.stderr)
    compile_ok = compile_result.returncode == 0

    job_get = job.get
    return {
        "schema_version": "report.v1",
        "job_id": str(job_get("job_id") or ""),
        "owner_user_id": str(job_get("owner_user_id") or ""),
        "status": "failed",
        "mode": "compile_only" if not tests_present else "compile_and_test",
        "environment": {
            "cpp_std": "c++20",
            "compare_mode": compare_mode,
            "time_limit_ms": limits.time_limit_ms,
            "memory_limit_mb": limits.memory_limit_mb,
            "cpus": limits.cpus,
            "pids_limit": limits.pids_limit,
            "max_output_bytes_per_test": limits.max_output_bytes_per_test,
        },
        "compile": {
            "cmd": " ".join(compile_result.cmd),
            "ok": compile_ok,
            "exit_code": int(compile_result.returncode),
            "stdout_b64": c_stdout_b64,
            "stderr_b64": c_stderr_b64,
            "stdout_truncated": c_stdout_tr,
            "stderr_truncated": c_stderr_tr,
        },
        "tests": [],
        "summary": {
            "total": 0,
            "judged": 0,
            "run_only": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "first_failure": None,
            "first_failure_verdict": None,
            "first_failure_message": None,
        },
        "error": None,
        "truncation": {"max_stream_bytes": MAX_STREAM_BYTES, "terminal_log_truncated": False},
    }


def add_skip_test_record(*, report: dict[str, Any], case: Case) -> None:
    report["tests"].append(
        {
            "name": case.name,
            "group": case.group,
            "input_rel": f"tests/{case.input_rel}",
            "expected_rel": f"tests/{case.expected_rel}" if case.expected_rel else None,
            "expected_present": False,
            "verdict": "SKIP",
            "exit_code": 0,
            "timeout": False,
            "output_limit_exceeded": False,
            "signal": None,
            "time_ms": 0,
            "memory_kb": None,
            "stdout_b64": "",
            "stderr_b64": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "diff": {"ok": True, "mode": case.compare_mode, "message": "", "expected_preview_b64": "", "actual_preview_b64": ""},
        }
    )


def build_diff_payload(*, expected_text: str, actual_text: str, compare_mode: CompareMode) -> tuple[str, dict[str, Any]]:
    ok, msg, expected_preview, actual_preview = compare_output(actual_text, expected_text, compare_mode)
    expected_preview_b64 = b64encode_ascii(expected_preview.encode("utf-8"))
    actual_preview_b64 = b64encode_ascii(actual_preview.encode("utf-8"))
    diff = {
        "ok": ok,
        "mode": compare_mode,
        "message": msg,
        "expected_preview_b64": expected_preview_b64,
        "actual_preview_b64": actual_preview_b64,
    }
    return ("AC" if ok else "WA"), diff


def update_summary_for_verdict(*, summary: dict[str, Any], evaluation: CaseEvaluation) -> None:
    verdict = evaluation.verdict
    if verdict not in ("AC", "WA", "RE", "TLE", "OLE"):
        summary["run_only"] += 1
        return

    summary["judged"] += 1 if evaluation.expected_present else 0
    if verdict == "AC":
        summary["passed"] += 1
        return

    summary["failed"] += 1
    summary_get = summary.get
    if summary_get("first_failure") is None:
        summary["first_failure"] = evaluation.case.name
        summary["first_failure_verdict"] = verdict
        diff_get = evaluation.diff.get
        summary["first_failure_message"] = diff_get("message") or verdict


def build_test_record(data: TestRecordData) -> dict[str, Any]:
    case = data.evaluation.case
    run_result_get = data.run_result.get
    return {
        "name": case.name,
        "group": case.group,
        "input_rel": f"tests/{case.input_rel}",
        "expected_rel": f"tests/{case.expected_rel}" if case.expected_rel else None,
        "expected_present": data.evaluation.expected_present,
        "verdict": data.evaluation.verdict,
        "exit_code": data.run_result["exit_code"],
        "timeout": data.run_result["timeout"],
        "output_limit_exceeded": data.run_result["output_limit_exceeded"],
        "signal": None,
        "time_ms": data.run_result["time_ms"],
        "memory_kb": run_result_get("memory_kb"),
        "stdout_b64": data.stdout_b64,
        "stderr_b64": data.stderr_b64,
        "stdout_truncated": data.stdout_truncated,
        "stderr_truncated": data.stderr_truncated,
        "diff": data.evaluation.diff,
    }
