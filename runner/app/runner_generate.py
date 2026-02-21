from __future__ import annotations

# Codex 代码生成 runner。
#
# 职责：
# - 读取 job/state 输入
# - 组装 generate/repair prompt
# - 调用 Codex（优先 app-server，失败回退 exec）
# - 写出 main.cpp / solution.json / usage.json 与 attempt artifacts
#
# 调试日志默认关闭；设置环境变量 `REALMOI_GENERATE_DEBUG=1` 可输出额外异常上下文。

# Codex generate runner entrypoint.
#
# 说明：
# - 读取 job.json / state.json 等输入
# - 生成 prompt（首次 generate；失败后 repair）
# - 调用 codex（优先 app-server；失败回退 exec）
# - 输出 main.cpp / solution.json / usage.json 及 attempt_* artifacts

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

MODULE_DIR = str(Path(__file__).resolve().parent)
if MODULE_DIR not in sys.path:
    # Ensure imports work both when executed as a script and when imported as a module.
    sys.path.insert(0, MODULE_DIR)

from runner_generate_codex_appserver import CodexAppserverArtifacts, run_codex_appserver
from runner_generate_codex_exec import CodexExecArtifacts, run_codex_exec
from runner_generate_io import build_full_unified_diff, ensure_dir, job_path, read_job, write_json, write_text
from runner_generate_prompt import (
    build_prompt_generate,
    build_prompt_repair,
    maybe_set_openai_api_key_from_auth_json,
    normalize_reasoning_effort,
    summarize_report,
)
from runner_generate_status import status_update
from runner_generate_text import extract_cpp_code_block
from runner_generate_usage import parse_usage


SCHEMA_PATH = Path(os.environ.get("REALMOI_SCHEMA_PATH") or "/app/schemas/codex_output_schema.json")

# ----------------------------
# Debug / IO helpers
# ----------------------------

def debug_enabled() -> bool:
    return os.environ.get("REALMOI_GENERATE_DEBUG") == "1"


def note_exception(context: str, exc: BaseException) -> None:
    if not debug_enabled():
        return
    print(f"[generate][debug] {context}: {exc}", flush=True)


