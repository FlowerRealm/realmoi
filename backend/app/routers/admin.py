from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select

from ..auth import hash_password
from ..deps import AdminUserDep, DbDep
from ..models import ModelPricing, UpstreamChannel, UsageRecord, User
from ..services.pricing import microusd_to_amount_str
from ..services import upstream_models as upstream_models_service
from ..services.upstream_models import UpstreamModelsError, fetch_upstream_models_payload
from ..services.upstream_channels import list_upstream_channels
from ..settings import SETTINGS
from ..utils.errors import http_error


router = APIRouter(prefix="/admin", tags=["admin"])

# Backward-compatible alias for tests/tools that clear admin upstream cache.
_models_cache = upstream_models_service._models_cache
httpx = upstream_models_service.httpx


class UserItem(BaseModel):
    id: str
    username: str
    role: str
    is_disabled: bool
    created_at: datetime


class UsersListResponse(BaseModel):
    items: list[UserItem]
    total: int


@router.get("/users", response_model=UsersListResponse)
def list_users(_: AdminUserDep, db: DbDep, q: str | None = None, limit: int = 50, offset: int = 0):
    stmt = select(User).order_by(User.created_at.desc())
    if q:
        stmt = stmt.where(User.username.like(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(stmt.limit(limit).offset(offset)).all()
    return UsersListResponse(
        items=[UserItem.model_validate(u, from_attributes=True) for u in items],
        total=total,
    )


class PatchUserRequest(BaseModel):
    is_disabled: bool | None = None
    role: str | None = None


@router.patch("/users/{user_id}")
def patch_user(admin: AdminUserDep, db: DbDep, user_id: str, req: PatchUserRequest):
    user = db.get(User, user_id)
    if not user:
        http_error(404, "not_found", "User not found")

    if user.id == admin.id and req.is_disabled:
        http_error(409, "conflict", "Cannot disable yourself")

    if req.role and req.role not in ("user", "admin"):
        http_error(422, "invalid_request", "Invalid role")

    # Ensure at least one active admin.
    if (req.role == "user" or req.is_disabled is True) and user.role == "admin" and not user.is_disabled:
        active_admins = db.scalar(
            select(func.count()).select_from(User).where(and_(User.role == "admin", User.is_disabled == False))  # noqa: E712
        )
        if (active_admins or 0) <= 1:
            http_error(409, "conflict", "Must keep at least one active admin")

    if req.is_disabled is not None:
        user.is_disabled = req.is_disabled
    if req.role is not None:
        user.role = req.role
    db.add(user)
    db.commit()
    return {"ok": True}


class ResetPasswordRequest(BaseModel):
    new_password: str


@router.post("/users/{user_id}/reset_password")
def reset_password(_: AdminUserDep, db: DbDep, user_id: str, req: ResetPasswordRequest):
    if not (8 <= len(req.new_password) <= 72):
        http_error(422, "invalid_request", "Invalid password length")
    user = db.get(User, user_id)
    if not user:
        http_error(404, "not_found", "User not found")
    user.password_hash = hash_password(req.new_password)
    db.add(user)
    db.commit()
    return {"ok": True}


class UpstreamChannelItem(BaseModel):
    channel: str
    display_name: str
    base_url: str
    api_key_masked: str
    has_api_key: bool
    models_path: str
    is_default: bool
    is_enabled: bool
    source: str


def _mask_api_key(value: str) -> str:
    s = value.strip()
    if not s:
        return ""
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}...{s[-4:]}"


@router.get("/upstream/channels", response_model=list[UpstreamChannelItem])
def upstream_channels(_: AdminUserDep, db: DbDep):
    items: list[UpstreamChannelItem] = []
    try:
        channels = list_upstream_channels(db=db, include_disabled=True)
    except ValueError as e:
        http_error(500, "server_misconfigured", str(e))
    for channel in channels:
        items.append(
            UpstreamChannelItem(
                channel=channel.channel,
                display_name=channel.display_name,
                base_url=channel.base_url,
                api_key_masked=_mask_api_key(channel.api_key),
                has_api_key=bool(channel.api_key.strip()),
                models_path=channel.models_path,
                is_default=False,
                is_enabled=channel.is_enabled,
                source=channel.source,
            )
        )
    return items


class UpsertUpstreamChannelRequest(BaseModel):
    display_name: str | None = None
    base_url: str
    api_key: str | None = None
    models_path: str = "/v1/models"
    is_enabled: bool = True


def _normalize_models_path(path: str) -> str:
    p = path.strip()
    if not p:
        p = SETTINGS.upstream_models_path
    if not p.startswith("/"):
        p = f"/{p}"
    return p


@router.put("/upstream/channels/{channel}")
def upsert_upstream_channel(_: AdminUserDep, db: DbDep, channel: str, req: UpsertUpstreamChannelRequest):
    channel_key = channel.strip()
    if not channel_key:
        http_error(422, "invalid_request", "Invalid channel")
    if channel_key.lower() == "default":
        http_error(422, "invalid_request", "Channel name 'default' is reserved")

    base_url = req.base_url.strip()
    if not base_url:
        http_error(422, "invalid_request", "Missing base_url")

    row = db.get(UpstreamChannel, channel_key)
    api_key_value = req.api_key.strip() if req.api_key is not None else None
    if row is None and (api_key_value is None or not api_key_value):
        http_error(422, "invalid_request", "Missing api_key")

    if row is None:
        row = UpstreamChannel(channel=channel_key)

    row.display_name = (req.display_name or "").strip() or channel_key
    row.base_url = base_url
    if api_key_value:
        row.api_key = api_key_value
    elif not row.api_key:
        http_error(422, "invalid_request", "Missing api_key")
    row.models_path = _normalize_models_path(req.models_path)
    row.is_enabled = bool(req.is_enabled)

    db.add(row)
    db.commit()
    return {"ok": True}


@router.delete("/upstream/channels/{channel}")
def delete_upstream_channel(_: AdminUserDep, db: DbDep, channel: str):
    channel_key = channel.strip()
    if not channel_key:
        http_error(422, "invalid_request", "Invalid channel")
    if channel_key.lower() == "default":
        http_error(422, "invalid_request", "Channel name 'default' is reserved")

    row = db.get(UpstreamChannel, channel_key)
    if row is None:
        http_error(404, "not_found", "Upstream channel not found")

    used_count = db.scalar(
        select(func.count()).select_from(ModelPricing).where(ModelPricing.upstream_channel == channel_key)
    ) or 0
    if used_count > 0:
        http_error(409, "conflict", f"Channel in use by {used_count} model(s)")

    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/upstream/models")
def upstream_models(_: AdminUserDep, db: DbDep, channel: str | None = Query(default=None, max_length=64)):
    try:
        return fetch_upstream_models_payload(channel=channel, db=db)
    except UpstreamModelsError as e:
        if e.code == "unknown_upstream_channel":
            http_error(422, "invalid_request", f"Unknown upstream channel: {e.message}")
        if e.code == "disabled_upstream_channel":
            http_error(422, "invalid_request", f"Disabled upstream channel: {e.message}")
        if e.code == "missing_upstream_api_key":
            http_error(401, "upstream_unauthorized", "Missing upstream API key")
        if e.code == "upstream_unauthorized":
            http_error(401, "upstream_unauthorized", "Upstream unauthorized")
        if e.code == "upstream_bad_response":
            http_error(502, "upstream_bad_response", e.message)
        if e.code == "upstream_unavailable":
            http_error(503, "upstream_unavailable", f"Upstream unavailable: {e.message}")
        http_error(500, "server_misconfigured", e.message)


class PricingItem(BaseModel):
    model: str
    upstream_channel: str = ""
    currency: str
    unit: str
    is_active: bool
    input_microusd_per_1m_tokens: int | None = None
    cached_input_microusd_per_1m_tokens: int | None = None
    output_microusd_per_1m_tokens: int | None = None
    cached_output_microusd_per_1m_tokens: int | None = None


@router.get("/pricing/models", response_model=list[PricingItem])
def list_pricing_models(_: AdminUserDep, db: DbDep):
    items = db.scalars(select(ModelPricing).order_by(ModelPricing.model.asc())).all()
    return [PricingItem.model_validate(x, from_attributes=True) for x in items]


class UpsertPricingRequest(BaseModel):
    upstream_channel: str | None = None
    currency: str = "USD"
    is_active: bool = False
    input_microusd_per_1m_tokens: int | None = None
    cached_input_microusd_per_1m_tokens: int | None = None
    output_microusd_per_1m_tokens: int | None = None
    cached_output_microusd_per_1m_tokens: int | None = None


@router.put("/pricing/models/{model}")
def upsert_pricing_model(_: AdminUserDep, db: DbDep, model: str, req: UpsertPricingRequest):
    for v in (
        req.input_microusd_per_1m_tokens,
        req.cached_input_microusd_per_1m_tokens,
        req.output_microusd_per_1m_tokens,
        req.cached_output_microusd_per_1m_tokens,
    ):
        if v is not None and v < 0:
            http_error(422, "invalid_request", "Prices must be >= 0")

    if req.is_active and any(
        v is None
        for v in (
            req.input_microusd_per_1m_tokens,
            req.cached_input_microusd_per_1m_tokens,
            req.output_microusd_per_1m_tokens,
            req.cached_output_microusd_per_1m_tokens,
        )
    ):
        http_error(422, "invalid_request", "Missing prices; cannot activate")

    item = db.get(ModelPricing, model)
    if not item:
        item = ModelPricing(model=model)

    if req.upstream_channel is not None:
        item.upstream_channel = req.upstream_channel.strip()
    elif not item.upstream_channel:
        item.upstream_channel = ""

    item.currency = req.currency
    item.is_active = req.is_active
    item.input_microusd_per_1m_tokens = req.input_microusd_per_1m_tokens
    item.cached_input_microusd_per_1m_tokens = req.cached_input_microusd_per_1m_tokens
    item.output_microusd_per_1m_tokens = req.output_microusd_per_1m_tokens
    item.cached_output_microusd_per_1m_tokens = req.cached_output_microusd_per_1m_tokens

    db.add(item)
    db.commit()
    return {"ok": True}


class BillingQueryInfo(BaseModel):
    owner_user_id: str | None = None
    model: str | None = None
    range_days: int | None = None
    top_limit: int
    recent_limit: int
    since: datetime | None = None


class BillingCostSummary(BaseModel):
    currency: str = "USD"
    cost_microusd: int | None = None
    amount: str | None = None
    priced_records: int
    unpriced_records: int


class BillingTotalSummary(BaseModel):
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    cached_output_tokens: int
    records: int
    unique_users: int
    unique_models: int
    cost: BillingCostSummary


class BillingBreakdownItem(BaseModel):
    key: str
    label: str | None = None
    records: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    cached_output_tokens: int
    cost_microusd: int | None = None
    amount: str | None = None
    priced_records: int
    unpriced_records: int


class BillingRecentRecord(BaseModel):
    id: str
    created_at: datetime
    owner_user_id: str
    username: str | None = None
    job_id: str
    stage: str
    model: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    cached_output_tokens: int
    cost_microusd: int | None = None
    amount: str | None = None


class AdminBillingSummaryResponse(BaseModel):
    query: BillingQueryInfo
    total: BillingTotalSummary
    top_users: list[BillingBreakdownItem]
    top_models: list[BillingBreakdownItem]
    recent_records: list[BillingRecentRecord]


def _bucket_seed() -> dict[str, int]:
    return {
        "records": 0,
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "cached_output_tokens": 0,
        "cost_microusd": 0,
        "priced_records": 0,
        "unpriced_records": 0,
    }


def _resolved_cost(cost_microusd: int, priced_records: int) -> int | None:
    if priced_records <= 0:
        return None
    return cost_microusd


def _bucket_rank(row: tuple[str, dict[str, int]]) -> tuple[int, int, int]:
    data = row[1]
    total_io = data["input_tokens"] + data["output_tokens"]
    return (data["cost_microusd"], total_io, data["records"])


@router.get("/billing/summary", response_model=AdminBillingSummaryResponse)
def admin_billing_summary(
    _: AdminUserDep,
    db: DbDep,
    owner_user_id: str | None = None,
    model: str | None = None,
    range_days: int | None = Query(default=None, ge=1, le=3650),
    top_limit: int = Query(default=8, ge=1, le=50),
    recent_limit: int = Query(default=20, ge=1, le=200),
):
    stmt = select(UsageRecord)
    if owner_user_id:
        stmt = stmt.where(UsageRecord.owner_user_id == owner_user_id)
    if model:
        stmt = stmt.where(UsageRecord.model == model)
    since: datetime | None = None
    if range_days is not None:
        since = datetime.now(tz=timezone.utc) - timedelta(days=range_days)
        stmt = stmt.where(UsageRecord.created_at >= since)

    rows = db.scalars(stmt).all()
    rows_sorted = sorted(rows, key=lambda r: r.created_at, reverse=True)

    user_groups: dict[str, dict[str, int]] = defaultdict(_bucket_seed)
    model_groups: dict[str, dict[str, int]] = defaultdict(_bucket_seed)

    total_input = 0
    total_cached_input = 0
    total_output = 0
    total_cached_output = 0
    total_cost_microusd = 0
    total_priced_records = 0
    total_unpriced_records = 0

    for row in rows:
        total_input += row.input_tokens
        total_cached_input += row.cached_input_tokens
        total_output += row.output_tokens
        total_cached_output += row.cached_output_tokens

        is_priced = row.cost_microusd is not None
        if is_priced:
            total_priced_records += 1
            total_cost_microusd += int(row.cost_microusd or 0)
        else:
            total_unpriced_records += 1

        user_bucket = user_groups[row.owner_user_id]
        user_bucket["records"] += 1
        user_bucket["input_tokens"] += row.input_tokens
        user_bucket["cached_input_tokens"] += row.cached_input_tokens
        user_bucket["output_tokens"] += row.output_tokens
        user_bucket["cached_output_tokens"] += row.cached_output_tokens
        if is_priced:
            user_bucket["priced_records"] += 1
            user_bucket["cost_microusd"] += int(row.cost_microusd or 0)
        else:
            user_bucket["unpriced_records"] += 1

        model_bucket = model_groups[row.model]
        model_bucket["records"] += 1
        model_bucket["input_tokens"] += row.input_tokens
        model_bucket["cached_input_tokens"] += row.cached_input_tokens
        model_bucket["output_tokens"] += row.output_tokens
        model_bucket["cached_output_tokens"] += row.cached_output_tokens
        if is_priced:
            model_bucket["priced_records"] += 1
            model_bucket["cost_microusd"] += int(row.cost_microusd or 0)
        else:
            model_bucket["unpriced_records"] += 1

    top_user_rows = sorted(user_groups.items(), key=_bucket_rank, reverse=True)[:top_limit]
    top_model_rows = sorted(model_groups.items(), key=_bucket_rank, reverse=True)[:top_limit]
    recent_rows = rows_sorted[:recent_limit]

    lookup_user_ids = {user_id for user_id, _ in top_user_rows}
    lookup_user_ids.update(r.owner_user_id for r in recent_rows)
    username_map: dict[str, str] = {}
    if lookup_user_ids:
        users = db.scalars(select(User).where(User.id.in_(list(lookup_user_ids)))).all()
        username_map = {u.id: u.username for u in users}

    top_users = [
        BillingBreakdownItem(
            key=user_id,
            label=username_map.get(user_id),
            records=data["records"],
            input_tokens=data["input_tokens"],
            cached_input_tokens=data["cached_input_tokens"],
            output_tokens=data["output_tokens"],
            cached_output_tokens=data["cached_output_tokens"],
            cost_microusd=_resolved_cost(data["cost_microusd"], data["priced_records"]),
            amount=(
                microusd_to_amount_str(data["cost_microusd"])
                if data["priced_records"] > 0
                else None
            ),
            priced_records=data["priced_records"],
            unpriced_records=data["unpriced_records"],
        )
        for user_id, data in top_user_rows
    ]

    top_models = [
        BillingBreakdownItem(
            key=model_name,
            label=model_name,
            records=data["records"],
            input_tokens=data["input_tokens"],
            cached_input_tokens=data["cached_input_tokens"],
            output_tokens=data["output_tokens"],
            cached_output_tokens=data["cached_output_tokens"],
            cost_microusd=_resolved_cost(data["cost_microusd"], data["priced_records"]),
            amount=(
                microusd_to_amount_str(data["cost_microusd"])
                if data["priced_records"] > 0
                else None
            ),
            priced_records=data["priced_records"],
            unpriced_records=data["unpriced_records"],
        )
        for model_name, data in top_model_rows
    ]

    recent_records = [
        BillingRecentRecord(
            id=row.id,
            created_at=row.created_at,
            owner_user_id=row.owner_user_id,
            username=username_map.get(row.owner_user_id),
            job_id=row.job_id,
            stage=row.stage,
            model=row.model,
            input_tokens=row.input_tokens,
            cached_input_tokens=row.cached_input_tokens,
            output_tokens=row.output_tokens,
            cached_output_tokens=row.cached_output_tokens,
            cost_microusd=row.cost_microusd,
            amount=(microusd_to_amount_str(int(row.cost_microusd)) if row.cost_microusd is not None else None),
        )
        for row in recent_rows
    ]

    resolved_total_cost = _resolved_cost(total_cost_microusd, total_priced_records)
    total = BillingTotalSummary(
        input_tokens=total_input,
        cached_input_tokens=total_cached_input,
        output_tokens=total_output,
        cached_output_tokens=total_cached_output,
        records=len(rows),
        unique_users=len(user_groups),
        unique_models=len(model_groups),
        cost=BillingCostSummary(
            currency="USD",
            cost_microusd=resolved_total_cost,
            amount=microusd_to_amount_str(resolved_total_cost) if resolved_total_cost is not None else None,
            priced_records=total_priced_records,
            unpriced_records=total_unpriced_records,
        ),
    )

    return AdminBillingSummaryResponse(
        query=BillingQueryInfo(
            owner_user_id=owner_user_id,
            model=model,
            range_days=range_days,
            top_limit=top_limit,
            recent_limit=recent_limit,
            since=since,
        ),
        total=total,
        top_users=top_users,
        top_models=top_models,
        recent_records=recent_records,
    )
