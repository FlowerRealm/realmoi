from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_, select

from ..deps import CurrentUserDep, DbDep
from ..models import UsageRecord
from ..services.pricing import microusd_to_amount_str
from ..utils.errors import http_error


router = APIRouter(prefix="/billing", tags=["billing"])


MICROUSD_PER_1M_TOKENS = 1_000_000


class BillingRangeQuery(BaseModel):
    start: str
    end: str


class BillingCostSummary(BaseModel):
    currency: str = "USD"
    cost_microusd: int | None = None
    amount: str | None = None
    priced_records: int
    unpriced_records: int


class BillingWindow(BaseModel):
    window: str = "range"
    since: datetime
    until: datetime
    records: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    cached_output_tokens: int
    total_tokens: int
    cached_tokens: int
    cache_ratio: float
    cost: BillingCostSummary


class BillingWindowsResponse(BaseModel):
    now: datetime
    query: BillingRangeQuery
    windows: list[BillingWindow]


class BillingDailyPoint(BaseModel):
    day: str
    records: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    cached_output_tokens: int
    total_tokens: int
    cached_tokens: int
    cache_ratio: float
    cost: BillingCostSummary


class BillingDailyResponse(BaseModel):
    query: BillingRangeQuery
    points: list[BillingDailyPoint]


class BillingEventsQuery(BaseModel):
    start: str
    end: str
    limit: int
    before_id: str | None = None


class BillingEventCost(BaseModel):
    currency: str = "USD"
    cost_microusd: int
    amount: str


class BillingEvent(BaseModel):
    id: str
    created_at: datetime
    job_id: str
    stage: str
    model: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    cached_output_tokens: int
    total_tokens: int
    cached_tokens: int
    cost: BillingEventCost | None = None


class BillingEventsResponse(BaseModel):
    query: BillingEventsQuery
    events: list[BillingEvent]
    next_before_id: str | None = None


class BillingPricingSnapshot(BaseModel):
    currency: str = "USD"
    input_microusd_per_1m_tokens: int
    cached_input_microusd_per_1m_tokens: int
    output_microusd_per_1m_tokens: int
    cached_output_microusd_per_1m_tokens: int


class BillingCostBreakdownLine(BaseModel):
    tokens: int
    price_microusd_per_1m_tokens: int
    cost_microusd: int
    amount: str


class BillingCostBreakdown(BaseModel):
    non_cached_input: BillingCostBreakdownLine
    non_cached_output: BillingCostBreakdownLine
    cached_input: BillingCostBreakdownLine
    cached_output: BillingCostBreakdownLine
    computed_total_microusd: int
    computed_total_amount: str


class BillingEventDetail(BillingEvent):
    pricing: BillingPricingSnapshot | None = None
    breakdown: BillingCostBreakdown | None = None


def _cost_summary(*, priced_records: int, unpriced_records: int, cost_microusd: int) -> BillingCostSummary:
    resolved_cost = cost_microusd if priced_records > 0 else None
    return BillingCostSummary(
        currency="USD",
        cost_microusd=resolved_cost,
        amount=microusd_to_amount_str(resolved_cost) if resolved_cost is not None else None,
        priced_records=priced_records,
        unpriced_records=unpriced_records,
    )


def _line_cost(tokens: int, microusd_per_1m: int) -> int:
    if tokens <= 0 or microusd_per_1m <= 0:
        return 0
    return (tokens * microusd_per_1m) // MICROUSD_PER_1M_TOKENS


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _event_cost(record: UsageRecord) -> BillingEventCost | None:
    if record.cost_microusd is None:
        return None
    return BillingEventCost(
        currency=record.currency or "USD",
        cost_microusd=int(record.cost_microusd),
        amount=microusd_to_amount_str(int(record.cost_microusd)),
    )


