from __future__ import annotations

from uuid import uuid4


def _login(client, username: str, password: str) -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _login_admin_headers(client) -> dict[str, str]:
    token = _login(client, "admin", "admin-password-123")
    return {"Authorization": f"Bearer {token}"}


def test_admin_users_create_list_patch_and_reset_password(client):
    admin_headers = _login_admin_headers(client)
    suffix = uuid4().hex[:8]
    username = f"admin_users_{suffix}"

    create_resp = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={"username": username, "password": "password123", "role": "user"},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()

    assert created["username"] == username
    assert created["role"] == "user"
    assert created["is_disabled"] is False
    assert "id" in created and created["id"]
    user_id = created["id"]

    list_resp = client.get("/api/admin/users", headers=admin_headers, params={"q": username, "limit": 50, "offset": 0})
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert listed["total"] >= 1
    assert any(row["id"] == user_id for row in listed["items"])

    role_user_resp = client.get("/api/admin/users", headers=admin_headers, params={"q": username, "role": "user"})
    assert role_user_resp.status_code == 200
    assert any(row["id"] == user_id for row in role_user_resp.json()["items"])

    patch_role_resp = client.patch(f"/api/admin/users/{user_id}", headers=admin_headers, json={"role": "admin"})
    assert patch_role_resp.status_code == 200

    role_admin_resp = client.get("/api/admin/users", headers=admin_headers, params={"q": username, "role": "admin"})
    assert role_admin_resp.status_code == 200
    assert any(row["id"] == user_id for row in role_admin_resp.json()["items"])

    disable_resp = client.patch(f"/api/admin/users/{user_id}", headers=admin_headers, json={"is_disabled": True})
    assert disable_resp.status_code == 200

    disabled_list_resp = client.get(
        "/api/admin/users",
        headers=admin_headers,
        params={"q": username, "is_disabled": True},
    )
    assert disabled_list_resp.status_code == 200
    assert any(row["id"] == user_id and row["is_disabled"] is True for row in disabled_list_resp.json()["items"])

    reset_resp = client.post(
        f"/api/admin/users/{user_id}/reset_password",
        headers=admin_headers,
        json={"new_password": "new-password-123"},
    )
    assert reset_resp.status_code == 200

    enable_resp = client.patch(f"/api/admin/users/{user_id}", headers=admin_headers, json={"is_disabled": False})
    assert enable_resp.status_code == 200

    login_new_password = client.post("/api/auth/login", json={"username": username, "password": "new-password-123"})
    assert login_new_password.status_code == 200


def test_admin_users_create_validation_and_conflicts(client):
    admin_headers = _login_admin_headers(client)
    suffix = uuid4().hex[:8]
    username = f"admin_users_conflict_{suffix}"

    invalid_username = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={"username": "x!", "password": "password123", "role": "user"},
    )
    assert invalid_username.status_code == 422

    invalid_password = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={"username": username, "password": "short", "role": "user"},
    )
    assert invalid_password.status_code == 422

    invalid_role = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={"username": username, "password": "password123", "role": "superadmin"},
    )
    assert invalid_role.status_code == 422

    ok_create = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={"username": username, "password": "password123", "role": "user"},
    )
    assert ok_create.status_code == 201

    conflict_create = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={"username": username, "password": "password123", "role": "user"},
    )
    assert conflict_create.status_code == 409

    invalid_list_role = client.get("/api/admin/users", headers=admin_headers, params={"role": "superadmin"})
    assert invalid_list_role.status_code == 422

