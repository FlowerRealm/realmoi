from runner.app.runner_generate import (
    explanation_fields_are_chinese,
    has_cjk_text,
    normalize_reasoning_effort,
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
