from __future__ import annotations

import atexit
import base64
import json
import os
import selectors
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

try:
    from realmoi_mcp_client import McpClientError, McpStdioClient
except ModuleNotFoundError:  # pragma: no cover
    from runner.app.realmoi_mcp_client import McpClientError, McpStdioClient  # type: ignore


MAX_STREAM_BYTES = 65536
JOB_DIR = Path(os.environ.get("REALMOI_JOB_DIR") or "/job")
WORK_DIR = Path(os.environ.get("REALMOI_WORK_DIR") or "/tmp/work")


def job_path(*parts: str) -> Path:
    return JOB_DIR.joinpath(*parts)


def ensure_runner_test_import_path() -> None:
    """Ensure child Python processes can import ``realmoi_status_mcp`` by module name."""

    module_dir = str(Path(__file__).resolve().parent)
    current = str(os.environ.get("PYTHONPATH") or "")
    paths = [p for p in current.split(os.pathsep) if p]
    if module_dir in paths:
        return
    os.environ["PYTHONPATH"] = os.pathsep.join([module_dir, *paths]) if paths else module_dir


_MCP_CLIENT: McpStdioClient | None = None
_MCP_DISABLED: bool = False
_STATUS_LAST_SIG: tuple[str, str] | None = None
_STATUS_LAST_TS: float = 0.0


def _close_mcp_client() -> None:
    global _MCP_CLIENT
    if _MCP_CLIENT is None:
        return
    try:
        _MCP_CLIENT.close()
    except Exception:
        pass
    _MCP_CLIENT = None


atexit.register(_close_mcp_client)


def _get_mcp_client() -> McpStdioClient | None:
    global _MCP_CLIENT, _MCP_DISABLED
    if _MCP_DISABLED:
        return None
    if _MCP_CLIENT is not None:
        return _MCP_CLIENT
    try:
        _MCP_CLIENT = McpStdioClient(module_name="realmoi_status_mcp", env=os.environ.copy())
        return _MCP_CLIENT
    except (McpClientError, OSError, ValueError):
        _MCP_DISABLED = True
        return None


def status_update(*, stage: str, summary: str, level: str = "info", progress: int | None = None) -> None:
    global _STATUS_LAST_SIG, _STATUS_LAST_TS

    stage = str(stage or "").strip() or "test"
    summary = str(summary or "").strip()
    if len(summary) > 200:
        summary = summary[:200]

    sig = (stage, summary)
    now = time.time()
    if _STATUS_LAST_SIG == sig and now - _STATUS_LAST_TS < 1.0:
        return
    _STATUS_LAST_SIG = sig
    _STATUS_LAST_TS = now

    client = _get_mcp_client()
    if client is None:
        return

    args: dict[str, Any] = {
        "stage": stage,
        "summary": summary,
        "level": level,
        "attempt": int(os.environ.get("ATTEMPT") or 1),
    }
    if progress is not None:
        args["progress"] = progress
    try:
        client.call_tool(name="status.update", arguments=args)
    except Exception:
        return


def b64_trunc(data: bytes, max_bytes: int = MAX_STREAM_BYTES) -> tuple[str, bool]:
    if len(data) > max_bytes:
        return base64.b64encode(data[:max_bytes]).decode("ascii"), True
    return base64.b64encode(data).decode("ascii"), False


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_job() -> dict[str, Any]:
    return json.loads(job_path("input", "job.json").read_text(encoding="utf-8"))


def normalize_tokens(s: str) -> list[str]:
    return s.split()


def normalize_trim_ws(s: str) -> str:
    lines = [line.rstrip() for line in s.replace("\r\n", "\n").split("\n")]
    return "\n".join(lines).rstrip("\n") + "\n"


