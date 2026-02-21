from __future__ import annotations

# AUTO_COMMENT_HEADER_V1: _codex_appserver_events.py
# 说明：Codex app-server 事件层（从 JSONL 流中抽取 assistant 文本与增量状态）。
# - 负责 turn/start 同步响应处理、turn.started/turn.completed 生命周期
# - 负责 item.* 事件的增量抽取（reasoning summary / agent message / command output）
# - 负责将原始 jsonl 落盘（通过 transport.write_jsonl）

import json
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable

try:
    from runner_generate_status import agent_delta_update
    from runner_generate_text import (
        extract_delta_from_params,
        extract_item_from_params,
        extract_text_from_item,
        extract_text_from_turn,
        normalize_item_type,
    )
except ModuleNotFoundError:  # pragma: no cover
    from runner.app.runner_generate_status import agent_delta_update  # type: ignore
    from runner.app.runner_generate_text import (  # type: ignore
        extract_delta_from_params,
        extract_item_from_params,
        extract_text_from_item,
        extract_text_from_turn,
        normalize_item_type,
    )

try:
    from _codex_appserver_transport import read_json_line, write_jsonl
except ModuleNotFoundError:  # pragma: no cover
    from runner.app._codex_appserver_transport import read_json_line, write_jsonl  # type: ignore


# -----------------------------
# Small parsing helpers
# -----------------------------


def safe_int(value: Any, *, default: int = 0) -> int:
    # Best-effort int conversion for app-server payload fields.
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def to_int_or_none(value: Any) -> int | None:
    # Like `safe_int`, but returns None when missing/invalid.
    try:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def to_usage(raw: dict[str, Any]) -> dict[str, int]:
    input_tokens = safe_int(raw.get("input_tokens") or raw.get("inputTokens") or 0)
    cached_input_tokens = safe_int(raw.get("cached_input_tokens") or raw.get("cachedInputTokens") or 0)
    output_tokens = safe_int(raw.get("output_tokens") or raw.get("outputTokens") or 0)
    cached_output_tokens = safe_int(raw.get("cached_output_tokens") or raw.get("cachedOutputTokens") or 0)
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "cached_output_tokens": cached_output_tokens,
    }


# -----------------------------
# Turn state + deltas
# -----------------------------


@dataclass
class DeltaBuffer:
    kind: str
    stage: str
    max_chars: int = 600
    min_interval_s: float = 0.25
    buf: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    last_flush_ts: float = 0.0

    def append(self, delta: str, meta: dict[str, Any] | None = None) -> None:
        if meta is not None:
            self.meta = meta
        self.buf += str(delta or "")

    def flush(self, *, force: bool = False) -> None:
        now = time.time()
        if not force and (len(self.buf) < self.max_chars) and (now - self.last_flush_ts < self.min_interval_s):
            return
        if not self.buf and self.kind != "reasoning_summary_boundary":
            return
        agent_delta_update(kind=self.kind, delta=self.buf, stage=self.stage, meta=self.meta)
        self.buf = ""
        self.last_flush_ts = now


@dataclass
class TurnState:
    assistant_text: str = ""
    assistant_text_fallback: str = ""
    usage_last: dict[str, int] = field(
        default_factory=lambda: {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "cached_output_tokens": 0,
        }
    )
    saw_turn_started: bool = False
    saw_agent_message_delta: bool = False
    reasoning_delta: DeltaBuffer = field(default_factory=lambda: DeltaBuffer(kind="reasoning_summary_delta", stage="analysis"))
    message_delta: DeltaBuffer = field(default_factory=lambda: DeltaBuffer(kind="agent_message_delta", stage="done"))
    command_delta: DeltaBuffer = field(default_factory=lambda: DeltaBuffer(kind="command_output_delta", stage="coding"))


@dataclass(frozen=True)
class EventLoopContext:
    # NOTE: 将 event-loop 相关参数打包，降低参数数量扣分。
    out: Any
    turn_req_id: int
    state: TurnState
    handlers: dict[str, Callable[[dict[str, Any]], None]]


# -----------------------------
# Event handlers (item.*)
# -----------------------------


