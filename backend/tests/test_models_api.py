from __future__ import annotations

from uuid import uuid4


def _signup_headers(client, username: str) -> dict[str, str]:
    resp = client.post("/api/auth/signup", json={"username": username, "password": "password123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _login(client, username: str, password: str) -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _login_admin_headers(client) -> dict[str, str]:
    token = _login(client, "admin", "admin-password-123")
    return {"Authorization": f"Bearer {token}"}


def _upsert_model(client, headers: dict[str, str], model: str, upstream_channel: str):
    resp = client.put(
        f"/api/admin/pricing/models/{model}",
        headers=headers,
        json={
            "upstream_channel": upstream_channel,
            "currency": "USD",
            "is_active": True,
            "input_microusd_per_1m_tokens": 1,
            "cached_input_microusd_per_1m_tokens": 1,
            "output_microusd_per_1m_tokens": 1,
            "cached_output_microusd_per_1m_tokens": 1,
        },
    )
    assert resp.status_code == 200


def _upsert_channel(
    client,
    headers: dict[str, str],
    channel: str,
    *,
    is_enabled: bool,
):
    resp = client.put(
        f"/api/admin/upstream/channels/{channel}",
        headers=headers,
        json={
            "display_name": channel,
            "base_url": "https://example.com/v1",
            "api_key": "sk-test",
            "models_path": "/v1/models",
            "is_enabled": is_enabled,
        },
    )
    assert resp.status_code == 200


def test_models_api_only_returns_models_bound_to_enabled_channels(client):
    suffix = uuid4().hex[:8]
    admin_headers = _login_admin_headers(client)
    user_headers = _signup_headers(client, f"models_user_{suffix}")

    model_unassigned = f"m-default-{suffix}"
    model_disabled = f"m-disabled-{suffix}"
    model_cn = f"m-cn-{suffix}"
    _upsert_model(client, admin_headers, model_unassigned, "")
    _upsert_model(client, admin_headers, model_disabled, "openai-disabled")
    _upsert_model(client, admin_headers, model_cn, "openai-cn")
    _upsert_channel(client, admin_headers, "openai-disabled", is_enabled=False)
    _upsert_channel(client, admin_headers, "openai-cn", is_enabled=True)

    resp = client.get("/api/models", headers=user_headers)
    assert resp.status_code == 200
    rows = resp.json()

    assert all(x["model"] != model_unassigned for x in rows)
    assert all(x["model"] != model_disabled for x in rows)
    row_cn = next(x for x in rows if x["model"] == model_cn)
    assert row_cn["upstream_channel"] == "openai-cn"
    assert row_cn["display_name"] == f"[openai-cn] {model_cn}"