def compare_output(actual: str, expected: str, mode: Literal["tokens", "trim_ws", "exact"]) -> tuple[bool, str, str, str]:
    if mode == "exact":
        ok = actual == expected
        if ok:
            return True, "", expected[:200], actual[:200]
        return False, "exact mismatch", expected[:200], actual[:200]
    if mode == "trim_ws":
        a = normalize_trim_ws(actual)
        e = normalize_trim_ws(expected)
        ok = a == e
        if ok:
            return True, "", e[:200], a[:200]
        return False, "trim_ws mismatch", e[:200], a[:200]
    # tokens
    a_tokens = normalize_tokens(actual)
    e_tokens = normalize_tokens(expected)
    if a_tokens == e_tokens:
        return True, "", " ".join(e_tokens[:50]), " ".join(a_tokens[:50])
    # find first mismatch
    n = min(len(a_tokens), len(e_tokens))
    idx = next((i for i in range(n) if a_tokens[i] != e_tokens[i]), n)
    return (
        False,
        f"tokens mismatch at {idx}: expected={e_tokens[idx] if idx < len(e_tokens) else '<eof>'} actual={a_tokens[idx] if idx < len(a_tokens) else '<eof>'}",
        " ".join(e_tokens[max(0, idx - 10) : idx + 10]),
        " ".join(a_tokens[max(0, idx - 10) : idx + 10]),
    )


@dataclass(frozen=True)
class Case:
    name: str
    group: str
    input_rel: str
    expected_rel: str | None
    compare_mode: Literal["tokens", "trim_ws", "exact"]


def load_cases(job: dict[str, Any]) -> list[Case]:
    tests = job.get("tests") or {}
    tests_dir = job_path("input") / str(tests.get("dir") or "tests")
    fmt = str(tests.get("format") or "auto")
    compare_mode = str((tests.get("compare") or {}).get("mode") or "tokens")

    manifest_path = tests_dir / "manifest.json"
    if fmt in ("auto", "manifest") and manifest_path.exists():
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        cases = []
        for c in m.get("cases") or []:
            name = str(c.get("name") or "")
            group = str(c.get("group") or "default")
            inp = str(c.get("in") or "")
            out = c.get("out")
            cm = str(c.get("compare_mode") or m.get("compare_mode") or compare_mode)
            cases.append(Case(name=name, group=group, input_rel=inp, expected_rel=str(out) if out else None, compare_mode=cm))  # type: ignore[arg-type]
        return cases

    # in_out_pairs
    cases: list[Case] = []
    if not tests_dir.exists():
        return cases

    # group by subdir if any
    has_subdir = any(p.is_dir() for p in tests_dir.iterdir())
    for root, _dirs, files in os.walk(tests_dir):
        root_p = Path(root)
        group = root_p.relative_to(tests_dir).parts[0] if has_subdir and root_p != tests_dir else "default"
        for fn in files:
            if not fn.endswith(".in"):
                continue
            in_path = root_p / fn
            rel_in = str(in_path.relative_to(tests_dir))
            base = fn[: -len(".in")]
            out_path = root_p / f"{base}.out"
            rel_out = str(out_path.relative_to(tests_dir)) if out_path.exists() else None
            cases.append(Case(name=base, group=group, input_rel=rel_in, expected_rel=rel_out, compare_mode=compare_mode))  # type: ignore[arg-type]

    cases.sort(key=lambda c: (c.group, c.name))
    return cases