def read_text_utf8_best_effort(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError as exc:
        note_exception(f"read bytes: {path}", exc)
        raise
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        note_exception(f"decode utf-8: {path}", exc)
        return data.decode("utf-8", errors="replace")

# ----------------------------
# In-memory payloads
# ----------------------------

@dataclass(frozen=True)
class CodexCallSuccess:
    # 该次尝试内的 Codex 调用序号（从 1 开始）。
    call_index: int
    jsonl_path: Path
    last_message_path: Path
    response_obj: dict[str, Any]
    main_cpp: str


@dataclass(frozen=True)
class CodexInvocation:
    prompt: str
    model: str
    search_mode: Literal["disabled", "cached", "live"]
    reasoning_effort: str
    schema_path: Path
    jsonl_path: Path
    last_message_path: Path


@dataclass(frozen=True)
class CodexRetryRequest:
    """Inputs for one generate/repair attempt (may involve multiple Codex calls)."""

    attempt_dir: Path
    prompt: str
    prompt_mode: str
    model: str
    search_mode: Literal["disabled", "cached", "live"]
    reasoning_effort: str
    schema_path: Path

# ----------------------------
# Codex invocation + retry strategy
# ----------------------------

def ensure_runner_generate_import_path() -> None:
    """Ensure child Python processes can import ``runner_generate`` by module name."""

    module_dir = str(Path(__file__).resolve().parent)
    current = str(os.environ.get("PYTHONPATH") or "")
    paths = [p for p in current.split(os.pathsep) if p]
    if module_dir in paths:
        return
    os.environ["PYTHONPATH"] = os.pathsep.join([module_dir, *paths]) if paths else module_dir


def run_codex(invocation: CodexInvocation) -> int:
    """Run Codex once using the preferred transport (appserver or exec)."""
    artifacts = CodexExecArtifacts(
        schema_path=invocation.schema_path,
        jsonl_path=invocation.jsonl_path,
        last_message_path=invocation.last_message_path,
    )
    appserver_artifacts = CodexAppserverArtifacts(
        schema_path=invocation.schema_path,
        jsonl_path=invocation.jsonl_path,
        last_message_path=invocation.last_message_path,
    )
    transport = str(os.environ.get("REALMOI_CODEX_TRANSPORT") or "appserver").strip().lower()
    prefer_appserver = transport in ("appserver", "auto", "")

    if prefer_appserver:
        try:
            return run_codex_appserver(
                prompt=invocation.prompt,
                model=invocation.model,
                search_mode=invocation.search_mode,
                reasoning_effort=invocation.reasoning_effort,
                artifacts=appserver_artifacts,
            )
        except Exception as exc:
            note_exception("run_codex_appserver failed", exc)
            print(f"[generate] appserver failed, fallback to exec: {exc}", flush=True)
            if transport == "appserver":
                return run_codex_exec(
                    prompt=invocation.prompt,
                    model=invocation.model,
                    search_mode=invocation.search_mode,
                    reasoning_effort=invocation.reasoning_effort,
                    artifacts=artifacts,
                )

    return run_codex_exec(
        prompt=invocation.prompt,
        model=invocation.model,
        search_mode=invocation.search_mode,
        reasoning_effort=invocation.reasoning_effort,
        artifacts=artifacts,
    )

# ----------------------------
# Output writers
# ----------------------------

def write_mock_outputs(*, job: dict[str, Any], out_dir: Path, attempt_dir: Path, model: str) -> None:
    """Write placeholder outputs when MOCK_MODE=1 (used by CI smoke checks)."""
    job_id = str(job.get("job_id") or "")
    main_cpp = (
        "#include <bits/stdc++.h>\n"
        "using namespace std;\n"
        "int main(){ios::sync_with_stdio(false);cin.tie(nullptr);return 0;}\n"
    )
    write_text(out_dir / "main.cpp", main_cpp + "\n")
    write_text(attempt_dir / "main.cpp", main_cpp + "\n")
    seed_code_present = bool(str(job.get("seed", {}).get("current_code_cpp") or "").strip())
    issue_type = "minor_bug" if seed_code_present else "no_seed_code"
    wrong_lines = [1] if seed_code_present else []
    diff = (
        "diff --git a/main.cpp b/main.cpp\n"
        "--- a/main.cpp\n"
        "+++ b/main.cpp\n"
        "@@\n"
        "-// MOCK_MODE: placeholder\n"
        "+// MOCK_MODE: placeholder (fixed)\n"
    ) if seed_code_present else ""
    user_feedback = (
        "（MOCK_MODE）示例反馈：你的总体思路是对的，但有一处小错误。\n"
        "- 错误行：第 1 行（示例）\n"
        "- 修复方式：见下方 diff（示例）\n"
    ) if seed_code_present else ""
    solution_payload = {
        "schema_version": "solution.v1",
        "job_id": job_id,
        "solution_idea": "mock",
        "seed_code_idea": "mock",
        "seed_code_bug_reason": "mock",
        "user_feedback_md": user_feedback,
        "seed_code_issue_type": issue_type,
        "seed_code_wrong_lines": wrong_lines,
        "seed_code_fix_diff": diff,
        "assumptions": [],
        "complexity": "",
    }
    write_json(out_dir / "solution.json", solution_payload)
    write_json(attempt_dir / "solution.json", solution_payload)
    write_json(
        attempt_dir / "usage.json",
        {
            "schema_version": "usage.v1",
            "job_id": job_id,
            "codex_thread_id": "",
            "model": model,
            "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "cached_output_tokens": 0},
        },
    )
    write_json(out_dir / "usage.json", json.loads((attempt_dir / "usage.json").read_text(encoding="utf-8")))


def build_prompt(*, job: dict[str, Any], prompt_mode: str) -> str:
    """Build the generate/repair prompt for the current attempt."""
    if prompt_mode != "repair":
        return build_prompt_generate(job)

    report_path = job_path("output", "report.json")
    current_main_cpp = (
        job_path("output", "main.cpp").read_text(encoding="utf-8") if job_path("output", "main.cpp").exists() else ""
    )
    return build_prompt_repair(job, summarize_report(report_path), current_main_cpp)


def parse_last_message(raw: str) -> dict[str, Any] | None:
    """Parse Codex last-message payload; supports JSON object or a C++ code block fallback."""
    try:
        message_obj = json.loads(raw)
        return message_obj if isinstance(message_obj, dict) else None
    except ValueError as exc:
        note_exception("parse_last_message json", exc)
        code = extract_cpp_code_block(raw)
        if not code:
            return None
        return {"main_cpp": code}


def call_codex_once(
    *,
    call_index: int,
    invocation: CodexInvocation,
) -> CodexCallSuccess | None:
    """Run Codex once and parse a valid `main_cpp` out of the last message."""
    return_code = run_codex(invocation)
    if return_code != 0:
        return None

    try:
        raw = read_text_utf8_best_effort(invocation.last_message_path).strip()
    except OSError as exc:
        note_exception("read last_message_path", exc)
        return None

    message_obj = parse_last_message(raw)
    if not message_obj:
        return None
    main_cpp_raw = message_obj.get("main_cpp")
    if not isinstance(main_cpp_raw, str) or not main_cpp_raw.strip():
        return None

    main_cpp = main_cpp_raw.rstrip() + "\n"
    return CodexCallSuccess(
        call_index=call_index,
        jsonl_path=invocation.jsonl_path,
        last_message_path=invocation.last_message_path,
        response_obj=message_obj,
        main_cpp=main_cpp,
    )


def run_codex_with_retries(*, request: CodexRetryRequest) -> CodexCallSuccess | None:
    """Run Codex with infra retries + format retries, returning the first valid `main_cpp`."""
    infra_retries = [2, 5, 10]
    format_retries = 2

    call_index = 0
    for infra_retry_idx in range(len(infra_retries) + 1):
        if infra_retry_idx > 0:
            wait_s = infra_retries[infra_retry_idx - 1]
            print(f"[generate] infra retry {infra_retry_idx} after {wait_s}s")
            time.sleep(wait_s)

        for format_retry_idx in range(format_retries + 1):
            call_index += 1
            jsonl_path = request.attempt_dir / f"codex_call_{call_index}.jsonl"
            last_message_path = request.attempt_dir / f"last_message_call_{call_index}.json"

            status_update(
                stage="coding" if request.prompt_mode != "repair" else "repair",
                summary=f"调用 Codex（call {call_index}）",
            )
            prompt_used = (
                request.prompt
                if format_retry_idx == 0
                else request.prompt
                + "\n\n重试要求：你上一次输出不符合规范。现在只输出一个 JSON 对象，且必须包含非空字符串字段 main_cpp。"
            )
            invocation = CodexInvocation(
                prompt=prompt_used,
                model=request.model,
                search_mode=request.search_mode,
                reasoning_effort=request.reasoning_effort,
                schema_path=request.schema_path,
                jsonl_path=jsonl_path,
                last_message_path=last_message_path,
            )
            success = call_codex_once(
                call_index=call_index,
                invocation=invocation,
            )
            if success is not None:
                return success
    return None


def write_success_outputs(
    *,
    job: dict[str, Any],
    out_dir: Path,
    attempt_dir: Path,
    model: str,
    success: CodexCallSuccess,
) -> None:
    """Write `main.cpp`, `solution.json`, `usage.json`, and attempt artifacts for a successful run."""
    write_main_cpp(out_dir=out_dir, attempt_dir=attempt_dir, main_cpp=success.main_cpp)
    solution_payload = build_solution_payload(job=job, job_id=str(job.get("job_id") or ""), success=success)
    write_solution(out_dir=out_dir, attempt_dir=attempt_dir, solution_payload=solution_payload)
    usage_output = build_usage_output(job_id=str(job.get("job_id") or ""), model=model, jsonl_path=success.jsonl_path)
    write_usage(out_dir=out_dir, attempt_dir=attempt_dir, usage_output=usage_output)
    write_codex_artifacts(
        attempt_dir=attempt_dir,
        jsonl_path=success.jsonl_path,
        last_message_path=success.last_message_path,
    )


def write_main_cpp(*, out_dir: Path, attempt_dir: Path, main_cpp: str) -> None:
    write_text(out_dir / "main.cpp", main_cpp)
    write_text(attempt_dir / "main.cpp", main_cpp)


def coerce_positive_int_list(values: list[Any]) -> list[int]:
    result: list[int] = []
    for value in values:
        text = str(value).strip()
        if not text.isdigit():
            continue
        number = int(text)
        if number <= 0:
            continue
        result.append(number)
    return result


def build_solution_payload(*, job: dict[str, Any], job_id: str, success: CodexCallSuccess) -> dict[str, Any]:
    job_id = str(job.get("job_id") or "")
    solution_idea = str(success.response_obj.get("solution_idea") or "")
    seed_code_idea = str(success.response_obj.get("seed_code_idea") or "")
    seed_code_bug_reason = str(success.response_obj.get("seed_code_bug_reason") or "")
    user_feedback_md = str(success.response_obj.get("user_feedback_md") or "")
    seed_code_issue_type = str(success.response_obj.get("seed_code_issue_type") or "")
    seed_code_fix_diff = str(success.response_obj.get("seed_code_fix_diff") or "")
    assumptions = (
        success.response_obj.get("assumptions") if isinstance(success.response_obj.get("assumptions"), list) else []
    )
    complexity = str(success.response_obj.get("complexity") or "")
    wrong_lines_raw = success.response_obj.get("seed_code_wrong_lines")
    wrong_lines_list = wrong_lines_raw if isinstance(wrong_lines_raw, list) else []

    seed_code_cpp = str(job.get("seed", {}).get("current_code_cpp") or "")
    seed_code_full_diff = build_full_unified_diff(
        old_text=seed_code_cpp,
        new_text=success.main_cpp,
        fromfile="a/main.cpp",
        tofile="b/main.cpp",
    )
    solution_payload = {
        "schema_version": "solution.v1",
        "job_id": job_id,
        "solution_idea": solution_idea,
        "seed_code_idea": seed_code_idea,
        "seed_code_bug_reason": seed_code_bug_reason,
        "user_feedback_md": user_feedback_md,
        "seed_code_issue_type": seed_code_issue_type,
        "seed_code_wrong_lines": coerce_positive_int_list(wrong_lines_list),
        "seed_code_fix_diff": seed_code_fix_diff,
        "seed_code_full_diff": seed_code_full_diff,
        "assumptions": assumptions,
        "complexity": complexity,
    }
    return solution_payload


def write_solution(*, out_dir: Path, attempt_dir: Path, solution_payload: dict[str, Any]) -> None:
    write_json(out_dir / "solution.json", solution_payload)
    write_json(attempt_dir / "solution.json", solution_payload)


def build_usage_output(*, job_id: str, model: str, jsonl_path: Path) -> dict[str, Any]:
    usage_info = parse_usage(jsonl_path)
    thread_id = usage_info.get("codex_thread_id") or ""
    model_used = usage_info.get("model") or model
    usage_payload = usage_info.get("usage") or {}
    return {
        "schema_version": "usage.v1",
        "job_id": job_id,
        "codex_thread_id": thread_id,
        "model": model_used,
        "usage": usage_payload,
    }


def write_usage(*, out_dir: Path, attempt_dir: Path, usage_output: dict[str, Any]) -> None:
    write_json(attempt_dir / "usage.json", usage_output)
    write_json(out_dir / "usage.json", usage_output)


def write_codex_artifacts(*, attempt_dir: Path, jsonl_path: Path, last_message_path: Path) -> None:
    write_text(attempt_dir / "codex.jsonl", read_text_utf8_best_effort(jsonl_path))
    write_text(attempt_dir / "last_message.json", read_text_utf8_best_effort(last_message_path))


def main() -> int:
    job = read_job()
    attempt = int(os.environ.get("ATTEMPT") or 1)
    prompt_mode = os.environ.get("PROMPT_MODE") or "generate"
    search_mode = cast(Literal["disabled", "cached", "live"], str(job.get("search_mode") or "disabled"))
    model = str(job.get("model") or "")
    reasoning_effort = normalize_reasoning_effort(job.get("reasoning_effort"))
    if not model:
        print("[generate] missing model")
        return 2

    maybe_set_openai_api_key_from_auth_json()
    ensure_runner_generate_import_path()
    status_update(stage="analysis", summary="开始生成（Codex）")

    out_dir = job_path("output")
    attempt_dir = out_dir / "artifacts" / f"attempt_{attempt}"
    ensure_dir(attempt_dir)

    schema_path = SCHEMA_PATH

    if os.environ.get("MOCK_MODE") == "1":
        write_mock_outputs(job=job, out_dir=out_dir, attempt_dir=attempt_dir, model=model)
        return 0

    prompt = build_prompt(job=job, prompt_mode=prompt_mode)

    write_text(attempt_dir / "prompt.txt", prompt)

    success = run_codex_with_retries(
        request=CodexRetryRequest(
            attempt_dir=attempt_dir,
            prompt=prompt,
            prompt_mode=prompt_mode,
            model=model,
            search_mode=search_mode,
            reasoning_effort=reasoning_effort,
            schema_path=schema_path,
        )
    )
    if success is None:
        status_update(stage="error", summary="生成失败：invalid_output_or_codex_exit", level="error")
        return 1

    write_success_outputs(
        job=job,
        out_dir=out_dir,
        attempt_dir=attempt_dir,
        model=model,
        success=success,
    )
    status_update(stage="done", summary="生成完成，等待测试")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
