import json
import os
from pathlib import Path

from runner.app.runner_generate import ensure_runner_generate_import_path
from runner.app.runner_generate_prompt import (
    build_prompt_generate,
    build_prompt_repair,
    has_cjk_text,
    normalize_reasoning_effort,
    summarize_reasoning_text,
)
from runner.app.runner_generate_text import extract_delta_from_params, extract_item_from_params, extract_text_from_turn
from runner.app.runner_generate_usage import parse_usage


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
    assert extract_text_from_turn(turn) == '{"main_cpp":"int main(){return 0;}"}'


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
    item = extract_item_from_params(params)
    assert item["type"] == "command_execution"
    assert item["command"] == "ls -la"


def test_extract_delta_from_params_prefers_nested_msg_delta() -> None:
    params = {"msg": {"delta": "partial response"}}
    assert extract_delta_from_params(params) == "partial response"


def test_generate_prompt_does_not_ask_codex_to_run_tests() -> None:
    prompt = build_prompt_generate(
        {
            "problem": {"statement_md": "# A"},
            "seed": {"current_code_cpp": "int main() { return 0; }"},
        }
    )
    assert "独立测评机统一执行" in prompt
    assert "runner_test.py" not in prompt
    assert "python3 -X utf8" not in prompt


def test_generate_prompt_mentions_user_feedback_fields() -> None:
    prompt = build_prompt_generate(
        {
            "problem": {"statement_md": "# A"},
            "seed": {"current_code_cpp": "int main() { return 0; }"},
        }
    )
    assert "user_feedback_md" in prompt
    assert "seed_code_issue_type" in prompt
    assert "seed_code_wrong_lines" in prompt
    assert "seed_code_fix_diff" in prompt


def test_repair_prompt_does_not_ask_codex_to_run_tests() -> None:
    prompt = build_prompt_repair(
        {
            "problem": {"statement_md": "# A"},
            "seed": {"current_code_cpp": ""},
        },
        "first_failure=1 verdict=WA",
        "int main() { return 0; }",
    )
    assert "独立测评机统一执行" in prompt
    assert "runner_test.py" not in prompt
    assert "python3 -X utf8" not in prompt


def test_repair_prompt_mentions_user_feedback_fields() -> None:
    prompt = build_prompt_repair(
        {
            "problem": {"statement_md": "# A"},
            "seed": {"current_code_cpp": "int main() { return 0; }"},
        },
        "first_failure=1 verdict=WA",
        "int main() { return 0; }",
    )
    assert "user_feedback_md" in prompt
    assert "seed_code_issue_type" in prompt
    assert "seed_code_wrong_lines" in prompt
    assert "seed_code_fix_diff" in prompt


def test_generate_prompt_requires_mcp_self_test_when_tests_present() -> None:
    prompt = build_prompt_generate(
        {
            "problem": {"statement_md": "# A"},
            "seed": {"current_code_cpp": ""},
            "tests": {"present": True},
        }
    )
    assert "必须先调用 MCP 工具 `judge.self_test`" in prompt
    assert "judge.self_test" in prompt
    assert "\"main_cpp\"" in prompt
    assert "first_failure" in prompt
    assert "first_failure_message" in prompt


def test_generate_prompt_skips_self_test_when_no_tests() -> None:
    prompt = build_prompt_generate(
        {
            "problem": {"statement_md": "# A"},
            "seed": {"current_code_cpp": ""},
            "tests": {"present": False},
        }
    )
    assert "当前未提供 tests，本轮无需自测" in prompt
