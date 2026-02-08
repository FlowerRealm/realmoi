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


def test_models_live_api_returns_upstream_models_with_pricing_overlay(client, monkeypatch):
    from backend.app.routers import models as models_router  # noqa: WPS433

    suffix = uuid4().hex[:8]
    admin_headers = _login_admin_headers(client)
    user_headers = _signup_headers(client, f"live_models_user_{suffix}")
    channel = f"realms-{suffix}"
    priced_model = f"gpt-priced-{suffix}"
    unpriced_model = f"gpt-unpriced-{suffix}"

    _upsert_channel(client, admin_headers, channel, is_enabled=True)
    _upsert_model(client, admin_headers, priced_model, channel)

    monkeypatch.setattr(
        models_router,
        "list_upstream_model_ids",
        lambda *, channel, db=None: {priced_model, unpriced_model},
    )

    resp = client.get("/api/models/live", headers=user_headers)
    assert resp.status_code == 200
    rows = resp.json()

    channel_rows = [row for row in rows if row["upstream_channel"] == channel]
    assert len(channel_rows) == 2
    by_model = {row["model"]: row for row in channel_rows}
    assert by_model[priced_model]["upstream_channel"] == channel
    assert by_model[priced_model]["input_microusd_per_1m_tokens"] == 1
    assert by_model[unpriced_model]["upstream_channel"] == channel
    assert by_model[unpriced_model]["input_microusd_per_1m_tokens"] == 0
