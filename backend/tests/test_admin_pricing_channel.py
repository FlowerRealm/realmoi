from __future__ import annotations

from uuid import uuid4


def _login(client, username: str, password: str) -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _login_admin_headers(client) -> dict[str, str]:
    token = _login(client, "admin", "admin-password-123")
    return {"Authorization": f"Bearer {token}"}


def test_admin_can_set_and_update_upstream_channel(client):
    admin_headers = _login_admin_headers(client)
    model = f"pricing-channel-{uuid4().hex[:8]}"

    put_resp = client.put(
        f"/api/admin/pricing/models/{model}",
        headers=admin_headers,
        json={
            "upstream_channel": "  openai-cn  ",
            "currency": "USD",
            "is_active": False,
        },
    )
    assert put_resp.status_code == 200

    list_resp = client.get("/api/admin/pricing/models", headers=admin_headers)
    assert list_resp.status_code == 200
    items = list_resp.json()
    row = next(item for item in items if item["model"] == model)
    assert row["upstream_channel"] == "openai-cn"

    put_resp_2 = client.put(
        f"/api/admin/pricing/models/{model}",
        headers=admin_headers,
        json={
            "currency": "USD",
            "is_active": False,
        },
    )
    assert put_resp_2.status_code == 200

    list_resp_2 = client.get("/api/admin/pricing/models", headers=admin_headers)
    assert list_resp_2.status_code == 200
    items_2 = list_resp_2.json()
    row_2 = next(item for item in items_2 if item["model"] == model)
    assert row_2["upstream_channel"] == "openai-cn"
