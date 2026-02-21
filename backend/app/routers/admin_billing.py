from __future__ import annotations

# AUTO_COMMENT_HEADER_V1: admin_billing.py
# 说明：管理端 billing 汇总接口（聚合 UsageRecord）。
# - 支持按用户 / 模型过滤、按天数范围过滤
# - 输出 total 汇总 + top 用户/模型 + 最近记录
# - 该文件的注释以“解释数据口径”为主（便于后续排查账单一致性）

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

from ..deps import AdminUserDep, DbDep
from ..models import UsageRecord, User
from ..services.pricing import microusd_to_amount_str


router = APIRouter()


class BillingQueryInfo(BaseModel):
    # Echoed query info for admin billing summary responses.
    owner_user_id: str | None = None
    model: str | None = None
    range_days: int | None = None
    top_limit: int
    recent_limit: int
    since: datetime | None = None


class BillingCostSummary(BaseModel):
    # Cost summary for a set of usage records.
    currency: str = "USD"
    cost_microusd: int | None = None
    amount: str | None = None
    priced_records: int
    unpriced_records: int


class BillingTotalSummary(BaseModel):
    # Totals across all matched rows.
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    cached_output_tokens: int
    records: int
    unique_users: int
    unique_models: int
    cost: BillingCostSummary


class BillingBreakdownItem(BaseModel):
    # One breakdown row grouped by user or model.
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
    # Recent record preview for admin UI.
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
    # Response payload for the admin billing summary endpoint.
    query: BillingQueryInfo
    total: BillingTotalSummary
    top_users: list[BillingBreakdownItem]
    top_models: list[BillingBreakdownItem]
    recent_records: list[BillingRecentRecord]


def bucket_seed() -> dict[str, int]:
    # Initialize one aggregation bucket.
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


def resolved_cost(cost_microusd: int, priced_records: int) -> int | None:
    # Return cost only when at least one record is priced.
    if priced_records <= 0:
        return None
    return cost_microusd


def bucket_rank(row: tuple[str, dict[str, int]]) -> tuple[int, int, int]:
    # Sort key for top breakdown: cost first, then tokens, then record count.
    data = row[1]
    total_io = data["input_tokens"] + data["output_tokens"]
    return (data["cost_microusd"], total_io, data["records"])


def bucket_amount(cost_microusd: int, priced_records: int) -> str | None:
    # Format cost amount only when there are priced rows.
    if priced_records <= 0:
        return None
    return microusd_to_amount_str(cost_microusd)


def aggregate_usage_rows(
    rows: list[UsageRecord],
) -> tuple[dict[str, int], dict[str, dict[str, int]], dict[str, dict[str, int]]]:
    # 聚合口径：
    # - tokens：直接累加 UsageRecord 里的 token 字段（已确保非负）
    # - cost：仅对有定价（cost_microusd 非空）的记录累加
    # - priced/unpriced：用于 UI 区分“有定价”和“缺定价”的数据量
    user_groups: dict[str, dict[str, int]] = defaultdict(bucket_seed)
    model_groups: dict[str, dict[str, int]] = defaultdict(bucket_seed)

    totals = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "cached_output_tokens": 0,
        "cost_microusd": 0,
        "priced_records": 0,
        "unpriced_records": 0,
    }

    for row in rows:
        totals["input_tokens"] += row.input_tokens
        totals["cached_input_tokens"] += row.cached_input_tokens
        totals["output_tokens"] += row.output_tokens
        totals["cached_output_tokens"] += row.cached_output_tokens

        is_priced = row.cost_microusd is not None
        if is_priced:
            totals["priced_records"] += 1
            totals["cost_microusd"] += int(row.cost_microusd or 0)
        else:
            totals["unpriced_records"] += 1

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

    return totals, user_groups, model_groups


def build_breakdown_items(*, rows: list[tuple[str, dict[str, int]]], label_map: dict[str, str] | None) -> list[BillingBreakdownItem]:
    # 将聚合桶转换为可直接返回给前端的结构。
    items: list[BillingBreakdownItem] = []
    for key, data in rows:
        cost_val = resolved_cost(data["cost_microusd"], data["priced_records"])
        items.append(
            BillingBreakdownItem(
                key=key,
                label=(label_map or {}).get(key),
                records=data["records"],
                input_tokens=data["input_tokens"],
                cached_input_tokens=data["cached_input_tokens"],
                output_tokens=data["output_tokens"],
                cached_output_tokens=data["cached_output_tokens"],
                cost_microusd=cost_val,
                amount=bucket_amount(data["cost_microusd"], data["priced_records"]),
                priced_records=data["priced_records"],
                unpriced_records=data["unpriced_records"],
            )
        )
    return items


