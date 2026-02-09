from __future__ import annotations

from uuid import uuid4


def test_signup_login_me(client):
    username = f"alice_{uuid4().hex[:8]}"

    # Signup
    resp = client.post("/api/auth/signup", json={"username": username, "password": "password123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "Bearer"
    assert data["user"]["username"] == username
    assert data["user"]["role"] == "user"

    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Me
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["username"] == username

    # Login
    login = client.post("/api/auth/login", json={"username": username, "password": "password123"})
    assert login.status_code == 200


def test_login_invalid_credentials(client):
    resp = client.post("/api/auth/login", json={"username": "nope", "password": "password123"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"
