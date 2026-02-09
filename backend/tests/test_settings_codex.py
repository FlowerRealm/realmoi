from __future__ import annotations

from uuid import uuid4


def _signup(client, username: str = "bob"):
    unique_username = f"{username}_{uuid4().hex[:8]}"
    resp = client.post("/api/auth/signup", json={"username": unique_username, "password": "password123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_get_codex_settings(client):
    headers = _signup(client, "bob")
    resp = client.get("/api/settings/codex", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"]
    assert isinstance(data["allowed_keys"], list)
    assert "approval_policy" in data["effective_config_toml"]


def test_put_codex_settings_disallowed_key(client):
    headers = _signup(client, "charlie")
    resp = client.put("/api/settings/codex", headers=headers, json={"user_overrides_toml": 'model="o3"\n'})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "disallowed_key"
    assert err["message"] == "model"
