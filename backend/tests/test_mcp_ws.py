from __future__ import annotations

import base64
import io
import json
import os
import time
import zipfile
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select


def _login(client, username: str, password: str) -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _login_admin_headers(client) -> dict[str, str]:
    token = _login(client, "admin", "admin-password-123")
    return {"Authorization": f"Bearer {token}"}


def _signup_token(client, username: str) -> str:
    unique_username = f"{username}_{uuid4().hex[:8]}"
    resp = client.post("/api/auth/signup", json={"username": unique_username, "password": "password123"})
    assert resp.status_code == 200
    return str(resp.json()["access_token"])


def _ensure_model(client, model: str) -> None:
    admin_headers = _login_admin_headers(client)
    resp = client.put(
        f"/api/admin/pricing/models/{model}",
        headers=admin_headers,
        json={
            "currency": "USD",
            "is_active": True,
            "input_microusd_per_1m_tokens": 1,
            "cached_input_microusd_per_1m_tokens": 1,
            "output_microusd_per_1m_tokens": 1,
            "cached_output_microusd_per_1m_tokens": 1,
        },
    )
    assert resp.status_code == 200


def test_mcp_ws_job_create_and_subscribe_agent_status(client):
    _ensure_model(client, "test-model-mcp")
    token = _signup_token(client, "mcp-user")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("tests/1.in", "1 2\n")
        zf.writestr("tests/1.out", "3\n")
    zip_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    with client.websocket_connect(f"/api/mcp/ws?token={token}") as ws:
        ws.send_json({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        init_resp = ws.receive_json()
        assert init_resp["id"] == 1
        assert init_resp["result"]["serverInfo"]["name"] == "realmoi-mcp"

        ws.send_json({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools_resp = ws.receive_json()
        assert tools_resp["id"] == 2
        tool_names = {t.get("name") for t in (tools_resp.get("result") or {}).get("tools") or []}
        assert "job.create" in tool_names
        assert "job.get_tests" in tool_names
        assert "job.get_test_preview" in tool_names
        assert "job.subscribe" in tool_names

        ws.send_json(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "job.create",
                    "arguments": {
                        "model": "test-model-mcp",
                        "statement_md": "# A\n",
                        "current_code_cpp": "",
                        "tests_zip_b64": zip_b64,
                        "tests_format": "auto",
                        "compare_mode": "tokens",
                        "run_if_no_expected": True,
                        "reasoning_effort": "medium",
                        "time_limit_ms": 2000,
                        "memory_limit_mb": 256,
                    },
                },
            }
        )
        created = ws.receive_json()
        assert created["id"] == 3
        assert "error" not in created, f"mcp error: {created.get('error')}"
        job_id = str((created.get("result") or {}).get("structuredContent", {}).get("job_id") or "")
        assert job_id

        jobs_root = Path(os.environ["REALMOI_JOBS_ROOT"])
        assert (jobs_root / job_id / "input" / "job.json").exists()
        assert (jobs_root / job_id / "input" / "tests" / "1.in").exists()

        ws.send_json(
            {
                "jsonrpc": "2.0",
                "id": 41,
                "method": "tools/call",
                "params": {"name": "job.get_tests", "arguments": {"job_id": job_id}},
            }
        )
        tests_resp = ws.receive_json()
        assert tests_resp["id"] == 41
        tests_payload = (tests_resp.get("result") or {}).get("structuredContent") or {}
        items = tests_payload.get("items") or []
        assert isinstance(items, list) and items
        first = items[0] or {}
        assert first.get("name") == "1"
        assert first.get("input_rel") == "tests/1.in"
        assert first.get("expected_rel") == "tests/1.out"

        ws.send_json(
            {
                "jsonrpc": "2.0",
                "id": 42,
                "method": "tools/call",
                "params": {
                    "name": "job.get_test_preview",
                    "arguments": {"job_id": job_id, "input_rel": "tests/1.in", "expected_rel": "tests/1.out", "max_bytes": 1024},
                },
            }
        )
        preview_resp = ws.receive_json()
        assert preview_resp["id"] == 42
        preview_payload = (preview_resp.get("result") or {}).get("structuredContent") or {}
        assert (preview_payload.get("input") or {}).get("text") == "1 2\n"
        assert (preview_payload.get("expected") or {}).get("text") == "3\n"

        ws.send_json(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "job.get_state", "arguments": {"job_id": job_id}},
            }
        )
        state_resp = ws.receive_json()
        assert state_resp["id"] == 4
        assert str((state_resp.get("result") or {}).get("structuredContent", {}).get("job_id") or "") == job_id

        ws.send_json(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "job.subscribe",
                    "arguments": {"job_id": job_id, "streams": ["agent_status"], "agent_status_offset": 0},
                },
            }
        )
        sub_resp = ws.receive_json()
        assert sub_resp["id"] == 5

        # Append one line to agent_status.jsonl and expect a notification.
        log_path = jobs_root / job_id / "logs" / "agent_status.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
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
        with log_path.open("ab") as fp:
            fp.write((json.dumps(log_line, ensure_ascii=False) + "\n").encode("utf-8"))
            fp.flush()

        # Give the tailer a moment to pick up.
        time.sleep(0.3)

        notif = ws.receive_json()
        assert notif.get("method") == "agent_status"
        params = notif.get("params") or {}
        assert str(params.get("job_id") or "") == job_id
        assert (params.get("item") or {}).get("summary") == "测试中"


