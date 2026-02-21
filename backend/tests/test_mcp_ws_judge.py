from __future__ import annotations

"""MCP WebSocket integration tests (judge role)."""

import os

from sqlalchemy import select

from .mcp_ws_common import (
    build_minimal_tests_zip_bytes,
    ensure_model,
    signup_token,
    structured_content,
    ws_call_tool,
    ws_initialize_and_list_tools,
)
from .mcp_ws_judge_helpers import (
    assert_judge_tools,
    create_queued_job_for_judge_ws,
    judge_append_logs_and_patch_state,
    judge_assert_state_and_inputs,
    judge_claim_and_assert_lock,
    judge_prepare_generate,
    judge_put_artifacts_and_ingest_usage,
)


def test_mcp_judge_ws_claim_and_release(client):
    ensure_model(client, "test-model-judge-mcp")
    token = signup_token(client, "judge-mcp-user")

    tests_zip_bytes = build_minimal_tests_zip_bytes()
    job_id, owner_user_id, jobs_root, state_path = create_queued_job_for_judge_ws(
        client,
        token=token,
        model="test-model-judge-mcp",
        tests_zip_bytes=tests_zip_bytes,
    )

    judge_token = str(os.environ["REALMOI_JUDGE_MCP_TOKEN"])
    with client.websocket_connect(f"/api/mcp/ws?token={judge_token}") as ws:
        # 1) initialize + tools/list：断言 judge.* 工具齐全
        tool_names = ws_initialize_and_list_tools(ws, expected_role="judge")
        assert_judge_tools(tool_names)

        # 2) claim_next：抢占 queued job，并写入 judge.lock（claim_id）
        claim_id, lock_path = judge_claim_and_assert_lock(ws, job_id=job_id, jobs_root=jobs_root)

        # 3) prepare_generate：校验配置和鉴权透传
        prep_payload = judge_prepare_generate(ws, job_id=job_id, claim_id=claim_id)
        openai_base_url = prep_payload.get("openai_base_url")
        assert openai_base_url

        # 4) job.get_state + input.list + input.read_chunk：校验输入可读
        judge_assert_state_and_inputs(ws, job_id=job_id, claim_id=claim_id)

        # 5) append_terminal/agent_status + patch_state：校验写入与 offset/patch 机制
        judge_append_logs_and_patch_state(ws, job_id=job_id, claim_id=claim_id, jobs_root=jobs_root, state_path=state_path)

        # 6) put_artifacts + usage.ingest：校验 output/ 写入与 usage.json 归档
        judge_put_artifacts_and_ingest_usage(ws, job_id=job_id, claim_id=claim_id, jobs_root=jobs_root, model="test-model-judge-mcp")

        # 7) claim_next 再次调用应返回 claimed=false（仍然持有 claim）
        claim_again = ws_call_tool(ws, request_id=4, name="judge.claim_next", arguments={"machine_id": "judge-test"})
        again_payload = structured_content(claim_again)
        again_claimed = again_payload.get("claimed")
        assert again_claimed is False

        # 8) release_claim：释放 claim，并删除 judge.lock
        release_resp = ws_call_tool(
            ws,
            request_id=5,
            name="judge.release_claim",
            arguments={"job_id": job_id, "claim_id": claim_id},
        )
        release_payload = structured_content(release_resp)
        released = release_payload.get("released")
        assert released is True

    assert not lock_path.exists()

    from backend.app.db import SessionLocal  # noqa: WPS433
    from backend.app.models import UsageRecord  # noqa: WPS433

    # 使用记录必须被入库，并绑定 owner_user_id
    with SessionLocal() as db:
        rec = db.scalar(select(UsageRecord).where(UsageRecord.job_id == job_id))
        assert rec is not None
        assert rec.owner_user_id == owner_user_id
        assert rec.model == "test-model-judge-mcp"
        assert rec.input_tokens == 10