def run_program(
    *,
    exe_path: Path,
    input_bytes: bytes,
    time_limit_ms: int,
    output_limit_bytes: int,
) -> dict[str, Any]:
    def preexec() -> None:
        os.setsid()

    start = time.monotonic()
    proc = subprocess.Popen(
        [str(exe_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(WORK_DIR),
        preexec_fn=preexec,
    )
    assert proc.stdin and proc.stdout and proc.stderr
    proc.stdin.write(input_bytes)
    proc.stdin.close()

    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ, data="stdout")
    sel.register(proc.stderr, selectors.EVENT_READ, data="stderr")

    stdout = bytearray()
    stderr = bytearray()
    timeout = False
    output_limit_exceeded = False

    deadline = start + (time_limit_ms / 1000.0)
    while True:
        now = time.monotonic()
        if now >= deadline and proc.poll() is None:
            timeout = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                proc.kill()
            break

        events = sel.select(timeout=0.05)
        for key, _mask in events:
            stream = key.data
            data = key.fileobj.read1(4096)  # type: ignore[attr-defined]
            if not data:
                sel.unregister(key.fileobj)
                continue
            if stream == "stdout":
                stdout.extend(data)
            else:
                stderr.extend(data)

            if len(stdout) + len(stderr) > output_limit_bytes and proc.poll() is None:
                output_limit_exceeded = True
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    proc.kill()
                break

        if proc.poll() is not None and not sel.get_map():
            break

    end = time.monotonic()
    exit_code = proc.wait(timeout=1)
    return {
        "exit_code": int(exit_code),
        "timeout": timeout,
        "output_limit_exceeded": output_limit_exceeded,
        "time_ms": int((end - start) * 1000),
        "stdout": bytes(stdout),
        "stderr": bytes(stderr),
    }


def main() -> int:
    ensure_runner_test_import_path()
    job = read_job()
    try:
        attempt = int(os.environ.get("ATTEMPT") or 1)
    except Exception:
        attempt = 1
    if attempt < 1:
        attempt = 1
    os.environ["ATTEMPT"] = str(attempt)

    limits = job.get("limits") or {}
    time_limit_ms = int(limits.get("time_limit_ms") or 2000)
    memory_limit_mb = int(limits.get("memory_limit_mb") or 512)
    cpus = limits.get("cpus") or 1
    pids_limit = limits.get("pids_limit") or 256
    max_output_bytes_per_test = int(limits.get("max_output_bytes_per_test") or 1_048_576)
    max_terminal_log_bytes = int(limits.get("max_terminal_log_bytes") or 5_242_880)

    tests_present = bool((job.get("tests") or {}).get("present"))
    compare_mode = str(((job.get("tests") or {}).get("compare") or {}).get("mode") or "tokens")
    run_if_no_expected = bool((job.get("tests") or {}).get("run_if_no_expected", True))

    out_root = job_path("output") / "artifacts" / f"attempt_{attempt}" / "test_output"
    work_dir = WORK_DIR
    shutil.rmtree(out_root, ignore_errors=True)
    shutil.rmtree(work_dir, ignore_errors=True)
    out_root.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    src_cpp = job_path("output", "main.cpp")
    exe_path = work_dir / "prog"

    status_update(stage="test", summary="开始测试", progress=0)

    compile_cmd = ["g++", "-std=c++20", "-O2", "-pipe", str(src_cpp), "-o", str(exe_path)]
    status_update(stage="test", summary="编译中", progress=5)
    cp = subprocess.run(compile_cmd, capture_output=True)
    c_stdout = cp.stdout
    c_stderr = cp.stderr
    c_stdout_b64, c_stdout_tr = b64_trunc(c_stdout)
    c_stderr_b64, c_stderr_tr = b64_trunc(c_stderr)

    compile_ok = cp.returncode == 0

    report: dict[str, Any] = {
        "schema_version": "report.v1",
        "job_id": str(job.get("job_id") or ""),
        "owner_user_id": str(job.get("owner_user_id") or ""),
        "status": "failed",
        "mode": "compile_only" if not tests_present else "compile_and_test",
        "environment": {
            "cpp_std": "c++20",
            "compare_mode": compare_mode,
            "time_limit_ms": time_limit_ms,
            "memory_limit_mb": memory_limit_mb,
            "cpus": cpus,
            "pids_limit": pids_limit,
            "max_output_bytes_per_test": max_output_bytes_per_test,
        },
        "compile": {
            "cmd": " ".join(compile_cmd),
            "ok": compile_ok,
            "exit_code": int(cp.returncode),
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

    if not compile_ok:
        status_update(stage="repair", summary=f"编译失败：exit={cp.returncode}", level="error", progress=100)
        report["status"] = "failed"
        report["error"] = {"code": "compile_error", "message": "Compile failed"}
        write_json(out_root / "report.json", report)
        return 1

    if not tests_present:
        status_update(stage="done", summary="编译通过（无 tests）", progress=100)
        report["status"] = "succeeded"
        write_json(out_root / "report.json", report)
        return 0

    cases = load_cases(job)
    tests_dir = job_path("input") / str((job.get("tests") or {}).get("dir") or "tests")

    summary = report["summary"]
    summary["total"] = len(cases)

    total = len(cases)
    status_update(stage="test", summary=f"开始执行测试（{total} case）", progress=10)
    update_every = max(1, total // 10) if total else 1
    last_progress: int | None = None

    for idx, c in enumerate(cases, start=1):
        if total and (idx == 1 or idx == total or idx % update_every == 0):
            progress = 10 + int((80 * idx) / total)
            if progress != last_progress:
                status_update(stage="test", summary=f"测试进度：{idx}/{total}", progress=progress)
                last_progress = progress

        in_path = tests_dir / c.input_rel
        input_bytes = in_path.read_bytes()

        expected_present = c.expected_rel is not None and (tests_dir / c.expected_rel).exists()
        if not expected_present and not run_if_no_expected:
            report["tests"].append(
                {
                    "name": c.name,
                    "group": c.group,
                    "input_rel": f"tests/{c.input_rel}",
                    "expected_rel": f"tests/{c.expected_rel}" if c.expected_rel else None,
                    "expected_present": False,
                    "verdict": "SKIP",
                    "exit_code": 0,
                    "timeout": False,
                    "output_limit_exceeded": False,
                    "signal": None,
                    "time_ms": 0,
                    "stdout_b64": "",
                    "stderr_b64": "",
                    "stdout_truncated": False,
                    "stderr_truncated": False,
                    "diff": {"ok": True, "mode": c.compare_mode, "message": "", "expected_preview_b64": "", "actual_preview_b64": ""},
                }
            )
            summary["skipped"] += 1
            continue

        r = run_program(
            exe_path=exe_path,
            input_bytes=input_bytes,
            time_limit_ms=time_limit_ms,
            output_limit_bytes=max_output_bytes_per_test,
        )
        stdout_b64, stdout_tr = b64_trunc(r["stdout"])
        stderr_b64, stderr_tr = b64_trunc(r["stderr"])

        verdict = "RUN"
        diff = {"ok": True, "mode": c.compare_mode, "message": "", "expected_preview_b64": "", "actual_preview_b64": ""}

        if r["timeout"]:
            verdict = "TLE"
        elif r["output_limit_exceeded"]:
            verdict = "OLE"
        elif r["exit_code"] != 0:
            verdict = "RE"
        elif expected_present:
            expected_text = (tests_dir / c.expected_rel).read_text(encoding="utf-8", errors="ignore")  # type: ignore[arg-type]
            actual_text = r["stdout"].decode("utf-8", errors="ignore")
            ok, msg, e_prev, a_prev = compare_output(actual_text, expected_text, c.compare_mode)
            verdict = "AC" if ok else "WA"
            diff = {
                "ok": ok,
                "mode": c.compare_mode,
                "message": msg,
                "expected_preview_b64": base64.b64encode(e_prev.encode("utf-8")).decode("ascii"),
                "actual_preview_b64": base64.b64encode(a_prev.encode("utf-8")).decode("ascii"),
            }

        if verdict in ("AC", "WA", "RE", "TLE", "OLE"):
            summary["judged"] += 1 if expected_present else 0
            if verdict == "AC":
                summary["passed"] += 1
            elif verdict in ("WA", "RE", "TLE", "OLE"):
                summary["failed"] += 1
                if summary["first_failure"] is None:
                    summary["first_failure"] = c.name
                    summary["first_failure_verdict"] = verdict
                    summary["first_failure_message"] = diff.get("message") or verdict
        else:
            summary["run_only"] += 1

        report["tests"].append(
            {
                "name": c.name,
                "group": c.group,
                "input_rel": f"tests/{c.input_rel}",
                "expected_rel": f"tests/{c.expected_rel}" if c.expected_rel else None,
                "expected_present": expected_present,
                "verdict": verdict,
                "exit_code": r["exit_code"],
                "timeout": r["timeout"],
                "output_limit_exceeded": r["output_limit_exceeded"],
                "signal": None,
                "time_ms": r["time_ms"],
                "stdout_b64": stdout_b64,
                "stderr_b64": stderr_b64,
                "stdout_truncated": stdout_tr,
                "stderr_truncated": stderr_tr,
                "diff": diff,
            }
        )

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

    write_json(out_root / "report.json", report)
    return 0 if report["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