def test_mcp_judge_ws_claim_and_release(client):
    _ensure_model(client, "test-model-judge-mcp")
    token = _signup_token(client, "judge-mcp-user")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("tests/1.in", "1 2\n")
        zf.writestr("tests/1.out", "3\n")

    resp = client.post(
        "/api/jobs",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "model": "test-model-judge-mcp",
            "statement_md": "# A\n",
            "current_code_cpp": "",
            "tests_format": "auto",
            "compare_mode": "tokens",
            "run_if_no_expected": "true",
            "reasoning_effort": "medium",
            "time_limit_ms": "2000",
            "memory_limit_mb": "256",
        },
        files={"tests_zip": ("tests.zip", buf.getvalue(), "application/zip")},
    )
    assert resp.status_code == 200
    job_id = str(resp.json()["job_id"])

    jobs_root = Path(os.environ["REALMOI_JOBS_ROOT"])
    state_path = jobs_root / job_id / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    owner_user_id = str(state.get("owner_user_id") or "")
    state["status"] = "queued"
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    judge_token = str(os.environ["REALMOI_JUDGE_MCP_TOKEN"])
    with client.websocket_connect(f"/api/mcp/ws?token={judge_token}") as ws:
        ws.send_json({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        init_resp = ws.receive_json()
        assert init_resp["id"] == 1
        assert init_resp["result"]["serverInfo"]["name"] == "realmoi-mcp"
        assert init_resp["result"]["serverInfo"]["role"] == "judge"

        ws.send_json({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools_resp = ws.receive_json()
        assert tools_resp["id"] == 2
        tool_names = {t.get("name") for t in (tools_resp.get("result") or {}).get("tools") or []}
        assert "judge.claim_next" in tool_names
        assert "judge.release_claim" in tool_names
        assert "judge.input.list" in tool_names
        assert "judge.input.read_chunk" in tool_names
        assert "judge.job.append_terminal" in tool_names
        assert "judge.job.append_agent_status" in tool_names
        assert "judge.job.put_artifacts" in tool_names
        assert "judge.job.patch_state" in tool_names
        assert "judge.job.get_state" in tool_names
        assert "judge.prepare_generate" in tool_names
        assert "judge.usage.ingest" in tool_names

        ws.send_json(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "judge.claim_next", "arguments": {"machine_id": "judge-test"}},
            }
        )
        claim_resp = ws.receive_json()
        payload = (claim_resp.get("result") or {}).get("structuredContent") or {}
        assert payload.get("claimed") is True
        assert str(payload.get("job_id") or "") == job_id
        claim_id = str(payload.get("claim_id") or "")
        assert claim_id

        lock_path = jobs_root / job_id / "logs" / "judge.lock"
        assert lock_path.exists()
        lock_obj = json.loads(lock_path.read_text(encoding="utf-8"))
        assert str(lock_obj.get("claim_id") or "") == claim_id

        ws.send_json(
            {
                "jsonrpc": "2.0",
                "id": 30,
                "method": "tools/call",
                "params": {
                    "name": "judge.prepare_generate",
                    "arguments": {"job_id": job_id, "claim_id": claim_id},
                },
            }
        )
        prepared = ws.receive_json()
        assert prepared["id"] == 30
        prep_payload = (prepared.get("result") or {}).get("structuredContent") or {}
        assert "approval_policy" in str(prep_payload.get("effective_config_toml") or "")
        auth_json = base64.b64decode(str(prep_payload.get("auth_json_b64") or "").encode("ascii")).decode("utf-8", errors="ignore")
        assert "sk-test" in auth_json
        assert str(prep_payload.get("openai_base_url") or "")

        ws.send_json(
            {
                "jsonrpc": "2.0",
                "id": 31,
                "method": "tools/call",
                "params": {"name": "judge.job.get_state", "arguments": {"job_id": job_id, "claim_id": claim_id}},
            }
        )
        state_resp = ws.receive_json()
        assert state_resp["id"] == 31
        state_payload = (state_resp.get("result") or {}).get("structuredContent") or {}
        assert str(state_payload.get("job_id") or "") == job_id

        ws.send_json(
            {
                "jsonrpc": "2.0",
                "id": 32,
                "method": "tools/call",
                "params": {"name": "judge.input.list", "arguments": {"job_id": job_id, "claim_id": claim_id}},
            }
        )
        input_list = ws.receive_json()
        assert input_list["id"] == 32
        items = ((input_list.get("result") or {}).get("structuredContent") or {}).get("items") or []
        paths = {str(x.get("path") or "") for x in items}
        assert "job.json" in paths
        assert "tests/1.in" in paths

        ws.send_json(
            {
                "jsonrpc": "2.0",
                "id": 33,
                "method": "tools/call",
                "params": {
                    "name": "judge.input.read_chunk",
                    "arguments": {"job_id": job_id, "claim_id": claim_id, "path": "job.json", "offset": 0, "max_bytes": 4096},
                },
            }
        )
        read_resp = ws.receive_json()
        assert read_resp["id"] == 33
        read_payload = (read_resp.get("result") or {}).get("structuredContent") or {}
        chunk = base64.b64decode(str(read_payload.get("chunk_b64") or "").encode("ascii"))
        assert b"job_id" in chunk

        ws.send_json(
            {
                "jsonrpc": "2.0",
                "id": 34,
                "method": "tools/call",
                "params": {
                    "name": "judge.job.append_terminal",
                    "arguments": {
                        "job_id": job_id,
                        "claim_id": claim_id,
                        "offset": 0,
                        "chunk_b64": base64.b64encode(b"hello").decode("ascii"),
                    },
                },
            }
        )
        append_terminal = ws.receive_json()
        assert append_terminal["id"] == 34
        append_payload = (append_terminal.get("result") or {}).get("structuredContent") or {}
        assert append_payload.get("ok") is True
        assert int(append_payload.get("next_offset") or 0) == 5

        terminal_log_path = jobs_root / job_id / "logs" / "terminal.log"
        assert terminal_log_path.read_bytes() == b"hello"

        ws.send_json(
            {
                "jsonrpc": "2.0",
                "id": 35,
                "method": "tools/call",
                "params": {
                    "name": "judge.job.append_terminal",
                    "arguments": {
                        "job_id": job_id,
                        "claim_id": claim_id,
                        "offset": 0,
                        "chunk_b64": base64.b64encode(b"x").decode("ascii"),
                    },
                },
            }
        )
        mismatch = ws.receive_json()
        assert mismatch["id"] == 35
        mismatch_payload = (mismatch.get("result") or {}).get("structuredContent") or {}
        assert mismatch_payload.get("ok") is False
        assert mismatch_payload.get("code") == "offset_mismatch"

        ws.send_json(
            {
                "jsonrpc": "2.0",
                "id": 36,
                "method": "tools/call",
                "params": {
                    "name": "judge.job.append_agent_status",
                    "arguments": {
                        "job_id": job_id,
                        "claim_id": claim_id,
                        "offset": 0,
                        "chunk_b64": base64.b64encode(b"{}\n").decode("ascii"),
                    },
                },
            }
        )
        append_status = ws.receive_json()
        assert append_status["id"] == 36
        assert ((append_status.get("result") or {}).get("structuredContent") or {}).get("ok") is True

        ws.send_json(
            {
                "jsonrpc": "2.0",
                "id": 37,
                "method": "tools/call",
                "params": {
                    "name": "judge.job.patch_state",
                    "arguments": {"job_id": job_id, "claim_id": claim_id, "patch": {"status": "running_generate"}},
                },
            }
        )
        patched = ws.receive_json()
        assert patched["id"] == 37
        new_state = json.loads(state_path.read_text(encoding="utf-8"))
        assert new_state.get("status") == "running_generate"

        ws.send_json(
            {
                "jsonrpc": "2.0",
                "id": 38,
                "method": "tools/call",
                "params": {
                    "name": "judge.job.put_artifacts",
                    "arguments": {
                        "job_id": job_id,
                        "claim_id": claim_id,
                        "main_cpp": "int main() { return 0; }\\n",
                        "solution_json": {"main_cpp": "int main() { return 0; }\\n"},
                        "report_json": {"status": "succeeded"},
                    },
                },
            }
        )
        put_resp = ws.receive_json()
        assert put_resp["id"] == 38
        assert ((put_resp.get("result") or {}).get("structuredContent") or {}).get("ok") is True
        assert (jobs_root / job_id / "output" / "main.cpp").exists()
        assert (jobs_root / job_id / "output" / "solution.json").exists()
        assert (jobs_root / job_id / "output" / "report.json").exists()

        ws.send_json(
            {
                "jsonrpc": "2.0",
                "id": 39,
                "method": "tools/call",
                "params": {
                    "name": "judge.usage.ingest",
                    "arguments": {
                        "job_id": job_id,
                        "claim_id": claim_id,
                        "attempt": 1,
                        "usage": {
                            "schema_version": "usage.v1",
                            "job_id": job_id,
                            "codex_thread_id": "t1",
                            "model": "test-model-judge-mcp",
                            "usage": {"input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 20, "cached_output_tokens": 0},
                        },
                    },
                },
            }
        )
        ingest_resp = ws.receive_json()
        assert ingest_resp["id"] == 39
        assert ((ingest_resp.get("result") or {}).get("structuredContent") or {}).get("ok") is True
        assert (jobs_root / job_id / "output" / "artifacts" / "attempt_1" / "usage.json").exists()

        # Claim again should return empty while lock is held.
        ws.send_json(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "judge.claim_next", "arguments": {"machine_id": "judge-test"}},
            }
        )
        claim_again = ws.receive_json()
        again_payload = (claim_again.get("result") or {}).get("structuredContent") or {}
        assert again_payload.get("claimed") is False

        ws.send_json(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "judge.release_claim", "arguments": {"job_id": job_id, "claim_id": claim_id}},
            }
        )
        release_resp = ws.receive_json()
        assert release_resp["id"] == 5
        assert ((release_resp.get("result") or {}).get("structuredContent") or {}).get("released") is True

    assert not lock_path.exists()

    from backend.app.db import SessionLocal  # noqa: WPS433
    from backend.app.models import UsageRecord  # noqa: WPS433

    with SessionLocal() as db:
        rec = db.scalar(select(UsageRecord).where(UsageRecord.job_id == job_id))
        assert rec is not None
        assert rec.owner_user_id == owner_user_id
        assert rec.model == "test-model-judge-mcp"
        assert rec.input_tokens == 10
