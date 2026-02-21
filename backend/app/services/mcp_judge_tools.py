from __future__ import annotations

"""
Judge MCP tool definitions.

这些 tool 通过统一 MCP WS（/api/mcp/ws）提供给独立测评机（judge worker）使用。
本文件只包含静态的 tool schema，避免与具体 WS 处理逻辑耦合在一起。
"""

from typing import Any


def tool_schema(*, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    """Build MCP tool inputSchema."""
    return {
        "type": "object",
        "additionalProperties": True,
        "properties": properties,
        "required": required,
    }


def tool_def(*, name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    """Build MCP tool metadata object."""
    return {
        "name": name,
        "description": description,
        "inputSchema": tool_schema(properties=properties, required=required),
    }


JUDGE_TOOLS: list[dict[str, Any]] = [
    tool_def(
        name="judge.claim_next",
        description="Claim one queued job for independent judge worker.",
        properties={"machine_id": {"type": "string"}},
        required=["machine_id"],
    ),
    tool_def(
        name="judge.release_claim",
        description="Release claim lock for a previously claimed job.",
        properties={"job_id": {"type": "string"}, "claim_id": {"type": "string"}},
        required=["job_id", "claim_id"],
    ),
    tool_def(
        name="judge.job.get_state",
        description="Get job state.json payload (requires claim_id).",
        properties={"job_id": {"type": "string"}, "claim_id": {"type": "string"}},
        required=["job_id", "claim_id"],
    ),
    tool_def(
        name="judge.input.list",
        description="List files under job input/ (requires claim_id).",
        properties={"job_id": {"type": "string"}, "claim_id": {"type": "string"}},
        required=["job_id", "claim_id"],
    ),
    tool_def(
        name="judge.input.read_chunk",
        description="Read a chunk of an input file. Returns chunk_b64 + next_offset + eof (requires claim_id).",
        properties={
            "job_id": {"type": "string"},
            "claim_id": {"type": "string"},
            "path": {"type": "string"},
            "offset": {"type": "integer"},
            "max_bytes": {"type": "integer"},
        },
        required=["job_id", "claim_id", "path"],
    ),
    tool_def(
        name="judge.job.patch_state",
        description="Patch backend state.json (deep-merge) (requires claim_id).",
        properties={"job_id": {"type": "string"}, "claim_id": {"type": "string"}, "patch": {"type": "object"}},
        required=["job_id", "claim_id", "patch"],
    ),
    tool_def(
        name="judge.job.append_terminal",
        description="Append bytes to logs/terminal.log with offset check (requires claim_id).",
        properties={
            "job_id": {"type": "string"},
            "claim_id": {"type": "string"},
            "offset": {"type": "integer"},
            "chunk_b64": {"type": "string"},
        },
        required=["job_id", "claim_id", "offset", "chunk_b64"],
    ),
    tool_def(
        name="judge.job.append_agent_status",
        description="Append bytes to logs/agent_status.jsonl with offset check (requires claim_id).",
        properties={
            "job_id": {"type": "string"},
            "claim_id": {"type": "string"},
            "offset": {"type": "integer"},
            "chunk_b64": {"type": "string"},
        },
        required=["job_id", "claim_id", "offset", "chunk_b64"],
    ),
    tool_def(
        name="judge.job.put_artifacts",
        description="Write output artifacts main.cpp/solution.json/report.json (requires claim_id).",
        properties={
            "job_id": {"type": "string"},
            "claim_id": {"type": "string"},
            "main_cpp": {"type": "string"},
            "solution_json": {"type": "object"},
            "report_json": {"type": "object"},
        },
        required=["job_id", "claim_id"],
    ),
    tool_def(
        name="judge.prepare_generate",
        description="Prepare generate bundle (effective config + auth + upstream base url) (requires claim_id).",
        properties={"job_id": {"type": "string"}, "claim_id": {"type": "string"}},
        required=["job_id", "claim_id"],
    ),
    tool_def(
        name="judge.usage.ingest",
        description="Ingest usage.json payload into usage_records and persist usage artifacts (requires claim_id).",
        properties={
            "job_id": {"type": "string"},
            "claim_id": {"type": "string"},
            "attempt": {"type": "integer"},
            "usage": {"type": "object"},
        },
        required=["job_id", "claim_id", "attempt", "usage"],
    ),
]
