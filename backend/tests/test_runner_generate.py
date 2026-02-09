import json
import os
from pathlib import Path

from runner.app.runner_generate import (
    _extract_delta_from_params,
    _extract_item_from_params,
    _extract_text_from_turn,
    ensure_runner_generate_import_path,
    has_cjk_text,
    normalize_reasoning_effort,
    parse_usage,
    summarize_reasoning_text,
)


def test_has_cjk_text_detects_chinese() -> None:
    assert has_cjk_text("这是中文")
    assert not has_cjk_text("plain english")


def test_summarize_reasoning_text_falls_back_to_chinese_hint() -> None:
    text = "**Planning**\n\nI will inspect files first."
    assert summarize_reasoning_text(text) == "模型完成一轮思考，继续执行中。"


def test_summarize_reasoning_text_prefers_chinese_line() -> None:
    text = "**Plan**\n\n先解析输入，再构建答案。"
    assert summarize_reasoning_text(text) == "先解析输入，再构建答案。"


def test_normalize_reasoning_effort_defaults_to_medium_for_invalid_value() -> None:
    assert normalize_reasoning_effort("LOW") == "low"
    assert normalize_reasoning_effort("xhigh") == "xhigh"
    assert normalize_reasoning_effort("unexpected") == "medium"
    assert normalize_reasoning_effort(None) == "medium"


def test_parse_usage_supports_appserver_token_usage(tmp_path) -> None:
    p = tmp_path / "appserver.jsonl"
    lines = [
        {
            "id": 2,
            "result": {
                "thread": {"id": "thread-1"},
                "model": "gpt-5.2-codex",
            },
        },
        {
            "method": "thread/tokenUsage/updated",
            "params": {
                "threadId": "thread-1",
                "turnId": "0",
                "tokenUsage": {
                    "last": {
                        "inputTokens": 100,
                        "cachedInputTokens": 20,
                        "outputTokens": 30,
                        "reasoningOutputTokens": 0,
                        "totalTokens": 130,
                    }
                },
            },
        },
    ]
    p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n", encoding="utf-8")
    usage = parse_usage(p)
    assert usage["codex_thread_id"] == "thread-1"
    assert usage["model"] == "gpt-5.2-codex"
    assert usage["usage"] == {
        "input_tokens": 100,
        "cached_input_tokens": 20,
        "output_tokens": 30,
        "cached_output_tokens": 0,
    }


def test_ensure_runner_generate_import_path_sets_pythonpath(monkeypatch) -> None:
    monkeypatch.delenv("PYTHONPATH", raising=False)
    ensure_runner_generate_import_path()
    module_dir = str(Path(__file__).resolve().parents[2] / "runner" / "app")
    assert os.environ.get("PYTHONPATH") == module_dir


def test_extract_text_from_turn_supports_nested_agent_items() -> None:
    turn = {
        "id": "turn-1",
        "items": [
            {"type": "reasoning", "text": "..."},  # should be ignored
            {
                "type": "agentMessage",
                "content": [
                    {"type": "text", "text": '{"main_cpp":"int main(){return 0;}"}'},
                ],
            },
        ],
    }
    assert _extract_text_from_turn(turn) == '{"main_cpp":"int main(){return 0;}"}'


def test_extract_item_from_params_supports_codex_event_wrapper() -> None:
    params = {
        "msg": {
            "type": "item_completed",
            "item": {
                "type": "command_execution",
                "command": "ls -la",
            },
        }
    }
    item = _extract_item_from_params(params)
    assert item["type"] == "command_execution"
    assert item["command"] == "ls -la"


def test_extract_delta_from_params_prefers_nested_msg_delta() -> None:
    params = {"msg": {"delta": "partial response"}}
    assert _extract_delta_from_params(params) == "partial response"