class AdminBillingParams(BaseModel):
    # Query params for `/billing/summary` in a single object (keeps handler signature small).

    owner_user_id: str | None = None
    model: str | None = None
    range_days: int | None = None
    top_limit: int = 8
    recent_limit: int = 20


def get_admin_billing_params(
    owner_user_id: str | None = None,
    model: str | None = None,
    range_days: int | None = Query(default=None, ge=1, le=3650),
    top_limit: int = Query(default=8, ge=1, le=50),
    recent_limit: int = Query(default=20, ge=1, le=200),
) -> AdminBillingParams:
    return AdminBillingParams(
        owner_user_id=owner_user_id,
        model=model,
        range_days=range_days,
        top_limit=top_limit,
        recent_limit=recent_limit,
    )


@router.get("/billing/summary", response_model=AdminBillingSummaryResponse)
def admin_billing_summary(
    _: AdminUserDep,
    db: DbDep,
    params: AdminBillingParams = Depends(get_admin_billing_params),
):
    # 说明：该接口用于 admin UI 的“账单总览”页面。
    # 注意：返回内容包含 recent_records（默认 20 条），因此不建议将 range_days 设得过大。
    stmt = select(UsageRecord)
    if params.owner_user_id:
        stmt = stmt.where(UsageRecord.owner_user_id == params.owner_user_id)
    if params.model:
        stmt = stmt.where(UsageRecord.model == params.model)
    since: datetime | None = None
    if params.range_days is not None:
        since = datetime.now(tz=timezone.utc) - timedelta(days=params.range_days)
        stmt = stmt.where(UsageRecord.created_at >= since)

    rows = db.scalars(stmt).all()
    rows_sorted = sorted(rows, key=lambda r: r.created_at, reverse=True)

    totals, user_groups, model_groups = aggregate_usage_rows(rows)

    top_user_rows = sorted(user_groups.items(), key=bucket_rank, reverse=True)[: params.top_limit]
    top_model_rows = sorted(model_groups.items(), key=bucket_rank, reverse=True)[: params.top_limit]
    recent_rows = rows_sorted[: params.recent_limit]

    lookup_user_ids = {user_id for user_id, _ in top_user_rows}
    lookup_user_ids.update(r.owner_user_id for r in recent_rows)
    username_map: dict[str, str] = {}
    if lookup_user_ids:
        users = db.scalars(select(User).where(User.id.in_(list(lookup_user_ids)))).all()
        username_map = {u.id: u.username for u in users}

    top_users = build_breakdown_items(rows=top_user_rows, label_map=username_map)

    top_models = build_breakdown_items(
        rows=top_model_rows,
        label_map={k: k for k, _ in top_model_rows},
    )

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

    resolved_total_cost = resolved_cost(totals["cost_microusd"], totals["priced_records"])
    total = BillingTotalSummary(
        input_tokens=totals["input_tokens"],
        cached_input_tokens=totals["cached_input_tokens"],
        output_tokens=totals["output_tokens"],
        cached_output_tokens=totals["cached_output_tokens"],
        records=len(rows),
        unique_users=len(user_groups),
        unique_models=len(model_groups),
        cost=BillingCostSummary(
            currency="USD",
            cost_microusd=resolved_total_cost,
            amount=microusd_to_amount_str(resolved_total_cost) if resolved_total_cost is not None else None,
            priced_records=totals["priced_records"],
            unpriced_records=totals["unpriced_records"],
        ),
    )

    return AdminBillingSummaryResponse(
        query=BillingQueryInfo(
            owner_user_id=params.owner_user_id,
            model=params.model,
            range_days=params.range_days,
            top_limit=params.top_limit,
            recent_limit=params.recent_limit,
            since=since,
        ),
        total=total,
        top_users=top_users,
        top_models=top_models,
        recent_records=recent_records,
    )
