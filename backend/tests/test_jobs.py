from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path
from uuid import uuid4


def _login(client, username: str, password: str) -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _login_admin_headers(client) -> dict[str, str]:
    token = _login(client, "admin", "admin-password-123")
    return {"Authorization": f"Bearer {token}"}


def _signup_headers(client, username: str) -> dict[str, str]:
    unique_username = f"{username}_{uuid4().hex[:8]}"
    resp = client.post("/api/auth/signup", json={"username": unique_username, "password": "password123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _ensure_model(client, model: str = "test-model") -> None:
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


def _upsert_channel(client, channel: str) -> None:
    admin_headers = _login_admin_headers(client)
    resp = client.put(
        f"/api/admin/upstream/channels/{channel}",
        headers=admin_headers,
        json={
            "display_name": channel,
            "base_url": "https://example.com/v1",
            "api_key": "sk-test",
            "models_path": "/v1/models",
            "is_enabled": True,
        },
    )
    assert resp.status_code == 200


def _read_self_test_token(job_id: str) -> str:
    jobs_root = Path(os.environ["REALMOI_JOBS_ROOT"])
    job_obj = json.loads((jobs_root / job_id / "input" / "job.json").read_text(encoding="utf-8"))
    return str(((job_obj.get("judge") or {}).get("self_test_token")) or "")


def test_create_job_with_tests_zip(client):
    _ensure_model(client, "test-model")
    user_headers = _signup_headers(client, "dora")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("tests/1.in", "1 2\n")
        zf.writestr("tests/1.out", "3\n")

    data = {
        "model": "test-model",
        "statement_md": "# A\n",
        "current_code_cpp": "",
        "search_mode": "cached",
        "reasoning_effort": "high",
        "tests_format": "auto",
        "compare_mode": "tokens",
        "run_if_no_expected": "true",
        "time_limit_ms": "2000",
        "memory_limit_mb": "256",
    }
    files = {"tests_zip": ("tests.zip", buf.getvalue(), "application/zip")}

    resp = client.post("/api/jobs", headers=user_headers, data=data, files=files)
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    jobs_root = Path(os.environ["REALMOI_JOBS_ROOT"])
    assert (jobs_root / job_id / "input" / "tests" / "1.in").exists()
    job_json = (jobs_root / job_id / "input" / "job.json").read_text(encoding="utf-8")
    assert '"present": true' in job_json
    assert '"reasoning_effort": "high"' in job_json
    state_json = (jobs_root / job_id / "state.json").read_text(encoding="utf-8")
    assert '"reasoning_effort": "high"' in state_json


def test_create_job_rejects_zip_slip(client):
    _ensure_model(client, "test-model-2")
    user_headers = _signup_headers(client, "erin")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../evil", "x")

    data = {
        "model": "test-model-2",
        "statement_md": "# A\n",
        "current_code_cpp": "",
        "search_mode": "cached",
    }
    files = {"tests_zip": ("tests.zip", buf.getvalue(), "application/zip")}

    resp = client.post("/api/jobs", headers=user_headers, data=data, files=files)
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "invalid_tests_zip"


def test_create_job_defaults_reasoning_effort_to_medium(client):
    _ensure_model(client, "test-model-3")
    user_headers = _signup_headers(client, "harry")
    data = {
        "model": "test-model-3",
        "statement_md": "# A\n",
        "current_code_cpp": "",
        "search_mode": "cached",
    }

    resp = client.post("/api/jobs", headers=user_headers, data=data)
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    jobs_root = Path(os.environ["REALMOI_JOBS_ROOT"])
    state_json = (jobs_root / job_id / "state.json").read_text(encoding="utf-8")
    assert '"reasoning_effort": "medium"' in state_json


def test_create_job_allows_live_model_with_upstream_channel(client, monkeypatch):
    from backend.app.routers import jobs as jobs_router  # noqa: WPS433

    monkeypatch.setattr(
        jobs_router,
        "list_upstream_model_ids",
        lambda *, channel, db=None: {"gpt-live-from-realms"},
    )

    _upsert_channel(client, "Realms")
    user_headers = _signup_headers(client, "frank")
    data = {
        "model": "gpt-live-from-realms",
        "upstream_channel": "Realms",
        "statement_md": "# A\n",
        "current_code_cpp": "",
        "time_limit_ms": "2000",
        "memory_limit_mb": "256",
    }
    resp = client.post("/api/jobs", headers=user_headers, data=data)
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    jobs_root = Path(os.environ["REALMOI_JOBS_ROOT"])
    state = (jobs_root / job_id / "state.json").read_text(encoding="utf-8")
    assert '"upstream_channel": "Realms"' in state


def test_create_job_rejects_model_not_in_upstream_channel(client, monkeypatch):
    from backend.app.routers import jobs as jobs_router  # noqa: WPS433

    monkeypatch.setattr(
        jobs_router,
        "list_upstream_model_ids",
        lambda *, channel, db=None: {"gpt-5.2-codex"},
    )

    _upsert_channel(client, "Realms")
    user_headers = _signup_headers(client, "grace")
    data = {
        "model": "unknown-live-model",
        "upstream_channel": "Realms",
        "statement_md": "# A\n",
        "current_code_cpp": "",
        "time_limit_ms": "2000",
        "memory_limit_mb": "256",
    }
    resp = client.post("/api/jobs", headers=user_headers, data=data)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_model"


def test_external_self_test_requires_valid_job_token(client):
    _ensure_model(client, "test-model-self-test-token")
    user_headers = _signup_headers(client, "ivy")
    resp = client.post(
        "/api/jobs",
        headers=user_headers,
        data={
            "model": "test-model-self-test-token",
            "statement_md": "# A\n",
            "current_code_cpp": "",
        },
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    bad = client.post(f"/api/jobs/{job_id}/self-test", headers={"X-Job-Token": "bad-token"}, json={"main_cpp": "int main(){}"})
    assert bad.status_code == 403
    assert bad.json()["error"]["code"] == "invalid_job_token"


def test_external_self_test_returns_report_for_codex(client):
    _ensure_model(client, "test-model-self-test")
    user_headers = _signup_headers(client, "jane")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("tests/1.in", "1 2\n")
        zf.writestr("tests/1.out", "3\n")

    resp = client.post(
        "/api/jobs",
        headers=user_headers,
        data={
            "model": "test-model-self-test",
            "statement_md": "# A\n",
            "current_code_cpp": "",
            "tests_format": "auto",
            "compare_mode": "tokens",
            "run_if_no_expected": "true",
            "time_limit_ms": "2000",
            "memory_limit_mb": "256",
        },
        files={"tests_zip": ("tests.zip", buf.getvalue(), "application/zip")},
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    token = _read_self_test_token(job_id)
    assert token

    code = """
#include <bits/stdc++.h>
using namespace std;
int main() {
  long long a, b;
  if (!(cin >> a >> b)) return 0;
  cout << (a + b) << "\\n";
  return 0;
}
""".strip()
    test_resp = client.post(
        f"/api/jobs/{job_id}/self-test",
        headers={"X-Job-Token": token},
        json={"main_cpp": code},
    )
    assert test_resp.status_code == 200
    body = test_resp.json()
    assert body["status"] == "succeeded"
    assert body["compile_ok"] is True
    assert body["summary"]["total"] == 1
    assert body["summary"]["passed"] == 1