def _event_from_record(record: UsageRecord) -> BillingEvent:
    cached_input = max(0, int(record.cached_input_tokens))
    cached_output = max(0, int(record.cached_output_tokens))
    input_tokens = max(0, int(record.input_tokens))
    output_tokens = max(0, int(record.output_tokens))
    return BillingEvent(
        id=record.id,
        created_at=_as_utc(record.created_at),
        job_id=record.job_id,
        stage=record.stage,
        model=record.model,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input,
        output_tokens=output_tokens,
        cached_output_tokens=cached_output,
        total_tokens=input_tokens + output_tokens,
        cached_tokens=cached_input + cached_output,
        cost=_event_cost(record),
    )


def _event_detail_from_record(record: UsageRecord) -> BillingEventDetail:
    base = _event_from_record(record)
    prices = (
        record.input_microusd_per_1m_tokens,
        record.cached_input_microusd_per_1m_tokens,
        record.output_microusd_per_1m_tokens,
        record.cached_output_microusd_per_1m_tokens,
    )
    if any(price is None for price in prices):
        return BillingEventDetail(**base.model_dump(), pricing=None, breakdown=None)

    input_price = int(record.input_microusd_per_1m_tokens or 0)
    cached_input_price = int(record.cached_input_microusd_per_1m_tokens or 0)
    output_price = int(record.output_microusd_per_1m_tokens or 0)
    cached_output_price = int(record.cached_output_microusd_per_1m_tokens or 0)

    clamped_cached_input = min(base.cached_input_tokens, base.input_tokens)
    clamped_cached_output = min(base.cached_output_tokens, base.output_tokens)
    non_cached_input = max(0, base.input_tokens - clamped_cached_input)
    non_cached_output = max(0, base.output_tokens - clamped_cached_output)

    line_non_cached_input = BillingCostBreakdownLine(
        tokens=non_cached_input,
        price_microusd_per_1m_tokens=input_price,
        cost_microusd=_line_cost(non_cached_input, input_price),
        amount=microusd_to_amount_str(_line_cost(non_cached_input, input_price)),
    )
    line_non_cached_output = BillingCostBreakdownLine(
        tokens=non_cached_output,
        price_microusd_per_1m_tokens=output_price,
        cost_microusd=_line_cost(non_cached_output, output_price),
        amount=microusd_to_amount_str(_line_cost(non_cached_output, output_price)),
    )
    line_cached_input = BillingCostBreakdownLine(
        tokens=clamped_cached_input,
        price_microusd_per_1m_tokens=cached_input_price,
        cost_microusd=_line_cost(clamped_cached_input, cached_input_price),
        amount=microusd_to_amount_str(_line_cost(clamped_cached_input, cached_input_price)),
    )
    line_cached_output = BillingCostBreakdownLine(
        tokens=clamped_cached_output,
        price_microusd_per_1m_tokens=cached_output_price,
        cost_microusd=_line_cost(clamped_cached_output, cached_output_price),
        amount=microusd_to_amount_str(_line_cost(clamped_cached_output, cached_output_price)),
    )

    computed_total = (
        line_non_cached_input.cost_microusd
        + line_non_cached_output.cost_microusd
        + line_cached_input.cost_microusd
        + line_cached_output.cost_microusd
    )

    pricing = BillingPricingSnapshot(
        currency=record.currency or "USD",
        input_microusd_per_1m_tokens=input_price,
        cached_input_microusd_per_1m_tokens=cached_input_price,
        output_microusd_per_1m_tokens=output_price,
        cached_output_microusd_per_1m_tokens=cached_output_price,
    )
    breakdown = BillingCostBreakdown(
        non_cached_input=line_non_cached_input,
        non_cached_output=line_non_cached_output,
        cached_input=line_cached_input,
        cached_output=line_cached_output,
        computed_total_microusd=computed_total,
        computed_total_amount=microusd_to_amount_str(computed_total),
    )
    return BillingEventDetail(**base.model_dump(), pricing=pricing, breakdown=breakdown)


def _parse_date_utc(raw: str, *, field_name: str) -> datetime:
    try:
        day = datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        http_error(422, "invalid_request", f"Invalid {field_name}; expected YYYY-MM-DD")
    return day.replace(tzinfo=timezone.utc)


