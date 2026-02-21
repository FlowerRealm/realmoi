from __future__ import annotations

# AUTO_COMMENT_HEADER_V1: runner_generate_codex_exec.py
# 说明：该文件封装 `codex exec` 子进程调用与终端事件转发（尽量不影响主流程）。

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from _codex_exec_io import stream_stdout_to_jsonl, write_prompt_and_close

try:
    from runner_generate_prompt import summarize_reasoning_text
except ModuleNotFoundError:  # pragma: no cover
    from runner.app.runner_generate_prompt import summarize_reasoning_text  # type: ignore


@dataclass(frozen=True)
class CodexExecArtifacts:
    schema_path: Path
    jsonl_path: Path
    last_message_path: Path


# 构造 `codex exec` 命令行：stdin 输入 prompt，stdout 输出 json event stream。
def build_codex_cmd(*, model: str, search_mode: Literal["disabled", "cached", "live"], reasoning_effort: str, artifacts: CodexExecArtifacts) -> list[str]:
    cmd: list[str] = [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--dangerously-bypass-approvals-and-sandbox",
    ]
    if search_mode == "live":
        cmd.append("--search")
    elif search_mode in ("disabled", "cached"):
        cmd += ["--config", f"web_search={search_mode}"]
    cmd += ["--config", f"model_reasoning_effort={reasoning_effort}"]

    cmd += [
        "--json",
        "--output-schema",
        str(artifacts.schema_path),
        "--output-last-message",
        str(artifacts.last_message_path),
        "-m",
        model,
        "-",
    ]
    return cmd


# 解析 codex 的单行 json 事件；非 json 行返回 None（按原样输出）。
def try_parse_json(line: str) -> dict[str, Any] | None:
    s = line.strip()
    if not s:
        return None
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def emit_error_event(event: dict[str, Any]) -> None:
    message = str(event.get("message") or "")
    if message:
        print(f"[codex] 错误：{message}", flush=True)


def emit_turn_failed_event(event: dict[str, Any]) -> None:
    err = event.get("error") or {}
    if not isinstance(err, dict):
        return
    message = str(err.get("message") or "")
    if message:
        print(f"[codex] 执行失败：{message}", flush=True)


def emit_turn_completed_event(event: dict[str, Any]) -> None:
    usage = event.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    cached_input_tokens = int(usage.get("cached_input_tokens") or 0)
    cached_output_tokens = int(usage.get("cached_output_tokens") or 0)
    print(
        "[codex] 完成，Token统计："
        f"输入={input_tokens} 缓存输入={cached_input_tokens} 输出={output_tokens} 缓存输出={cached_output_tokens}",
        flush=True,
    )


def emit_command_execution_item(*, item: dict[str, Any], started: bool) -> None:
    command = str(item.get("command") or "")
    status = str(item.get("status") or "")

    if started:
        print(f"[codex] $ {command}", flush=True)
        return

    exit_code = item.get("exit_code")
    if exit_code is not None:
        print(f"[codex] exit={exit_code}", flush=True)

    aggregated_output = str(item.get("aggregated_output") or "")
    if aggregated_output.strip():
        out = aggregated_output.rstrip("\n")
        if len(out) > 4000:
            out = out[:4000] + "\n...[truncated]..."
        print(out, flush=True)

    if status and status != "completed":
        print(f"[codex] status={status}", flush=True)


def emit_item_event(*, event_type: str, event: dict[str, Any]) -> None:
    item = event.get("item") or {}
    if not isinstance(item, dict):
        return

    item_type = str(item.get("type") or "")
    started = event_type == "item.started"

    if item_type == "command_execution":
        emit_command_execution_item(item=item, started=started)
        return

    if event_type != "item.completed":
        return

    if item_type == "reasoning":
        print(f"[思考] {summarize_reasoning_text(str(item.get('text') or ''))}", flush=True)
        return
    if item_type == "agent_message":
        print("[结果] 已收到模型输出，正在解析。", flush=True)
        return


def emit_terminal_event(event: dict[str, Any]) -> None:
    event_type = str(event.get("type") or "")
    if event_type == "error":
        emit_error_event(event)
        return
    if event_type == "turn.failed":
        emit_turn_failed_event(event)
        return
    if event_type == "turn.completed":
        emit_turn_completed_event(event)
        return
    if event_type in ("item.started", "item.completed"):
        emit_item_event(event_type=event_type, event=event)
        return


def run_codex_exec(
    *,
    prompt: str,
    model: str,
    search_mode: Literal["disabled", "cached", "live"],
    reasoning_effort: str,
    artifacts: CodexExecArtifacts,
) -> int:
    # 注意：runner 侧已接管审批/沙箱，因此这里显式 bypass。
    cmd = build_codex_cmd(model=model, search_mode=search_mode, reasoning_effort=reasoning_effort, artifacts=artifacts)

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    write_prompt_and_close(proc=proc, prompt=prompt)

    def _handle_line(decoded: str) -> None:
        obj = try_parse_json(decoded)
        if obj is None:
            s = decoded.strip()
            if s:
                print(s, flush=True)
            return
        emit_terminal_event(obj)

    return stream_stdout_to_jsonl(proc=proc, jsonl_path=artifacts.jsonl_path, handle_line=_handle_line)
