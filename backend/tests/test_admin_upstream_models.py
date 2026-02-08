from __future__ import annotations

from uuid import uuid4


def _login(client, username: str, password: str) -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _login_admin_headers(client) -> dict[str, str]:
    token = _login(client, "admin", "admin-password-123")
    return {"Authorization": f"Bearer {token}"}


class _FakeHttpxResponse:
    def __init__(self, *, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_upstream_models_supports_channel_query(client, monkeypatch):
    from backend.app.routers import admin as admin_router  # noqa: WPS433

    admin_headers = _login_admin_headers(client)
    admin_router._models_cache.clear()

    put_resp = client.put(
        "/api/admin/upstream/channels/openai-cn",
        headers=admin_headers,
        json={
            "display_name": "openai-cn",
            "base_url": "https://cn.example.com/v1",
            "api_key": "sk-cn",
            "models_path": "/v1/models",
            "is_enabled": True,
        },
    )
    assert put_resp.status_code == 200

    captured: dict[str, str] = {}

    def _fake_get(url: str, headers: dict[str, str], timeout: int, trust_env: bool):
        captured["url"] = url
        captured["authorization"] = headers.get("Authorization") or ""
        captured["timeout"] = str(timeout)
        captured["trust_env"] = str(trust_env)
        return _FakeHttpxResponse(status_code=200, payload={"data": [{"id": "model-cn"}]})

    monkeypatch.setattr(admin_router.httpx, "get", _fake_get)

    resp = client.get("/api/admin/upstream/models", headers=admin_headers, params={"channel": "openai-cn"})
    assert resp.status_code == 200
    assert resp.json()["data"][0]["id"] == "model-cn"
    assert captured["url"] == "https://cn.example.com/v1/models"
    assert captured["authorization"] == "Bearer sk-cn"
    assert captured["timeout"] == "20"
    assert captured["trust_env"] == "False"


def test_upstream_models_unknown_channel_returns_422(client, monkeypatch):
    from backend.app.routers import admin as admin_router  # noqa: WPS433
    from backend.app.settings import SETTINGS  # noqa: WPS433

    admin_headers = _login_admin_headers(client)
    admin_router._models_cache.clear()
    monkeypatch.setattr(SETTINGS, "upstream_channels_json", "{}")

    resp = client.get("/api/admin/upstream/models", headers=admin_headers, params={"channel": "not-exists"})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "invalid_request"
    assert "Unknown upstream channel" in err["message"]


def test_upstream_channels_returns_configured_named_channels(client, monkeypatch):
    from backend.app.settings import SETTINGS  # noqa: WPS433

    admin_headers = _login_admin_headers(client)
    monkeypatch.setattr(
        SETTINGS,
        "upstream_channels_json",
        '{"openai-cn":{"base_url":"https://cn.example.com/v1","api_key":"sk-cn"},"openai-us":{"api_key":"sk-us"}}',
    )

    resp = client.get("/api/admin/upstream/channels", headers=admin_headers)
    assert resp.status_code == 200
    items = resp.json()
    channels = {x["channel"] for x in items}
    assert "openai-cn" in channels
    assert "openai-us" in channels
    assert "" not in channels


def test_upstream_channel_can_be_created_and_updated(client):
    admin_headers = _login_admin_headers(client)
    channel = f"openai-jp-{uuid4().hex[:6]}"
    model_base_url = "https://jp.example.com/v1"
    model_api_key = "sk-jp-1"

    put_resp = client.put(
        f"/api/admin/upstream/channels/{channel}",
        headers=admin_headers,
        json={
            "display_name": "东京线路",
            "base_url": model_base_url,
            "api_key": model_api_key,
            "models_path": "/v1/models",
            "is_enabled": True,
        },
    )
    assert put_resp.status_code == 200

    list_resp = client.get("/api/admin/upstream/channels", headers=admin_headers)
    assert list_resp.status_code == 200
    rows = list_resp.json()
    row = next(x for x in rows if x["channel"] == channel)
    assert row["display_name"] == "东京线路"
    assert row["base_url"] == model_base_url
    assert row["has_api_key"] is True
    assert row["api_key_masked"] != model_api_key
    assert row["is_enabled"] is True
    assert row["source"] == "db"

    put_resp_2 = client.put(
        f"/api/admin/upstream/channels/{channel}",
        headers=admin_headers,
        json={
            "display_name": "东京线路-2",
            "base_url": "https://jp2.example.com/v1",
            "models_path": "/v1/models",
            "is_enabled": False,
        },
    )
    assert put_resp_2.status_code == 200

    list_resp_2 = client.get("/api/admin/upstream/channels", headers=admin_headers)
    assert list_resp_2.status_code == 200
    rows_2 = list_resp_2.json()
    row_2 = next(x for x in rows_2 if x["channel"] == channel)
    assert row_2["display_name"] == "东京线路-2"
    assert row_2["base_url"] == "https://jp2.example.com/v1"
    # api_key omitted in second update, should keep old value.
    assert row_2["has_api_key"] is True
    assert row_2["api_key_masked"] == row["api_key_masked"]
    assert row_2["is_enabled"] is False


def test_upstream_channel_can_be_deleted_when_unused(client):
    admin_headers = _login_admin_headers(client)
    channel = f"openai-del-{uuid4().hex[:6]}"

    put_resp = client.put(
        f"/api/admin/upstream/channels/{channel}",
        headers=admin_headers,
        json={
            "display_name": "可删除",
            "base_url": "https://del.example.com/v1",
            "api_key": "sk-del",
            "models_path": "/v1/models",
            "is_enabled": True,
        },
    )
    assert put_resp.status_code == 200

    delete_resp = client.delete(f"/api/admin/upstream/channels/{channel}", headers=admin_headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["ok"] is True

    list_resp = client.get("/api/admin/upstream/channels", headers=admin_headers)
    assert list_resp.status_code == 200
    rows = list_resp.json()
    channels = {x["channel"] for x in rows}
    assert channel not in channels


def test_upstream_channel_delete_in_use_returns_409(client):
    admin_headers = _login_admin_headers(client)
    suffix = uuid4().hex[:6]
    channel = f"openai-used-{suffix}"
    model = f"model-used-{suffix}"

    put_resp = client.put(
        f"/api/admin/upstream/channels/{channel}",
        headers=admin_headers,
        json={
            "display_name": "在用渠道",
            "base_url": "https://used.example.com/v1",
            "api_key": "sk-used",
            "models_path": "/v1/models",
            "is_enabled": True,
        },
    )
    assert put_resp.status_code == 200

    pricing_resp = client.put(
        f"/api/admin/pricing/models/{model}",
        headers=admin_headers,
        json={
            "upstream_channel": channel,
            "currency": "USD",
            "is_active": False,
        },
    )
    assert pricing_resp.status_code == 200

    delete_resp = client.delete(f"/api/admin/upstream/channels/{channel}", headers=admin_headers)
    assert delete_resp.status_code == 409
    err = delete_resp.json()["error"]
    assert err["code"] == "conflict"
    assert "Channel in use" in err["message"]


def test_upstream_channel_delete_not_found_returns_404(client):
    admin_headers = _login_admin_headers(client)

    delete_resp = client.delete("/api/admin/upstream/channels/not-exists", headers=admin_headers)
    assert delete_resp.status_code == 404
    err = delete_resp.json()["error"]
    assert err["code"] == "not_found"


def test_upstream_channel_delete_default_returns_422(client):
    admin_headers = _login_admin_headers(client)

    delete_resp = client.delete("/api/admin/upstream/channels/default", headers=admin_headers)
    assert delete_resp.status_code == 422
    err = delete_resp.json()["error"]
    assert err["code"] == "invalid_request"