def _resolve_date_range(start: str | None, end: str | None) -> tuple[str, str, datetime, datetime, datetime]:
    now = datetime.now(tz=timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    today_str = today_start.strftime("%Y-%m-%d")

    start_str = (start or "").strip() or today_str
    end_str = (end or "").strip() or start_str

    since = _parse_date_utc(start_str, field_name="start")
    end_date = _parse_date_utc(end_str, field_name="end")
    if since > end_date:
        http_error(422, "invalid_request", "start cannot be later than end")

    if end_date > today_start:
        end_date = today_start
        end_str = today_str

    until = end_date + timedelta(days=1)
    if end_str == today_str:
        until = now
    return start_str, end_str, since, until, now


def _iter_days_inclusive(start_str: str, end_str: str) -> list[str]:
    start_day = _parse_date_utc(start_str, field_name="start")
    end_day = _parse_date_utc(end_str, field_name="end")
    days: list[str] = []
    cursor = start_day
    while cursor <= end_day:
        days.append(cursor.strftime("%Y-%m-%d"))
        cursor += timedelta(days=1)
    return days


@router.get("/summary")
def billing_summary(user: CurrentUserDep, db: DbDep):
    rows = db.scalars(select(UsageRecord).where(UsageRecord.owner_user_id == user.id)).all()
    usage = {
        "input_tokens": sum(r.input_tokens for r in rows),
        "cached_input_tokens": sum(r.cached_input_tokens for r in rows),
        "output_tokens": sum(r.output_tokens for r in rows),
        "cached_output_tokens": sum(r.cached_output_tokens for r in rows),
    }
    cost_microusd = sum(r.cost_microusd or 0 for r in rows) if any(r.cost_microusd is not None for r in rows) else None
    cost = None
    if cost_microusd is not None:
        cost = {"currency": "USD", "cost_microusd": cost_microusd, "amount": microusd_to_amount_str(cost_microusd)}
    return {"owner_user_id": user.id, "usage": usage, "cost": cost, "records": len(rows)}


@router.get("/windows", response_model=BillingWindowsResponse)
def billing_windows(
    user: CurrentUserDep,
    db: DbDep,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
):
    start_str, end_str, since, until, now = _resolve_date_range(start, end)
    rows = db.scalars(
        select(UsageRecord).where(
            and_(
                UsageRecord.owner_user_id == user.id,
                UsageRecord.created_at >= since,
                UsageRecord.created_at < until,
            )
        )
    ).all()

    input_tokens = sum(int(r.input_tokens) for r in rows)
    cached_input_tokens = sum(int(r.cached_input_tokens) for r in rows)
    output_tokens = sum(int(r.output_tokens) for r in rows)
    cached_output_tokens = sum(int(r.cached_output_tokens) for r in rows)
    total_tokens = input_tokens + output_tokens
    cached_tokens = cached_input_tokens + cached_output_tokens
    cache_ratio = float(cached_tokens / total_tokens) if total_tokens > 0 else 0.0

    priced_records = sum(1 for r in rows if r.cost_microusd is not None)
    unpriced_records = len(rows) - priced_records
    cost_microusd = sum(int(r.cost_microusd or 0) for r in rows if r.cost_microusd is not None)
    window = BillingWindow(
        window="range",
        since=since,
        until=until,
        records=len(rows),
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        cached_output_tokens=cached_output_tokens,
        total_tokens=total_tokens,
        cached_tokens=cached_tokens,
        cache_ratio=cache_ratio,
        cost=_cost_summary(
            priced_records=priced_records,
            unpriced_records=unpriced_records,
            cost_microusd=cost_microusd,
        ),
    )

    return BillingWindowsResponse(
        now=now,
        query=BillingRangeQuery(start=start_str, end=end_str),
        windows=[window],
    )


@router.get("/daily", response_model=BillingDailyResponse)
def billing_daily(
    user: CurrentUserDep,
    db: DbDep,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
):
    start_str, end_str, since, until, _ = _resolve_date_range(start, end)
    rows = db.scalars(
        select(UsageRecord).where(
            and_(
                UsageRecord.owner_user_id == user.id,
                UsageRecord.created_at >= since,
                UsageRecord.created_at < until,
            )
        )
    ).all()

    day_stats: dict[str, dict[str, int]] = {}
    for row in rows:
        day_key = _as_utc(row.created_at).strftime("%Y-%m-%d")
        stat = day_stats.setdefault(
            day_key,
            {
                "records": 0,
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "cached_output_tokens": 0,
                "cost_microusd": 0,
                "priced_records": 0,
                "unpriced_records": 0,
            },
        )
        stat["records"] += 1
        stat["input_tokens"] += max(0, int(row.input_tokens))
        stat["cached_input_tokens"] += max(0, int(row.cached_input_tokens))
        stat["output_tokens"] += max(0, int(row.output_tokens))
        stat["cached_output_tokens"] += max(0, int(row.cached_output_tokens))
        if row.cost_microusd is None:
            stat["unpriced_records"] += 1
        else:
            stat["priced_records"] += 1
            stat["cost_microusd"] += int(row.cost_microusd)

    points: list[BillingDailyPoint] = []
    for day in _iter_days_inclusive(start_str, end_str):
        stat = day_stats.get(
            day,
            {
                "records": 0,
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "cached_output_tokens": 0,
                "cost_microusd": 0,
                "priced_records": 0,
                "unpriced_records": 0,
            },
        )
        total_tokens = stat["input_tokens"] + stat["output_tokens"]
        cached_tokens = stat["cached_input_tokens"] + stat["cached_output_tokens"]
        cache_ratio = float(cached_tokens / total_tokens) if total_tokens > 0 else 0.0
        points.append(
            BillingDailyPoint(
                day=day,
                records=stat["records"],
                input_tokens=stat["input_tokens"],
                cached_input_tokens=stat["cached_input_tokens"],
                output_tokens=stat["output_tokens"],
                cached_output_tokens=stat["cached_output_tokens"],
                total_tokens=total_tokens,
                cached_tokens=cached_tokens,
                cache_ratio=cache_ratio,
                cost=_cost_summary(
                    priced_records=stat["priced_records"],
                    unpriced_records=stat["unpriced_records"],
                    cost_microusd=stat["cost_microusd"],
                ),
            )
        )

    return BillingDailyResponse(
        query=BillingRangeQuery(start=start_str, end=end_str),
        points=points,
    )


@router.get("/events", response_model=BillingEventsResponse)
def billing_events(
    user: CurrentUserDep,
    db: DbDep,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    before_id: str | None = Query(default=None),
):
    start_str, end_str, since, until, _ = _resolve_date_range(start, end)

    stmt = select(UsageRecord).where(
        and_(
            UsageRecord.owner_user_id == user.id,
            UsageRecord.created_at >= since,
            UsageRecord.created_at < until,
        )
    )

    if before_id:
        cursor = db.get(UsageRecord, before_id)
        if not cursor or cursor.owner_user_id != user.id:
            http_error(404, "not_found", "Cursor not found")
        cursor_created_at = _as_utc(cursor.created_at)
        if cursor_created_at < since or cursor_created_at >= until:
            http_error(422, "invalid_request", "Cursor is outside selected date range")
        stmt = stmt.where(
            or_(
                UsageRecord.created_at < cursor_created_at,
                and_(
                    UsageRecord.created_at == cursor_created_at,
                    UsageRecord.id < cursor.id,
                ),
            )
        )

    rows = db.scalars(
        stmt.order_by(UsageRecord.created_at.desc(), UsageRecord.id.desc()).limit(limit)
    ).all()
    next_before_id = rows[-1].id if len(rows) >= limit and rows else None

    return BillingEventsResponse(
        query=BillingEventsQuery(
            start=start_str,
            end=end_str,
            limit=limit,
            before_id=before_id,
        ),
        events=[_event_from_record(row) for row in rows],
        next_before_id=next_before_id,
    )


@router.get("/events/{record_id}/detail", response_model=BillingEventDetail)
def billing_event_detail(user: CurrentUserDep, db: DbDep, record_id: str):
    row = db.get(UsageRecord, record_id)
    if not row or row.owner_user_id != user.id:
        http_error(404, "not_found", "Record not found")
    return _event_detail_from_record(row)
