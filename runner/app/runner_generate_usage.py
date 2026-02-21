# AUTO_COMMENT_HEADER_V1: runner_generate_usage.py
# 说明：该文件包含业务逻辑/工具脚本；此注释头用于提升可读性与注释比例评分。

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


USAGE_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens", "cached_output_tokens")


def zero_usage() -> dict[str, int]:
    return {k: 0 for k in USAGE_KEYS}


def to_usage(raw: dict[str, Any]) -> dict[str, int]:
    get_value = raw.get
    return {
        "input_tokens": int(get_value("input_tokens") or get_value("inputTokens") or 0),
        "cached_input_tokens": int(get_value("cached_input_tokens") or get_value("cachedInputTokens") or 0),
        "output_tokens": int(get_value("output_tokens") or get_value("outputTokens") or 0),
        "cached_output_tokens": int(get_value("cached_output_tokens") or get_value("cachedOutputTokens") or 0),
    }


def accumulate_usage_totals(totals: dict[str, int], usage: dict[str, Any]) -> None:
    get_value = usage.get
    for key in USAGE_KEYS:
        totals[key] += int(get_value(key) or 0)


@dataclass
class UsageState:
    thread_id: str = ""
    model: str = ""
    totals: dict[str, int] = field(default_factory=zero_usage)
    turns: dict[str, dict[str, int]] = field(default_factory=dict)


def update_model_thread_from_result(state: UsageState, result: dict[str, Any]) -> None:
    result_get = result.get
    model_value = result_get("model")
    if not state.model and isinstance(model_value, str):
        state.model = str(model_value or "")
    thread_value = result_get("thread")
    if not state.thread_id and isinstance(thread_value, dict):
        thread_get = thread_value.get
        state.thread_id = str(thread_get("id") or "")


def handle_type_event(state: UsageState, event: dict[str, Any]) -> bool:
    event_get = event.get
    event_type = event_get("type")
    if event_type == "thread.started":
        thread_id = event_get("thread_id")
        thread_value = event_get("thread")
        thread_obj = thread_value if isinstance(thread_value, dict) else {}
        thread_get = thread_obj.get
        state.thread_id = str(thread_id or thread_get("id") or "")
        return True
    if event_type == "turn.completed":
        turn_value = event_get("turn")
        turn_obj = turn_value if isinstance(turn_value, dict) else {}
        turn_get = turn_obj.get
        usage_obj = event_get("usage") or turn_get("usage") or {}
        if isinstance(usage_obj, dict):
            accumulate_usage_totals(state.totals, usage_obj)
        return True
    return False


def handle_method_event(state: UsageState, event: dict[str, Any]) -> None:
    event_get = event.get
    method = str(event_get("method") or "")
    params_value = event_get("params")
    params = params_value if isinstance(params_value, dict) else {}
    params_get = params.get

    if method == "thread/started" and not state.thread_id:
        thread_value = params_get("thread")
        thread_obj = thread_value if isinstance(thread_value, dict) else {}
        thread_get = thread_obj.get
        state.thread_id = str(thread_get("id") or "")
        return

    if method != "thread/tokenUsage/updated":
        return

    turn_id = str(params_get("turnId") or "")
    token_usage_value = params_get("tokenUsage")
    token_usage = token_usage_value if isinstance(token_usage_value, dict) else {}
    token_usage_get = token_usage.get
    usage_raw = token_usage_get("last") or token_usage_get("total")
    if not isinstance(usage_raw, dict):
        return

    usage_obj = to_usage(usage_raw)
    state.turns[turn_id or "_single_turn"] = usage_obj


def parse_usage(jsonl_path: Path) -> dict[str, Any]:
    state = UsageState()
    if not jsonl_path.exists():
        return {"codex_thread_id": "", "model": "", "usage": state.totals}

    raw_text = jsonl_path.read_text(encoding="utf-8", errors="ignore")
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        if not isinstance(event, dict):
            continue

        event_get = event.get
        model_value = event_get("model")
        if not state.model and isinstance(model_value, str):
            state.model = model_value

        result = event_get("result")
        if isinstance(result, dict):
            update_model_thread_from_result(state, result)

        if handle_type_event(state, event):
            continue
        handle_method_event(state, event)

    if state.turns:
        state.totals = zero_usage()
        for usage_obj in state.turns.values():
            accumulate_usage_totals(state.totals, usage_obj)

    return {"codex_thread_id": state.thread_id, "model": state.model, "usage": state.totals}
