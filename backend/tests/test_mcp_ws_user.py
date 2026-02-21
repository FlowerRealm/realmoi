from __future__ import annotations

"""MCP WebSocket integration tests (user role)."""

import time

from .mcp_ws_common import (
    MCP_JOB_CREATE_ARGS_BASE,
    append_jsonl,
    build_minimal_tests_zip_b64,
    ensure_model,
    jobs_root_from_env,
    signup_token,
    structured_content,
    ws_call_tool,
    ws_initialize_and_list_tools,
)


def create_job_and_assert_inputs(*, ws, zip_b64: str) -> tuple[str, Any]:
    created = ws_call_tool(
        ws,
        request_id=3,
        name="job.create",
        arguments={**MCP_JOB_CREATE_ARGS_BASE, "tests_zip_b64": zip_b64},
    )
    created_payload = structured_content(created)
    job_id = str(created_payload.get("job_id") or "")
    assert job_id

    jobs_root = jobs_root_from_env()
    assert (jobs_root / job_id / "input" / "job.json").exists()
    assert (jobs_root / job_id / "input" / "tests" / "1.in").exists()
    return job_id, jobs_root


def assert_job_tests_listing(*, ws, job_id: str) -> None:
    tests_resp = ws_call_tool(ws, request_id=41, name="job.get_tests", arguments={"job_id": job_id})
    tests_payload = structured_content(tests_resp)
    items = tests_payload.get("items") or []
    assert isinstance(items, list) and items
    first = items[0] or {}
    assert first.get("name") == "1"
    assert first.get("input_rel") == "tests/1.in"
    assert first.get("expected_rel") == "tests/1.out"


def assert_job_test_preview(*, ws, job_id: str) -> None:
    preview_resp = ws_call_tool(
        ws,
        request_id=42,
        name="job.get_test_preview",
        arguments={"job_id": job_id, "input_rel": "tests/1.in", "expected_rel": "tests/1.out", "max_bytes": 1024},
    )
    preview_payload = structured_content(preview_resp)
    preview_input = (preview_payload.get("input") or {}).get("text")
    preview_expected = (preview_payload.get("expected") or {}).get("text")
    assert preview_input == "1 2\n"
    assert preview_expected == "3\n"


def assert_job_state(*, ws, job_id: str) -> None:
    state_resp = ws_call_tool(ws, request_id=4, name="job.get_state", arguments={"job_id": job_id})
    state_payload = structured_content(state_resp)
    state_job_id = str(state_payload.get("job_id") or "")
    assert state_job_id == job_id


def subscribe_agent_status_stream(*, ws, job_id: str) -> None:
    ws_call_tool(
        ws,
        request_id=5,
        name="job.subscribe",
        arguments={"job_id": job_id, "streams": ["agent_status"], "agent_status_offset": 0},
    )


def append_agent_status_line_and_receive(*, ws, jobs_root: Any, job_id: str) -> None:
    log_path = jobs_root / job_id / "logs" / "agent_status.jsonl"
    log_line = {
        "ts": "2026-02-09T00:00:00Z",
        "seq": "t-1",
        "job_id": job_id,
        "attempt": 1,
        "stage": "test",
        "level": "info",
        "progress": 10,
        "summary": "测试中",
        "meta": {},
    }
    append_jsonl(log_path, log_line)

    # Give the tailer a moment to pick up.
    time.sleep(0.3)

    notif = ws.receive_json()
    assert notif.get("method") == "agent_status"
    params = notif.get("params") or {}
    assert str(params.get("job_id") or "") == job_id
    assert (params.get("item") or {}).get("summary") == "测试中"


def test_mcp_ws_job_create_and_subscribe_agent_status(client):
    ensure_model(client, "test-model-mcp")
    token = signup_token(client, "mcp-user")

    zip_b64 = build_minimal_tests_zip_b64()

    with client.websocket_connect(f"/api/mcp/ws?token={token}") as ws:
        # 1) initialize + tools/list：确认暴露的 job.* 工具集
        tool_names = ws_initialize_and_list_tools(ws)
        assert "job.create" in tool_names
        assert "job.get_tests" in tool_names
        assert "job.get_test_preview" in tool_names
        assert "job.subscribe" in tool_names

        # 2) job.create：创建 job 并落盘 input/job.json + tests/
        job_id, jobs_root = create_job_and_assert_inputs(ws=ws, zip_b64=zip_b64)

        # 3) job.get_tests：校验 tests 列表路径
        assert_job_tests_listing(ws=ws, job_id=job_id)

        # 4) job.get_test_preview：校验 preview 文本内容
        assert_job_test_preview(ws=ws, job_id=job_id)

        # 5) job.get_state：检查 state 返回的 job_id 一致性
        assert_job_state(ws=ws, job_id=job_id)

        # 6) job.subscribe：订阅 agent_status stream
        subscribe_agent_status_stream(ws=ws, job_id=job_id)

        # 7) 追加 agent_status.jsonl 并等待 tail 通知
        append_agent_status_line_and_receive(ws=ws, jobs_root=jobs_root, job_id=job_id)
