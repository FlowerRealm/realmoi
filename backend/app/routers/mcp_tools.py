from __future__ import annotations

# MCP tool definitions served to user-side MCP clients.
#
# 说明：
# - 这里仅包含静态 schema/描述，便于路由文件聚焦在 WS 交互与权限控制。
# - tool 名称遵循简单的 `namespace.action` 约定（models.* / job.*）。

from typing import Any


def tool_schema(*, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": True,
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def tool_def(*, name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": tool_schema(properties=properties, required=required),
    }


MCP_TOOLS: list[dict[str, Any]] = [
    tool_def(
        name="models.list",
        description="List available models. {live:true} fetches upstream models when possible.",
        properties={"live": {"type": "boolean"}},
    ),
    tool_def(
        name="job.create",
        description="Create a new job. tests_zip_b64 is base64 of tests.zip (optional).",
        properties={
            "model": {"type": "string"},
            "upstream_channel": {"type": "string"},
            "statement_md": {"type": "string"},
            "current_code_cpp": {"type": "string"},
            "tests_zip_b64": {"type": "string"},
            "tests_format": {"type": "string"},
            "compare_mode": {"type": "string"},
            "run_if_no_expected": {"type": "boolean"},
            "search_mode": {"type": "string"},
            "reasoning_effort": {"type": "string"},
            "time_limit_ms": {"type": "integer"},
            "memory_limit_mb": {"type": "integer"},
        },
        required=["model", "statement_md"],
    ),
    tool_def(
        name="job.start",
        description="Start a job.",
        properties={"job_id": {"type": "string"}},
        required=["job_id"],
    ),
    tool_def(
        name="job.cancel",
        description="Cancel a job.",
        properties={"job_id": {"type": "string"}},
        required=["job_id"],
    ),
    tool_def(
        name="job.get_state",
        description="Get job state.json payload.",
        properties={"job_id": {"type": "string"}},
        required=["job_id"],
    ),
    tool_def(
        name="job.get_artifacts",
        description="Get job artifacts (main.cpp/solution.json/report.json).",
        properties={"job_id": {"type": "string"}, "names": {"type": "array", "items": {"type": "string"}}},
        required=["job_id"],
    ),
    tool_def(
        name="job.get_tests",
        description="List extracted tests (from user tests.zip).",
        properties={"job_id": {"type": "string"}},
        required=["job_id"],
    ),
    tool_def(
        name="job.get_test_preview",
        description="Read preview text for a single test input/expected (tests/xx.in/.out).",
        properties={
            "job_id": {"type": "string"},
            "input_rel": {"type": "string"},
            "expected_rel": {"type": ["string", "null"]},
            "max_bytes": {"type": "integer"},
        },
        required=["job_id", "input_rel"],
    ),
    tool_def(
        name="job.subscribe",
        description="Subscribe streams for a job; pushes JSON-RPC notifications: agent_status/terminal.",
        properties={
            "job_id": {"type": "string"},
            "streams": {"type": "array", "items": {"type": "string"}},
            "agent_status_offset": {"type": "integer"},
            "terminal_offset": {"type": "integer"},
        },
        required=["job_id"],
    ),
    tool_def(
        name="job.unsubscribe",
        description="Unsubscribe streams for a job.",
        properties={"job_id": {"type": "string"}, "streams": {"type": "array", "items": {"type": "string"}}},
        required=["job_id"],
    ),
]

