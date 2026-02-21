from __future__ import annotations

# AUTO_COMMENT_HEADER_V1: runner_generate_codex_appserver.py
# 说明：Codex app-server 适配器（runner 侧入口）。
# - 主流程：启动 app-server → thread/start → turn/start → 事件循环 → 抽取 assistant 文本
# - 事件/增量语义在 `_codex_appserver_events.py`；传输/IO 在 `_codex_appserver_transport.py`

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

try:
    from _codex_appserver_events import EventLoopContext, TurnState, build_event_handlers, run_event_loop
    from _codex_appserver_transport import (
        TurnStartRequest,
        read_schema_json,
        start_appserver_process,
        start_thread,
        start_turn,
        terminate_process,
    )
except ModuleNotFoundError:  # pragma: no cover
    from runner.app._codex_appserver_events import EventLoopContext, TurnState, build_event_handlers, run_event_loop  # type: ignore
    from runner.app._codex_appserver_transport import (  # type: ignore
        TurnStartRequest,
        read_schema_json,
        start_appserver_process,
        start_thread,
        start_turn,
        terminate_process,
    )


SearchMode = Literal["disabled", "cached", "live"]


@dataclass(frozen=True)
class CodexAppserverArtifacts:
    schema_path: Path
    jsonl_path: Path
    last_message_path: Path


def run_codex_appserver(
    *,
    prompt: str,
    model: str,
    search_mode: SearchMode,
    reasoning_effort: str,
    artifacts: CodexAppserverArtifacts,
) -> int:
    # NOTE: app-server transport does not use this flag today (kept for runner_generate parity).
    del search_mode

    proc: subprocess.Popen[str] | None = None
    state = TurnState()
    request_id = 0
    handlers = build_event_handlers(state)

    try:
        proc = start_appserver_process()
        schema_obj = read_schema_json(artifacts.schema_path)

        with artifacts.jsonl_path.open("w", encoding="utf-8") as out:
            thread_id, _model_used, request_id = start_thread(proc, out, model=model, request_id=request_id)
            turn_req_id, request_id = start_turn(
                proc,
                req=TurnStartRequest(
                    thread_id=thread_id,
                    prompt=prompt,
                    reasoning_effort=reasoning_effort,
                    schema_obj=schema_obj,
                ),
                request_id=request_id,
            )
            ctx = EventLoopContext(out=out, turn_req_id=turn_req_id, state=state, handlers=handlers)
            run_event_loop(proc, ctx=ctx)

        if not state.assistant_text.strip():
            raise RuntimeError("appserver_empty_agent_message")

        artifacts.last_message_path.parent.mkdir(parents=True, exist_ok=True)
        artifacts.last_message_path.write_text(state.assistant_text, encoding="utf-8")
        return 0

    finally:
        if proc is not None:
            terminate_process(proc)