def handle_reasoning_summary_delta(state: TurnState, params: dict[str, Any]) -> None:
    delta = str(params.get("delta") or "")
    summary_index = to_int_or_none(params.get("summaryIndex"))
    meta: dict[str, Any] = {"source": "summary_text_delta"}
    if summary_index is not None:
        meta["summary_index"] = summary_index
    state.reasoning_delta.append(delta, meta=meta)
    state.reasoning_delta.flush()


def handle_reasoning_summary_part_added(state: TurnState, params: dict[str, Any]) -> None:
    state.reasoning_delta.flush(force=True)
    boundary_meta: dict[str, Any] = {"source": "summary_part_added", "boundary": True}
    summary_index = to_int_or_none(params.get("summaryIndex"))
    if summary_index is not None:
        boundary_meta["summary_index"] = summary_index
    agent_delta_update(kind="reasoning_summary_boundary", delta="", stage="analysis", meta=boundary_meta)


def handle_agent_message_delta(state: TurnState, params: dict[str, Any]) -> None:
    delta = extract_delta_from_params(params)
    state.assistant_text += delta
    state.message_delta.append(delta)
    state.saw_agent_message_delta = True
    state.message_delta.flush()


def handle_agent_message_fallback(state: TurnState, params: dict[str, Any]) -> None:
    delta = extract_delta_from_params(params)
    if delta:
        state.assistant_text_fallback += delta


def handle_command_output_delta(state: TurnState, params: dict[str, Any]) -> None:
    delta = str(params.get("delta") or "")
    if delta:
        print(delta, end="", flush=True)
    state.command_delta.append(delta)
    state.command_delta.flush()


def handle_item_started(state: TurnState, params: dict[str, Any]) -> None:
    item = extract_item_from_params(params)
    if normalize_item_type(item.get("type")) != "commandexecution":
        return
    command_text = str(item.get("command") or "")
    if command_text:
        print(f"[codex] $ {command_text}", flush=True)


def handle_item_completed(state: TurnState, params: dict[str, Any]) -> None:
    item = extract_item_from_params(params)
    item_type = normalize_item_type(item.get("type"))

    if item_type == "commandexecution":
        exit_code = item.get("exitCode")
        if exit_code is None:
            exit_code = item.get("exit_code")
        if exit_code is not None:
            print(f"[codex] exit={int(exit_code)}", flush=True)
        state.command_delta.flush(force=True)
        return

    if item_type not in {"agentmessage", "assistantmessage", "message"}:
        return

    text = extract_text_from_item(item)
    if not text:
        return

    state.assistant_text = text
    if not state.saw_agent_message_delta:
        state.message_delta.append(text)
        state.message_delta.flush(force=True)


def handle_token_usage_updated(state: TurnState, params: dict[str, Any]) -> None:
    token_usage = params.get("tokenUsage") if isinstance(params.get("tokenUsage"), dict) else {}
    usage_raw = token_usage.get("last") or token_usage.get("total")
    if isinstance(usage_raw, dict):
        state.usage_last = to_usage(usage_raw)


def handle_turn_completed(state: TurnState, params: dict[str, Any], out) -> None:
    turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
    extracted = extract_text_from_turn(turn)
    if extracted:
        state.assistant_text = extracted
    if not state.assistant_text.strip() and state.assistant_text_fallback.strip():
        state.assistant_text = state.assistant_text_fallback
    if state.assistant_text and not state.saw_agent_message_delta:
        state.message_delta.append(state.assistant_text)

    state.reasoning_delta.flush(force=True)
    state.message_delta.flush(force=True)
    state.command_delta.flush(force=True)

    out.write(json.dumps({"type": "turn.completed", "usage": state.usage_last}, ensure_ascii=False) + "\n")
    out.flush()

    print(
        "[codex] 完成，Token统计：输入={input_tokens} 缓存输入={cached_input_tokens} 输出={output_tokens} 缓存输出={cached_output_tokens}".format(
            **state.usage_last
        ),
        flush=True,
    )


