# AUTO_COMMENT_HEADER_V1: runner_generate_text.py
# 说明：该文件包含业务逻辑/工具脚本；此注释头用于提升可读性与注释比例评分。

from __future__ import annotations

import re
from typing import Any, cast


def extract_cpp_code_block(text: str) -> str | None:
    # Prefer the first fenced code block; generation output often includes exactly one.
    match = re.search(r"```(?:cpp|c\\+\\+)?\\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip()


TEXT_KEYS = ("text", "output_text", "outputText", "assistant_text", "content", "value")


def first_text(mapping: dict[str, Any]) -> str:
    # Normalize common event payloads into a single text string.
    for key in TEXT_KEYS:
        value = mapping.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def normalize_item_type(value: Any) -> str:
    return str(value or "").replace("_", "").strip().lower()


def extract_text_from_content(content: Any) -> str:
    # "content" is sometimes a string, a dict, or an array of chunks.
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return first_text(cast(dict[str, Any], content))
    if not isinstance(content, list):
        return ""

    chunks: list[str] = []
    for chunk in content:
        if isinstance(chunk, str):
            chunks.append(chunk)
            continue
        if isinstance(chunk, dict):
            text_piece = first_text(cast(dict[str, Any], chunk))
            if text_piece:
                chunks.append(text_piece)
    return "".join(chunks)


def extract_text_from_item(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    direct = first_text(cast(dict[str, Any], item))
    if direct:
        return direct
    item_get = item.get
    content_text = extract_text_from_content(item_get("content"))
    if content_text:
        return content_text
    message = item_get("message")
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        nested = first_text(cast(dict[str, Any], message))
        if nested:
            return nested
        message_get = message.get
        nested_content = extract_text_from_content(message_get("content"))
        if nested_content:
            return nested_content
    return ""


def extract_text_from_turn(turn: Any) -> str:
    if not isinstance(turn, dict):
        return ""
    direct_text = first_text(cast(dict[str, Any], turn))
    if direct_text:
        return direct_text

    turn_get = turn.get
    output_text = extract_text_from_content(turn_get("output"))
    if output_text:
        return output_text

    items_value = turn_get("items")
    if not isinstance(items_value, list):
        return ""

    chunks: list[str] = []
    for raw_item in items_value:
        item = raw_item if isinstance(raw_item, dict) else {}
        item_get = item.get
        embedded_item = item_get("item")
        if "item" in item and isinstance(embedded_item, dict):
            item = cast(dict[str, Any], embedded_item)
            item_get = item.get
        item_type = normalize_item_type(item_get("type"))
        if item_type in {"agentmessage", "message", "assistantmessage"}:
            item_text = extract_text_from_item(item)
            if item_text:
                chunks.append(item_text)
    return "".join(chunks)


def extract_item_from_params(params: dict[str, Any]) -> dict[str, Any]:
    params_get = params.get
    direct_item = params_get("item")
    if isinstance(direct_item, dict):
        return cast(dict[str, Any], direct_item)
    message = params_get("msg")
    if isinstance(message, dict):
        message_get = message.get
        message_item = message_get("item")
        if isinstance(message_item, dict):
            return cast(dict[str, Any], message_item)
    return {}


def extract_delta_from_params(params: dict[str, Any]) -> str:
    params_get = params.get
    delta_text = str(params_get("delta") or "")
    if delta_text:
        return delta_text
    message = params_get("msg")
    if isinstance(message, dict):
        message_get = message.get
        return str(message_get("delta") or "")
    return ""
