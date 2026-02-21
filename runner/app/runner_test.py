from __future__ import annotations

# Local test runner invoked by the backend job manager.
#
# Responsibilities:
# - compile `output/main.cpp`
# - run against cases under `input/tests/`
# - write `output/artifacts/attempt_{ATTEMPT}/test_output/report.json`

import os
import subprocess
from pathlib import Path
from typing import Any

from runner_test_cases import load_cases, normalize_compare_mode
from runner_test_fs import job_path, prepare_dirs, read_text, write_json
from runner_test_models import CompileResult, RunLimits
from runner_test_report import init_report
from runner_test_run import run_cases
from runner_test_status import status_update


def ensure_runner_test_import_path() -> None:
    # Ensure child Python processes can import `realmoi_status_mcp` by module name.
    module_dir = str(Path(__file__).resolve().parent)
    current = str(os.environ.get("PYTHONPATH") or "")
    paths = [p for p in current.split(os.pathsep) if p]
    if module_dir in paths:
        return
    os.environ["PYTHONPATH"] = os.pathsep.join([module_dir, *paths]) if paths else module_dir


def parse_attempt_env() -> int:
    # Parse ATTEMPT from environment and normalize to >=1.
    try:
        attempt = int(os.environ.get("ATTEMPT") or 1)
    except Exception:
        attempt = 1
    if attempt < 1:
        attempt = 1
    os.environ["ATTEMPT"] = str(attempt)
    return attempt


def read_job() -> dict[str, Any]:
    raw = read_text(job_path("input", "job.json"))
    try:
        import json

        return json.loads(raw)
    except Exception as exc:
        raise RuntimeError(f"invalid_job_json:{exc}") from exc


def load_limits(job: dict[str, Any]) -> RunLimits:
    limits = job.get("limits") or {}
    return RunLimits(
        time_limit_ms=int(limits.get("time_limit_ms") or 2000),
        memory_limit_mb=int(limits.get("memory_limit_mb") or 512),
        cpus=limits.get("cpus") or 1,
        pids_limit=limits.get("pids_limit") or 256,
        max_output_bytes_per_test=int(limits.get("max_output_bytes_per_test") or 1_048_576),
        max_terminal_log_bytes=int(limits.get("max_terminal_log_bytes") or 5_242_880),
    )


def compile_cpp(*, src_cpp: Path, exe_path: Path) -> CompileResult:
    compile_cmd = ["g++", "-std=c++20", "-O2", "-pipe", str(src_cpp), "-o", str(exe_path)]
    try:
        cp = subprocess.run(compile_cmd, capture_output=True)
    except Exception as exc:
        raise RuntimeError(f"compile_cpp_failed:{type(exc).__name__}:{exc}") from exc
    return CompileResult(
        cmd=compile_cmd,
        returncode=int(cp.returncode),
        stdout=bytes(cp.stdout or b""),
        stderr=bytes(cp.stderr or b""),
    )


def get_tests_config(job: dict[str, Any]) -> tuple[bool, str, bool, Path]:
    tests = job.get("tests") or {}
    tests_present = bool(tests.get("present"))
    compare_mode = normalize_compare_mode(
        str((tests.get("compare") or {}).get("mode") or "tokens"),
        default="tokens",
    )
    run_if_no_expected = bool(tests.get("run_if_no_expected", True))
    tests_dir = job_path("input") / str(tests.get("dir") or "tests")
    return tests_present, compare_mode, run_if_no_expected, tests_dir


def write_report(*, out_root: Path, report: dict[str, Any]) -> None:
    write_json(out_root / "report.json", report)


def finish_compile_failed(*, out_root: Path, report: dict[str, Any], returncode: int) -> int:
    status_update(stage="repair", summary=f"编译失败：exit={returncode}", level="error", progress=100)
    report["status"] = "failed"
    report["error"] = {"code": "compile_error", "message": "Compile failed"}
    write_report(out_root=out_root, report=report)
    return 1


def finish_no_tests(*, out_root: Path, report: dict[str, Any]) -> int:
    status_update(stage="done", summary="编译通过（无 tests）", progress=100)
    report["status"] = "succeeded"
    write_report(out_root=out_root, report=report)
    return 0


def finish_tests_done(*, out_root: Path, report: dict[str, Any]) -> int:
    summary = report["summary"]
    report["status"] = "succeeded" if summary["failed"] == 0 else "failed"
    if report["status"] != "succeeded":
        report["error"] = {"code": "tests_failed", "message": "Tests failed"}

    if report["status"] == "succeeded":
        status_update(stage="done", summary=f"测试通过：passed={summary['passed']} failed=0", progress=100)
    else:
        verdict = str(summary.get("first_failure_verdict") or "")
        case = str(summary.get("first_failure") or "")
        msg_ = str(summary.get("first_failure_message") or "")
        bits = [x for x in (verdict, case, msg_) if x]
        detail = " ".join(bits)
        if detail:
            detail = "：" + detail
        status_update(
            stage="repair",
            summary=f"测试未通过（failed={summary['failed']}）{detail}",
            level="warn",
            progress=100,
        )

    write_report(out_root=out_root, report=report)
    return 0 if report["status"] == "succeeded" else 1


def main() -> int:
    ensure_runner_test_import_path()
    job = read_job()
    attempt = parse_attempt_env()
    limits = load_limits(job)

    tests_present, compare_mode, run_if_no_expected, tests_dir = get_tests_config(job)

    out_root, work_dir = prepare_dirs(attempt=attempt)

    src_cpp = job_path("output", "main.cpp")
    exe_path = work_dir / "prog"

    status_update(stage="test", summary="开始测试", progress=0)
    status_update(stage="test", summary="编译中", progress=5)
    compile_result = compile_cpp(src_cpp=src_cpp, exe_path=exe_path)
    report: dict[str, Any] = init_report(
        job=job,
        attempt=attempt,
        tests_present=tests_present,
        compare_mode=compare_mode,
        limits=limits,
        compile_result=compile_result,
    )

    if compile_result.returncode != 0:
        return finish_compile_failed(out_root=out_root, report=report, returncode=int(compile_result.returncode))

    if not tests_present:
        return finish_no_tests(out_root=out_root, report=report)

    cases = load_cases(job)
    run_cases(
        report=report,
        cases=cases,
        tests_dir=tests_dir,
        exe_path=exe_path,
        limits=limits,
        run_if_no_expected=run_if_no_expected,
    )
    return finish_tests_done(out_root=out_root, report=report)


if __name__ == "__main__":
    raise SystemExit(main())
