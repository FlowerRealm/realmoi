from __future__ import annotations

"""MCP judge.* WebSocket test helpers.

Split from the original `test_mcp_ws.py` to keep each test module small.
"""

import base64
import json
from pathlib import Path

from .mcp_ws_common import (
    HTTP_JOB_CREATE_FORM_BASE,
    JUDGE_PUT_ARTIFACTS_ARGS,
    b64encode_ascii,
    jobs_root_from_env,
    set_job_status,
    structured_content,
    ws_call_tool,
)


def assert_judge_tools(tool_names: set[str]) -> None:
    """Assert judge role exposes the full judge.* tool set."""

    expected = {
        "judge.claim_next",
        "judge.release_claim",
        "judge.input.list",
        "judge.input.read_chunk",
        "judge.job.append_terminal",
        "judge.job.append_agent_status",
        "judge.job.put_artifacts",
        "judge.job.patch_state",
        "judge.job.get_state",
        "judge.prepare_generate",
        "judge.usage.ingest",
    }
    missing = expected - set(tool_names)
    assert not missing, f"missing tools: {sorted(missing)}"


def create_queued_job_for_judge_ws(
    client,
    *,
    token: str,
    model: str,
    tests_zip_bytes: bytes,
) -> tuple[str, str, Path, Path]:
    """Create a job via HTTP and force it into queued status for judge flow tests."""

    resp = client.post(
        "/api/jobs",
        headers={"Authorization": f"Bearer {token}"},
        data={**HTTP_JOB_CREATE_FORM_BASE, "model": model},
        files={"tests_zip": ("tests.zip", tests_zip_bytes, "application/zip")},
    )
    assert resp.status_code == 200
    job_id = str(resp.json()["job_id"])

    jobs_root = jobs_root_from_env()
    state_path = jobs_root / job_id / "state.json"
    patched = set_job_status(state_path, "queued")
    owner_user_id = str(patched.get("owner_user_id") or "")
    return job_id, owner_user_id, jobs_root, state_path


def judge_claim_and_assert_lock(ws, *, job_id: str, jobs_root: Path) -> tuple[str, Path]:
    """Claim a job via judge.claim_next and assert judge.lock is written correctly."""

    claim_resp = ws_call_tool(ws, request_id=3, name="judge.claim_next", arguments={"machine_id": "judge-test"})
    payload = structured_content(claim_resp)
    claimed = payload.get("claimed")
    claimed_job_id = str(payload.get("job_id") or "")
    assert claimed is True
    assert claimed_job_id == job_id

    claim_id = str(payload.get("claim_id") or "")
    assert claim_id

    lock_path = jobs_root / job_id / "logs" / "judge.lock"
    assert lock_path.exists()
    lock_obj = json.loads(lock_path.read_text(encoding="utf-8"))
    assert str(lock_obj.get("claim_id") or "") == claim_id

    return claim_id, lock_path


def judge_assert_state_and_inputs(ws, *, job_id: str, claim_id: str) -> None:
    """Assert judge job state and required input paths, then sanity-check job.json content."""

    state_resp = ws_call_tool(
        ws,
        request_id=31,
        name="judge.job.get_state",
        arguments={"job_id": job_id, "claim_id": claim_id},
    )
    state_payload = structured_content(state_resp)
    assert str(state_payload.get("job_id") or "") == job_id

    input_list = ws_call_tool(
        ws,
        request_id=32,
        name="judge.input.list",
        arguments={"job_id": job_id, "claim_id": claim_id},
    )
    input_payload = structured_content(input_list)
    items = input_payload.get("items") or []
    paths = {str(x.get("path") or "") for x in items if isinstance(x, dict)}
    assert "job.json" in paths
    assert "tests/1.in" in paths

    chunk = judge_read_job_json_chunk(ws, job_id=job_id, claim_id=claim_id)
    assert b"job_id" in chunk