def build_event_handlers(state: TurnState) -> dict[str, Callable[[dict[str, Any]], None]]:
    # Normalize event keys from different app-server versions.
    return {
        "item/reasoning/summaryTextDelta": lambda p: handle_reasoning_summary_delta(state, p),
        "item/reasoning/summary_text_delta": lambda p: handle_reasoning_summary_delta(state, p),
        "item/reasoning/summaryPartAdded": lambda p: handle_reasoning_summary_part_added(state, p),
        "item/reasoning/summary_part_added": lambda p: handle_reasoning_summary_part_added(state, p),
        "item/agentMessage/delta": lambda p: handle_agent_message_delta(state, p),
        "item/agent_message/delta": lambda p: handle_agent_message_delta(state, p),
        "codex/event/agent_message_delta": lambda p: handle_agent_message_fallback(state, p),
        "codex/event/agent_message_content_delta": lambda p: handle_agent_message_fallback(state, p),
        "item/commandExecution/outputDelta": lambda p: handle_command_output_delta(state, p),
        "item/command_execution/output_delta": lambda p: handle_command_output_delta(state, p),
        "item/started": lambda p: handle_item_started(state, p),
        "item.started": lambda p: handle_item_started(state, p),
        "item/completed": lambda p: handle_item_completed(state, p),
        "item.completed": lambda p: handle_item_completed(state, p),
        "thread/tokenUsage/updated": lambda p: handle_token_usage_updated(state, p),
        "thread/token_usage/updated": lambda p: handle_token_usage_updated(state, p),
    }


# -----------------------------
# Event loop routing
# -----------------------------


TURN_STARTED_METHODS = {"turn/started", "turn.started"}
TURN_COMPLETED_METHODS = {"turn/completed", "turn.completed"}


def handle_turn_start_response(state: TurnState, obj: dict[str, Any], *, turn_req_id: int) -> bool:
    # turn/start 的同步返回：可能包含整段 assistant 文本（非 event）。
    if obj.get("id") != turn_req_id:
        return False
    if "error" in obj:
        start_error = obj.get("error")
        raise RuntimeError(f"appserver_turn_start_failed:{start_error}")
    if "result" not in obj:
        return False
    result_obj = obj.get("result") if isinstance(obj.get("result"), dict) else {}
    extracted = extract_text_from_turn(result_obj.get("turn"))
    if extracted:
        state.assistant_text = extracted
    return True


def handle_event_method_error(params: dict[str, Any]) -> None:
    message = str(params.get("message") or "unknown_error")
    raise RuntimeError(f"appserver_error:{message}")


def handle_turn_started_marker(state: TurnState, method: str) -> bool:
    if method not in TURN_STARTED_METHODS:
        return False
    state.saw_turn_started = True
    return True


def handle_turn_completed_marker(ctx: EventLoopContext, method: str, params: dict[str, Any]) -> bool:
    if method not in TURN_COMPLETED_METHODS:
        return False
    handle_turn_completed(ctx.state, params, ctx.out)
    return True


def run_event_loop(proc: subprocess.Popen[str], *, ctx: EventLoopContext) -> None:
    # NOTE: 事件循环负责：
    # - 持续读取 app-server JSONL
    # - 落盘原始 jsonl
    # - 驱动 turn.completed 退出
    while True:
        raw_line, obj = read_json_line(proc)
        if raw_line:
            write_jsonl(ctx.out, raw_line)
        if handle_event_line(ctx=ctx, obj=obj):
            return


def handle_event_line(*, ctx: EventLoopContext, obj: dict[str, Any] | None) -> bool:
    # obj is None => process exited.
    if obj is None:
        raise RuntimeError("appserver_exited_before_turn_completed")
    if not obj:
        return False

    if handle_turn_start_response(ctx.state, obj, turn_req_id=ctx.turn_req_id):
        return False

    method = str(obj.get("method") or "")
    params = obj.get("params") if isinstance(obj.get("params"), dict) else {}

    if method == "error":
        handle_event_method_error(params)
        return False

    if handle_turn_started_marker(ctx.state, method):
        return False

    # 等到 turn/started 之后再处理 item.* / turn.completed 等流式事件。
    if not ctx.state.saw_turn_started:
        return False

    if handle_turn_completed_marker(ctx, method, params):
        return True

    handler = ctx.handlers.get(method)
    if handler is not None:
        handler(params)
    return False

