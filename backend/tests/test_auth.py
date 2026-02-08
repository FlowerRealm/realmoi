from __future__ import annotations


def test_signup_login_me(client):
    # Signup
    resp = client.post("/api/auth/signup", json={"username": "alice", "password": "password123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "Bearer"
    assert data["user"]["username"] == "alice"
    assert data["user"]["role"] == "user"

    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Me
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["username"] == "alice"

    # Login
    login = client.post("/api/auth/login", json={"username": "alice", "password": "password123"})
    assert login.status_code == 200


def test_login_invalid_credentials(client):
    resp = client.post("/api/auth/login", json={"username": "nope", "password": "password123"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"

