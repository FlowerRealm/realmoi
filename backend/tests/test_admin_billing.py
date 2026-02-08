from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4


def _login(client, username: str, password: str) -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _login_admin_headers(client) -> dict[str, str]:
    token = _login(client, "admin", "admin-password-123")
    return {"Authorization": f"Bearer {token}"}


def _signup_user(client, username: str) -> tuple[str, str]:
    resp = client.post("/api/auth/signup", json={"username": username, "password": "password123"})
    assert resp.status_code == 200
    user = resp.json()["user"]
    return user["id"], user["username"]


def _insert_usage_record(
    *,
    owner_user_id: str,
    model: str,
    created_at: datetime,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    cached_output_tokens: int,
    cost_microusd: int | None,
) -> None:
    from backend.app.db import SessionLocal  # noqa: WPS433
    from backend.app.models import UsageRecord  # noqa: WPS433

    with SessionLocal() as db:
        rec = UsageRecord(
            job_id=f"job-{uuid4().hex[:12]}",
            owner_user_id=owner_user_id,
            stage="generate",
            model=model,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            cached_output_tokens=cached_output_tokens,
            currency="USD",
            input_microusd_per_1m_tokens=1 if cost_microusd is not None else None,
            cached_input_microusd_per_1m_tokens=1 if cost_microusd is not None else None,
            output_microusd_per_1m_tokens=1 if cost_microusd is not None else None,
            cached_output_microusd_per_1m_tokens=1 if cost_microusd is not None else None,
            cost_microusd=cost_microusd,
            created_at=created_at,
        )
        db.add(rec)
        db.commit()


def test_admin_billing_summary_range_and_top_users(client):
    admin_headers = _login_admin_headers(client)
    suffix = uuid4().hex[:8]
    shared_model = f"billing-range-model-{suffix}"
    now = datetime.now(tz=timezone.utc)

    user_a_id, user_a_name = _signup_user(client, f"billing_a_{suffix}")
    user_b_id, _ = _signup_user(client, f"billing_b_{suffix}")

    _insert_usage_record(
        owner_user_id=user_a_id,
        model=shared_model,
        created_at=now - timedelta(days=1),
        input_tokens=1_000,
        cached_input_tokens=100,
        output_tokens=500,
        cached_output_tokens=50,
        cost_microusd=300,
    )
    _insert_usage_record(
        owner_user_id=user_b_id,
        model=shared_model,
        created_at=now - timedelta(days=2),
        input_tokens=400,
        cached_input_tokens=20,
        output_tokens=160,
        cached_output_tokens=0,
        cost_microusd=None,
    )
    _insert_usage_record(
        owner_user_id=user_b_id,
        model=shared_model,
        created_at=now - timedelta(days=40),
        input_tokens=4_000,
        cached_input_tokens=400,
        output_tokens=900,
        cached_output_tokens=0,
        cost_microusd=900,
    )

    resp = client.get(
        "/api/admin/billing/summary",
        headers=admin_headers,
        params={
            "model": shared_model,
            "range_days": 7,
            "top_limit": 5,
            "recent_limit": 5,
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"]["records"] == 2
    assert data["total"]["unique_users"] == 2
    assert data["total"]["unique_models"] == 1
    assert data["total"]["cost"]["priced_records"] == 1
    assert data["total"]["cost"]["unpriced_records"] == 1
    assert data["total"]["cost"]["cost_microusd"] == 300
    assert data["total"]["cost"]["amount"] == "0.000300"

    assert len(data["top_users"]) == 2
    assert data["top_users"][0]["label"] == user_a_name
    assert data["top_users"][0]["cost_microusd"] == 300
    assert data["top_users"][1]["cost_microusd"] is None

    assert len(data["recent_records"]) == 2
    assert data["recent_records"][0]["owner_user_id"] == user_a_id
    assert data["recent_records"][0]["amount"] == "0.000300"
    assert data["recent_records"][1]["owner_user_id"] == user_b_id
    assert data["recent_records"][1]["amount"] is None


def test_admin_billing_summary_owner_and_model_filters(client):
    admin_headers = _login_admin_headers(client)
    suffix = uuid4().hex[:8]
    now = datetime.now(tz=timezone.utc)

    owner_id, owner_name = _signup_user(client, f"billing_owner_{suffix}")
    other_id, _ = _signup_user(client, f"billing_other_{suffix}")
    model_a = f"billing-owner-a-{suffix}"
    model_b = f"billing-owner-b-{suffix}"

    _insert_usage_record(
        owner_user_id=owner_id,
        model=model_a,
        created_at=now - timedelta(days=1),
        input_tokens=300,
        cached_input_tokens=10,
        output_tokens=80,
        cached_output_tokens=0,
        cost_microusd=100,
    )
    _insert_usage_record(
        owner_user_id=owner_id,
        model=model_b,
        created_at=now - timedelta(days=2),
        input_tokens=600,
        cached_input_tokens=60,
        output_tokens=200,
        cached_output_tokens=0,
        cost_microusd=250,
    )
    _insert_usage_record(
        owner_user_id=other_id,
        model=model_a,
        created_at=now - timedelta(days=1),
        input_tokens=7_000,
        cached_input_tokens=700,
        output_tokens=1_000,
        cached_output_tokens=0,
        cost_microusd=900,
    )

    resp_owner_only = client.get(
        "/api/admin/billing/summary",
        headers=admin_headers,
        params={
            "owner_user_id": owner_id,
            "range_days": 30,
            "top_limit": 5,
            "recent_limit": 10,
        },
    )
    assert resp_owner_only.status_code == 200
    owner_data = resp_owner_only.json()

    assert owner_data["total"]["records"] == 2
    assert owner_data["total"]["unique_users"] == 1
    assert owner_data["total"]["unique_models"] == 2
    assert len(owner_data["top_users"]) == 1
    assert owner_data["top_users"][0]["label"] == owner_name
    assert len(owner_data["top_models"]) == 2
    assert owner_data["top_models"][0]["key"] == model_b
    assert owner_data["top_models"][0]["cost_microusd"] == 250

    resp_owner_and_model = client.get(
        "/api/admin/billing/summary",
        headers=admin_headers,
        params={
            "owner_user_id": owner_id,
            "model": model_a,
            "range_days": 30,
            "top_limit": 5,
            "recent_limit": 10,
        },
    )
    assert resp_owner_and_model.status_code == 200
    filtered_data = resp_owner_and_model.json()
    assert filtered_data["total"]["records"] == 1
    assert filtered_data["total"]["unique_users"] == 1
    assert filtered_data["total"]["unique_models"] == 1
    assert filtered_data["top_models"][0]["key"] == model_a
    assert filtered_data["recent_records"][0]["owner_user_id"] == owner_id
    assert filtered_data["recent_records"][0]["model"] == model_a
