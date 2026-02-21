from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from runner_program import run_program
except ModuleNotFoundError:  # pragma: no cover
    from runner.app.runner_program import run_program
from runner_test_fs import WORK_DIR, read_bytes, read_text
from runner_test_models import Case, CaseEvaluation, RunLimits, TestRecordData
from runner_test_report import add_skip_test_record, b64_trunc, build_diff_payload, build_test_record, update_summary_for_verdict
from runner_test_status import status_update


def should_emit_progress(*, idx: int, total: int, update_every: int) -> bool:
    if total <= 0:
        return False
    if idx == 1 or idx == total:
        return True
    return idx % max(1, update_every) == 0


def resolve_expected(*, tests_dir: Path, case: Case) -> tuple[bool, str]:
    if case.expected_rel is None:
        return False, ""
    expected_path = tests_dir / case.expected_rel
    if not expected_path.exists():
        return False, ""
    return True, read_text(expected_path, errors="replace")


def run_cases(
    *,
    report: dict[str, Any],
    cases: list[Case],
    tests_dir: Path,
    exe_path: Path,
    limits: RunLimits,
    run_if_no_expected: bool,
) -> None:
    # Run all test cases and mutate report in-place.

    summary = report["summary"]
    summary["total"] = len(cases)

    total = len(cases)
    status_update(stage="test", summary=f"开始执行测试（{total} case）", progress=10)
    update_every = max(1, total // 10) if total else 1
    last_progress: int | None = None

    for idx, case in enumerate(cases, start=1):
        if should_emit_progress(idx=idx, total=total, update_every=update_every):
            progress = 10 + int((80 * idx) / total)
            if progress != last_progress:
                status_update(stage="test", summary=f"测试进度：{idx}/{total}", progress=progress)
                last_progress = progress

        input_bytes = read_bytes(tests_dir / case.input_rel)
        expected_present, expected_text = resolve_expected(tests_dir=tests_dir, case=case)
        if not expected_present and not run_if_no_expected:
            add_skip_test_record(report=report, case=case)
            summary["skipped"] += 1
            continue

        run_result = run_program(
            exe_path=exe_path,
            input_bytes=input_bytes,
            time_limit_ms=limits.time_limit_ms,
            output_limit_bytes=limits.max_output_bytes_per_test,
            work_dir=WORK_DIR,
        )
        stdout_b64, stdout_truncated = b64_trunc(run_result["stdout"])
        stderr_b64, stderr_truncated = b64_trunc(run_result["stderr"])

        verdict = "RUN"
        diff: dict[str, Any] = {"ok": True, "mode": case.compare_mode, "message": "", "expected_preview_b64": "", "actual_preview_b64": ""}
        if run_result["timeout"]:
            verdict = "TLE"
        elif run_result["output_limit_exceeded"]:
            verdict = "OLE"
        elif run_result["exit_code"] != 0:
            verdict = "RE"
        elif expected_present:
            actual_text = run_result["stdout"].decode("utf-8", errors="replace")
            verdict, diff = build_diff_payload(expected_text=expected_text, actual_text=actual_text, compare_mode=case.compare_mode)

        evaluation = CaseEvaluation(case=case, expected_present=expected_present, verdict=verdict, diff=diff)
        update_summary_for_verdict(summary=summary, evaluation=evaluation)
        report["tests"].append(
            build_test_record(
                TestRecordData(
                    evaluation=evaluation,
                    run_result=run_result,
                    stdout_b64=stdout_b64,
                    stderr_b64=stderr_b64,
                    stdout_truncated=stdout_truncated,
                    stderr_truncated=stderr_truncated,
                )
            )
        )
