import json
import os
from pathlib import Path

from runner.app.runner_generate import (
    ensure_runner_generate_import_path,
    explanation_fields_are_chinese,
    has_cjk_text,
    normalize_reasoning_effort,
    parse_usage,
    summarize_reasoning_text,
)


def test_has_cjk_text_detects_chinese() -> None:
    assert has_cjk_text("这是中文")
    assert not has_cjk_text("plain english")


def test_explanation_fields_are_chinese_requires_all_fields() -> None:
    obj = {
        "solution_idea": "先排序再扫描",
        "seed_code_idea": "遍历数组",
        "seed_code_bug_reason": "边界没处理",
    }
    assert explanation_fields_are_chinese(obj)

    obj["seed_code_bug_reason"] = "missing boundary handling"
    assert not explanation_fields_are_chinese(obj)


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