def judge_append_logs_and_patch_state(
    ws,
    *,
    job_id: str,
    claim_id: str,
    jobs_root: Path,
    state_path: Path,
) -> None:
    """Append terminal/agent_status logs and patch state.json through judge tools."""

    append_resp = ws_call_tool(
        ws,
        request_id=34,
        name="judge.job.append_terminal",
        arguments={"job_id": job_id, "claim_id": claim_id, "offset": 0, "chunk_b64": b64encode_ascii(b"hello")},
    )
    append_payload = structured_content(append_resp)
    append_ok = append_payload.get("ok")
    append_next_offset = int(append_payload.get("next_offset") or 0)
    assert append_ok is True
    assert append_next_offset == 5

    terminal_log_path = jobs_root / job_id / "logs" / "terminal.log"
    assert terminal_log_path.read_bytes() == b"hello"

    mismatch_resp = ws_call_tool(
        ws,
        request_id=35,
        name="judge.job.append_terminal",
        arguments={"job_id": job_id, "claim_id": claim_id, "offset": 0, "chunk_b64": b64encode_ascii(b"x")},
    )
    mismatch_payload = structured_content(mismatch_resp)
    mismatch_ok = mismatch_payload.get("ok")
    mismatch_code = mismatch_payload.get("code")
    assert mismatch_ok is False
    assert mismatch_code == "offset_mismatch"

    status_resp = ws_call_tool(
        ws,
        request_id=36,
        name="judge.job.append_agent_status",
        arguments={"job_id": job_id, "claim_id": claim_id, "offset": 0, "chunk_b64": b64encode_ascii(b"{}\n")},
    )
    status_payload = structured_content(status_resp)
    status_ok = status_payload.get("ok")
    assert status_ok is True

    patched_resp = ws_call_tool(
        ws,
        request_id=37,
        name="judge.job.patch_state",
        arguments={"job_id": job_id, "claim_id": claim_id, "patch": {"status": "running_generate"}},
    )
    patched_result = patched_resp.get("result")
    assert patched_result is not None
    new_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert new_state.get("status") == "running_generate"


def judge_put_artifacts_and_ingest_usage(ws, *, job_id: str, claim_id: str, jobs_root: Path, model: str) -> None:
    """Put artifacts + ingest usage for a job and assert output files are written."""

    put_resp = ws_call_tool(
        ws,
        request_id=38,
        name="judge.job.put_artifacts",
        arguments={"job_id": job_id, "claim_id": claim_id, **JUDGE_PUT_ARTIFACTS_ARGS},
    )
    put_payload = structured_content(put_resp)
    put_ok = put_payload.get("ok")
    assert put_ok is True
    assert (jobs_root / job_id / "output" / "main.cpp").exists()
    assert (jobs_root / job_id / "output" / "solution.json").exists()
    assert (jobs_root / job_id / "output" / "report.json").exists()

    ingest_resp = ws_call_tool(
        ws,
        request_id=39,
        name="judge.usage.ingest",
        arguments={
            "job_id": job_id,
            "claim_id": claim_id,
            "attempt": 1,
            "usage": {
                "schema_version": "usage.v1",
                "job_id": job_id,
                "codex_thread_id": "t1",
                "model": model,
                "usage": {"input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 20, "cached_output_tokens": 0},
            },
        },
    )
    ingest_payload = structured_content(ingest_resp)
    ingest_ok = ingest_payload.get("ok")
    assert ingest_ok is True
    assert (jobs_root / job_id / "output" / "artifacts" / "attempt_1" / "usage.json").exists()


def judge_prepare_generate(ws, *, job_id: str, claim_id: str) -> dict:
    """Call judge.prepare_generate and return the prepared payload."""

    prepared = ws_call_tool(
        ws,
        request_id=30,
        name="judge.prepare_generate",
        arguments={"job_id": job_id, "claim_id": claim_id},
    )
    prep_payload = structured_content(prepared)

    effective_config = str(prep_payload.get("effective_config_toml") or "")
    assert "approval_policy" in effective_config

    auth_b64 = str(prep_payload.get("auth_json_b64") or "")
    auth_bytes = base64.b64decode(auth_b64.encode("ascii"))
    auth_json = auth_bytes.decode("utf-8", errors="ignore")
    assert "sk-test" in auth_json

    openai_base_url = str(prep_payload.get("openai_base_url") or "")
    assert openai_base_url

    return prep_payload


def judge_read_job_json_chunk(ws, *, job_id: str, claim_id: str) -> bytes:
    """Read first bytes of input/job.json via judge.input.read_chunk."""

    read_resp = ws_call_tool(
        ws,
        request_id=33,
        name="judge.input.read_chunk",
        arguments={"job_id": job_id, "claim_id": claim_id, "path": "job.json", "offset": 0, "max_bytes": 4096},
    )
    read_payload = structured_content(read_resp)
    chunk_b64 = str(read_payload.get("chunk_b64") or "")
    return base64.b64decode(chunk_b64.encode("ascii"))

