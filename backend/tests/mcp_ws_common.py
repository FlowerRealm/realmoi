from __future__ import annotations

"""MCP WebSocket test helpers (common).

These helpers are shared by:
- `backend/tests/test_mcp_ws_user.py`
- `backend/tests/test_mcp_ws_judge.py`
"""

import base64
import io
import json
import os
import zipfile
from pathlib import Path
from uuid import uuid4


# ----------------------------
# 固定 payload（减少测试样板行数）
# ----------------------------

PRICING_MODEL_PATCH: dict[str, int | str | bool] = {
    "currency": "USD",
    "is_active": True,
    "input_microusd_per_1m_tokens": 1,
    "cached_input_microusd_per_1m_tokens": 1,
    "output_microusd_per_1m_tokens": 1,
    "cached_output_microusd_per_1m_tokens": 1,
}

MCP_JOB_CREATE_ARGS_BASE: dict[str, object] = {
    "model": "test-model-mcp",
    "statement_md": "# A\n",
    "current_code_cpp": "",
    "tests_format": "auto",
    "compare_mode": "tokens",
    "run_if_no_expected": True,
    "reasoning_effort": "medium",
    "time_limit_ms": 2000,
    "memory_limit_mb": 256,
}

HTTP_JOB_CREATE_FORM_BASE: dict[str, str] = {
    "model": "test-model-judge-mcp",
    "statement_md": "# A\n",
    "current_code_cpp": "",
    "tests_format": "auto",
    "compare_mode": "tokens",
    "run_if_no_expected": "true",
    "reasoning_effort": "medium",
    "time_limit_ms": "2000",
    "memory_limit_mb": "256",
}

JUDGE_PUT_ARTIFACTS_ARGS: dict[str, object] = {
    "main_cpp": "int main() { return 0; }\n",
    "solution_json": {"main_cpp": "int main() { return 0; }\n"},
    "report_json": {"status": "succeeded"},
}


# ----------------------------
# HTTP 认证/管理接口辅助
# ----------------------------


def login(client, username: str, password: str) -> str:
    """Login and return access token."""

    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def login_admin_headers(client) -> dict[str, str]:
    """Return Authorization header for the built-in admin user."""

    token = login(client, "admin", "admin-password-123")
    return {"Authorization": f"Bearer {token}"}


def signup_token(client, username: str) -> str:
    """Signup a random username and return its access token."""

    unique_username = f"{username}_{uuid4().hex[:8]}"
    resp = client.post("/api/auth/signup", json={"username": unique_username, "password": "password123"})
    assert resp.status_code == 200
    return str(resp.json()["access_token"])


def ensure_model(client, model: str) -> None:
    """Ensure pricing model exists so job.create validation passes."""

    admin_headers = login_admin_headers(client)
    resp = client.put(
        f"/api/admin/pricing/models/{model}",
        headers=admin_headers,
        json=PRICING_MODEL_PATCH,
    )
    assert resp.status_code == 200


# ----------------------------
# MCP JSON-RPC 辅助（WS）
# ----------------------------


def ws_call_tool(ws, *, request_id: int, name: str, arguments: dict) -> dict:
    """Call MCP tool and return the JSON-RPC response frame for `request_id`.

    Notes:
        Some calls may interleave with notifications (frames without matching `id`).
        This helper skips non-matching frames until it receives the response.
    """

    sent = ws.send_json({"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
    assert sent is None

    while True:
        resp = ws.receive_json()
        if not isinstance(resp, dict):
            continue
        if resp.get("id") != request_id:
            continue
        err = resp.get("error")
        assert "error" not in resp, f"mcp error: {err}"
        return resp


def ws_initialize_and_list_tools(ws, *, expected_role: str | None = None) -> set[str]:
    """
    Run MCP initialize + tools/list and return tool name set.

    Args:
        ws: WebSocket connection from FastAPI TestClient.
        expected_role: Optional server role assertion (e.g. "judge").

    Returns:
        Tool name set.
    """

    sent_init = ws.send_json({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert sent_init is None
    init_resp = ws.receive_json()
    assert init_resp["id"] == 1
    server_info = (init_resp.get("result") or {}).get("serverInfo") or {}
    assert server_info.get("name") == "realmoi-mcp"
    if expected_role is not None:
        assert server_info.get("role") == expected_role

    sent_tools = ws.send_json({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert sent_tools is None
    tools_resp = ws.receive_json()
    assert tools_resp["id"] == 2
    tools = ((tools_resp.get("result") or {}).get("tools") or []) if isinstance(tools_resp, dict) else []
    tool_names: set[str] = set()
    for t in tools:
        if isinstance(t, dict):
            tool_name = str(t.get("name") or "")
            tool_names.add(tool_name)
    return tool_names


def structured_content(resp: dict) -> dict:
    """Extract `result.structuredContent` dict from a JSON-RPC response frame."""

    payload = (resp.get("result") or {}).get("structuredContent") or {}
    return payload if isinstance(payload, dict) else {}


# ----------------------------
# ZIP / jobs 目录 / 文件辅助
# ----------------------------


def build_minimal_tests_zip_b64() -> str:
    """Build a minimal tests zip (tests/1.in + tests/1.out) and return base64 ascii."""

    zip_bytes = build_minimal_tests_zip_bytes()
    zip_b64_bytes = base64.b64encode(zip_bytes)
    return zip_b64_bytes.decode("ascii")


def build_minimal_tests_zip_bytes() -> bytes:
    """Build a minimal tests zip (tests/1.in + tests/1.out) and return raw bytes."""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("tests/1.in", "1 2\n")
        zf.writestr("tests/1.out", "3\n")
    return buf.getvalue()


def jobs_root_from_env() -> Path:
    """Resolve REALMOI_JOBS_ROOT as Path."""

    return Path(os.environ["REALMOI_JOBS_ROOT"])


def append_jsonl(path: Path, line_obj: dict) -> None:
    """Append one json line (utf-8) to a file path (creating parents)."""

    mkdir_done = path.parent.mkdir(parents=True, exist_ok=True)
    assert mkdir_done is None
    handle = path.open("ab")
    with handle as fp:
        payload = json.dumps(line_obj, ensure_ascii=False) + "\n"
        raw = payload.encode("utf-8")
        written_bytes = fp.write(raw)
        assert written_bytes > 0
        fp.flush()


def set_job_status(state_path: Path, status: str) -> dict:
    """Patch `state.json` status field and persist."""

    state_text = state_path.read_text(encoding="utf-8")
    state = json.loads(state_text)
    state["status"] = status
    new_text = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    state_path.write_text(new_text, encoding="utf-8")
    return state


def b64encode_ascii(data: bytes) -> str:
    """Base64-encode bytes and return ascii string."""

    return base64.b64encode(data).decode("ascii")

