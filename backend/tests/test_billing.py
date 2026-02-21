from __future__ import annotations

"""User billing API tests.

This file tests:
- `/api/billing/windows`
- `/api/billing/events` (cursor pagination)
- `/api/billing/events/{id}/detail` (permission + breakdown)
- `/api/billing/daily` (trend aggregation + gap filling)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest


def login(client, username: str, password: str) -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def signup_user(client, username: str) -> tuple[str, str]:
    resp = client.post("/api/auth/signup", json={"username": username, "password": "password123"})
    assert resp.status_code == 200
    user = resp.json()["user"]
    return user["id"], user["username"]


@dataclass(frozen=True)
class UsageRecordInsert:
    owner_user_id: str
    model: str
    created_at: datetime
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    cached_output_tokens: int
    cost_microusd: int | None
    input_price: int | None = None
    cached_input_price: int | None = None
    output_price: int | None = None
    cached_output_price: int | None = None


def insert_usage_record(record: UsageRecordInsert) -> str:
    from backend.app.db import SessionLocal  # noqa: WPS433
    from backend.app.models import UsageRecord  # noqa: WPS433

    with SessionLocal() as db:
        rec = UsageRecord(
            job_id=f"job-{uuid4().hex[:12]}",
            owner_user_id=record.owner_user_id,
            stage="generate",
            model=record.model,
            input_tokens=record.input_tokens,
            cached_input_tokens=record.cached_input_tokens,
            output_tokens=record.output_tokens,
            cached_output_tokens=record.cached_output_tokens,
            currency="USD",
            input_microusd_per_1m_tokens=record.input_price,
            cached_input_microusd_per_1m_tokens=record.cached_input_price,
            output_microusd_per_1m_tokens=record.output_price,
            cached_output_microusd_per_1m_tokens=record.cached_output_price,
            cost_microusd=record.cost_microusd,
            created_at=record.created_at,
        )
        db.add(rec)
        try:
            db.commit()
            db.refresh(rec)
        except Exception:
            db.rollback()
            raise
        return rec.id


def test_billing_windows_and_events_cursor(client):
    suffix = uuid4().hex[:8]
    now = datetime.now(tz=timezone.utc)
    start = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")

    owner_id, owner_username = signup_user(client, f"billing_user_{suffix}")
    other_id, _ = signup_user(client, f"billing_other_{suffix}")
    model = f"billing-model-{suffix}"

    newest_id = insert_usage_record(
        UsageRecordInsert(
            owner_user_id=owner_id,
            model=model,
            created_at=now - timedelta(hours=1),
            input_tokens=1_000,
            cached_input_tokens=200,
            output_tokens=300,
            cached_output_tokens=40,
            cost_microusd=250,
            input_price=1,
            cached_input_price=1,
            output_price=1,
            cached_output_price=1,
        )
    )
    insert_usage_record(
        UsageRecordInsert(
            owner_user_id=owner_id,
            model=model,
            created_at=now - timedelta(hours=3),
            input_tokens=500,
            cached_input_tokens=10,
            output_tokens=200,
            cached_output_tokens=0,
            cost_microusd=None,
        )
    )
    insert_usage_record(
        UsageRecordInsert(
            owner_user_id=owner_id,
            model=model,
            created_at=now - timedelta(days=9),
            input_tokens=9_000,
            cached_input_tokens=900,
            output_tokens=1_500,
            cached_output_tokens=0,
            cost_microusd=900,
            input_price=1,
            cached_input_price=1,
            output_price=1,
            cached_output_price=1,
        )
    )
    insert_usage_record(
        UsageRecordInsert(
            owner_user_id=other_id,
            model=model,
            created_at=now - timedelta(hours=2),
            input_tokens=9_999,
            cached_input_tokens=999,
            output_tokens=999,
            cached_output_tokens=99,
            cost_microusd=999,
            input_price=1,
            cached_input_price=1,
            output_price=1,
            cached_output_price=1,
        )
    )

    token = login(client, owner_username, "password123")
    headers = {"Authorization": f"Bearer {token}"}

    resp_windows = client.get(
        "/api/billing/windows",
        headers=headers,
        params={"start": start, "end": end},
    )
    assert resp_windows.status_code == 200
    data_windows = resp_windows.json()
    assert data_windows["query"]["start"] == start
    assert data_windows["query"]["end"] == end
    window = data_windows["windows"][0]
    assert window["records"] == 2
    assert window["input_tokens"] == 1_500
    assert window["cached_input_tokens"] == 210
    assert window["output_tokens"] == 500
    assert window["cached_output_tokens"] == 40
    assert window["cost"]["priced_records"] == 1
    assert window["cost"]["unpriced_records"] == 1
    assert window["cost"]["cost_microusd"] == 250
    assert window["cost"]["amount"] == "0.000250"

    resp_page_1 = client.get(
        "/api/billing/events",
        headers=headers,
        params={"start": start, "end": end, "limit": 1},
    )
    assert resp_page_1.status_code == 200
    data_page_1 = resp_page_1.json()
    assert len(data_page_1["events"]) == 1
    assert data_page_1["events"][0]["id"] == newest_id
    assert data_page_1["events"][0]["cost"]["cost_microusd"] == 250
    assert data_page_1["next_before_id"]

    resp_page_2 = client.get(
        "/api/billing/events",
        headers=headers,
        params={
            "start": start,
            "end": end,
            "limit": 2,
            "before_id": data_page_1["next_before_id"],
        },
    )
    assert resp_page_2.status_code == 200
    data_page_2 = resp_page_2.json()
    assert len(data_page_2["events"]) == 1
    assert data_page_2["events"][0]["cost"] is None


def test_billing_event_detail_and_record_permission(client):
    suffix = uuid4().hex[:8]
    now = datetime.now(tz=timezone.utc)

    owner_id, owner_username = signup_user(client, f"billing_owner_{suffix}")
    other_id, _ = signup_user(client, f"billing_other_{suffix}")
    model = f"billing-detail-model-{suffix}"

    own_record_id = insert_usage_record(
        UsageRecordInsert(
            owner_user_id=owner_id,
            model=model,
            created_at=now - timedelta(minutes=30),
            input_tokens=1_200_000,
            cached_input_tokens=200_000,
            output_tokens=800_000,
            cached_output_tokens=100_000,
            cost_microusd=4,
            input_price=2,
            cached_input_price=1,
            output_price=4,
            cached_output_price=1,
        )
    )
    other_record_id = insert_usage_record(
        UsageRecordInsert(
            owner_user_id=other_id,
            model=model,
            created_at=now - timedelta(minutes=20),
            input_tokens=100,
            cached_input_tokens=0,
            output_tokens=50,
            cached_output_tokens=0,
            cost_microusd=1,
            input_price=1,
            cached_input_price=1,
            output_price=1,
            cached_output_price=1,
        )
    )

    token = login(client, owner_username, "password123")
    headers = {"Authorization": f"Bearer {token}"}

    resp_detail = client.get(
        f"/api/billing/events/{own_record_id}/detail",
        headers=headers,
    )
    assert resp_detail.status_code == 200
    data_detail = resp_detail.json()
    assert data_detail["id"] == own_record_id
    assert data_detail["pricing"]["input_microusd_per_1m_tokens"] == 2
    assert data_detail["pricing"]["cached_input_microusd_per_1m_tokens"] == 1
    assert data_detail["pricing"]["output_microusd_per_1m_tokens"] == 4
    assert data_detail["pricing"]["cached_output_microusd_per_1m_tokens"] == 1
    assert data_detail["breakdown"]["non_cached_input"]["tokens"] == 1_000_000
    assert data_detail["breakdown"]["non_cached_output"]["tokens"] == 700_000
    assert data_detail["breakdown"]["cached_input"]["tokens"] == 200_000
    assert data_detail["breakdown"]["cached_output"]["tokens"] == 100_000
    assert data_detail["breakdown"]["computed_total_microusd"] == 4
    assert data_detail["breakdown"]["computed_total_amount"] == "0.000004"

    resp_other = client.get(
        f"/api/billing/events/{other_record_id}/detail",
        headers=headers,
    )
    assert resp_other.status_code == 404


def test_billing_daily_trend_aggregates_and_fills_missing_days(client):
    suffix = uuid4().hex[:8]
    owner_id, owner_username = signup_user(client, f"billing_daily_{suffix}")
    other_id, _ = signup_user(client, f"billing_daily_other_{suffix}")
    model = f"billing-daily-model-{suffix}"

    inserts = [
        UsageRecordInsert(
            owner_user_id=owner_id,
            model=model,
            created_at=datetime(2026, 1, 10, 10, 30, tzinfo=timezone.utc),
            input_tokens=100,
            cached_input_tokens=20,
            output_tokens=50,
            cached_output_tokens=10,
            cost_microusd=100,
            input_price=1,
            cached_input_price=1,
            output_price=1,
            cached_output_price=1,
        ),
        UsageRecordInsert(
            owner_user_id=owner_id,
            model=model,
            created_at=datetime(2026, 1, 12, 8, 0, tzinfo=timezone.utc),
            input_tokens=200,
            cached_input_tokens=0,
            output_tokens=100,
            cached_output_tokens=0,
            cost_microusd=None,
        ),
        UsageRecordInsert(
            owner_user_id=owner_id,
            model=model,
            created_at=datetime(2026, 1, 12, 18, 45, tzinfo=timezone.utc),
            input_tokens=300,
            cached_input_tokens=100,
            output_tokens=200,
            cached_output_tokens=50,
            cost_microusd=300,
            input_price=1,
            cached_input_price=1,
            output_price=1,
            cached_output_price=1,
        ),
        UsageRecordInsert(
            owner_user_id=other_id,
            model=model,
            created_at=datetime(2026, 1, 12, 9, 0, tzinfo=timezone.utc),
            input_tokens=9_999,
            cached_input_tokens=999,
            output_tokens=9_999,
            cached_output_tokens=999,
            cost_microusd=999,
            input_price=1,
            cached_input_price=1,
            output_price=1,
            cached_output_price=1,
        ),
    ]
    for r in inserts:
        insert_usage_record(r)

    token = login(client, owner_username, "password123")
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get(
        "/api/billing/daily",
        headers=headers,
        params={"start": "2026-01-10", "end": "2026-01-13"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"]["start"] == "2026-01-10"
    assert data["query"]["end"] == "2026-01-13"
    assert len(data["points"]) == 4

    day_10 = data["points"][0]
    assert day_10["day"] == "2026-01-10"
    assert day_10["records"] == 1
    assert day_10["total_tokens"] == 150
    assert day_10["cached_tokens"] == 30
    assert day_10["cache_ratio"] == pytest.approx(0.2)
    assert day_10["cost"]["priced_records"] == 1
    assert day_10["cost"]["unpriced_records"] == 0
    assert day_10["cost"]["cost_microusd"] == 100
    assert day_10["cost"]["amount"] == "0.000100"

    day_11 = data["points"][1]
    assert day_11["day"] == "2026-01-11"
    assert day_11["records"] == 0
    assert day_11["total_tokens"] == 0
    assert day_11["cache_ratio"] == 0
    assert day_11["cost"]["priced_records"] == 0
    assert day_11["cost"]["unpriced_records"] == 0
    assert day_11["cost"]["cost_microusd"] is None

    day_12 = data["points"][2]
    assert day_12["day"] == "2026-01-12"
    assert day_12["records"] == 2
    assert day_12["input_tokens"] == 500
    assert day_12["cached_input_tokens"] == 100
    assert day_12["output_tokens"] == 300
    assert day_12["cached_output_tokens"] == 50
    assert day_12["total_tokens"] == 800
    assert day_12["cached_tokens"] == 150
    assert day_12["cache_ratio"] == pytest.approx(0.1875)
    assert day_12["cost"]["priced_records"] == 1
    assert day_12["cost"]["unpriced_records"] == 1
    assert day_12["cost"]["cost_microusd"] == 300
    assert day_12["cost"]["amount"] == "0.000300"

    day_13 = data["points"][3]
    assert day_13["day"] == "2026-01-13"
    assert day_13["records"] == 0
    assert day_13["cost"]["cost_microusd"] is None
