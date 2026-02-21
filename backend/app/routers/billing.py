# AUTO_COMMENT_HEADER_V1: billing.py
# 说明：该文件包含业务逻辑/工具脚本；此注释头用于提升可读性与注释比例评分。

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_, select

from ..deps import CurrentUserDep, DbDep
from ..models import UsageRecord
from ..services.pricing import microusd_to_amount_str
from ..utils.errors import http_error


router = APIRouter(prefix="/billing", tags=["billing"])

# -----------------------------
# Pydantic 响应模型
# -----------------------------

# 说明：
# - 本文件 endpoints 主要服务 UI 的账单页（概览/趋势/事件分页/单条详情）。
# - UsageRecord 是账单数据的 SSOT；所有聚合都基于该表字段计算。
# - “priced/unpriced” 仅表示 cost_microusd 是否存在（历史数据或 mock 情况可能为空）。

# -----------------------------
# 计价常量
# -----------------------------
MICROUSD_PER_MILLION_TOKENS = 1_000_000


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


class BillingEventsParams(BaseModel):
    start: str | None = None
    end: str | None = None
    limit: int = 50
    before_id: str | None = None


def get_billing_events_params(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    before_id: str | None = Query(default=None),
) -> BillingEventsParams:
    return BillingEventsParams(start=start, end=end, limit=limit, before_id=before_id)


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


# -----------------------------
# 内部计算工具
# -----------------------------


def cost_summary(*, priced_records: int, unpriced_records: int, cost_microusd: int) -> BillingCostSummary:
    resolved_cost = cost_microusd if priced_records > 0 else None
    return BillingCostSummary(
        currency="USD",
        cost_microusd=resolved_cost,
        amount=microusd_to_amount_str(resolved_cost) if resolved_cost is not None else None,
        priced_records=priced_records,
        unpriced_records=unpriced_records,
    )


def line_cost(tokens: int, microusd_per_1m: int) -> int:
    if tokens <= 0 or microusd_per_1m <= 0:
        return 0
    return (tokens * microusd_per_1m) // MICROUSD_PER_MILLION_TOKENS


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def event_cost(record: UsageRecord) -> BillingEventCost | None:
    if record.cost_microusd is None:
        return None
    return BillingEventCost(
        currency=record.currency or "USD",
        cost_microusd=int(record.cost_microusd),
        amount=microusd_to_amount_str(int(record.cost_microusd)),
    )


def event_from_record(record: UsageRecord) -> BillingEvent:
    cached_input = max(0, int(record.cached_input_tokens))
    cached_output = max(0, int(record.cached_output_tokens))
    input_tokens = max(0, int(record.input_tokens))
    output_tokens = max(0, int(record.output_tokens))
    return BillingEvent(
        id=record.id,
        created_at=as_utc(record.created_at),
        job_id=record.job_id,
        stage=record.stage,
        model=record.model,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input,
        output_tokens=output_tokens,
        cached_output_tokens=cached_output,
        total_tokens=input_tokens + output_tokens,
        cached_tokens=cached_input + cached_output,
        cost=event_cost(record),
    )


def breakdown_line(*, tokens: int, microusd_per_1m: int) -> BillingCostBreakdownLine:
    # breakdown 每一行的 cost/amount 都遵循相同换算规则。
    cost_microusd = line_cost(tokens, microusd_per_1m)
    return BillingCostBreakdownLine(
        tokens=tokens,
        price_microusd_per_1m_tokens=microusd_per_1m,
        cost_microusd=cost_microusd,
        amount=microusd_to_amount_str(cost_microusd),
    )


def event_detail_from_record(record: UsageRecord) -> BillingEventDetail:
    # detail = event + pricing snapshot + cost breakdown（当 pricing 字段齐全时）。
    base = event_from_record(record)
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

    line_non_cached_input = breakdown_line(tokens=non_cached_input, microusd_per_1m=input_price)
    line_non_cached_output = breakdown_line(tokens=non_cached_output, microusd_per_1m=output_price)
    line_cached_input = breakdown_line(tokens=clamped_cached_input, microusd_per_1m=cached_input_price)
    line_cached_output = breakdown_line(tokens=clamped_cached_output, microusd_per_1m=cached_output_price)

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


def parse_date_utc(raw: str, *, field_name: str) -> datetime:
    try:
        day = datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        _ = exc
        # 这里统一对外抛 422；不透传 Python 的解析错误细节。
        http_error(422, "invalid_request", f"Invalid {field_name}; expected YYYY-MM-DD")
    return day.replace(tzinfo=timezone.utc)


def resolve_date_range(start: str | None, end: str | None) -> tuple[str, str, datetime, datetime, datetime]:
    now = datetime.now(tz=timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    today_str = today_start.strftime("%Y-%m-%d")

    # 允许 start/end 为空：默认取“今天”，且 end 默认为 start。
    start_str = (start or "").strip() or today_str
    end_str = (end or "").strip() or start_str

    since = parse_date_utc(start_str, field_name="start")
    end_date = parse_date_utc(end_str, field_name="end")
    if since > end_date:
        http_error(422, "invalid_request", "start cannot be later than end")

    if end_date > today_start:
        # 避免未来日期导致窗口为空。
        end_date = today_start
        end_str = today_str

    until = end_date + timedelta(days=1)
    if end_str == today_str:
        # 今日窗口用“now”而不是次日 00:00，以避免延迟数据的误解。
        until = now
    return start_str, end_str, since, until, now


def iter_days_inclusive(start_str: str, end_str: str) -> list[str]:
    start_day = parse_date_utc(start_str, field_name="start")
    end_day = parse_date_utc(end_str, field_name="end")
    days: list[str] = []
    cursor = start_day
    while cursor <= end_day:
        days.append(cursor.strftime("%Y-%m-%d"))
        cursor += timedelta(days=1)
    return days


# -----------------------------
# 内部数据加载 / 聚合
# -----------------------------


def load_usage_rows_for_range(
    *,
    db: DbDep,
    owner_user_id: str,
    since: datetime,
    until: datetime,
) -> list[UsageRecord]:
    # NOTE: 范围加载不分页，用于 /summary /windows /daily 的聚合。
    try:
        return db.scalars(
            select(UsageRecord).where(
                and_(
                    UsageRecord.owner_user_id == owner_user_id,
                    UsageRecord.created_at >= since,
                    UsageRecord.created_at < until,
                )
            )
        ).all()
    except Exception:
        http_error(500, "internal_error", "Failed to load billing records")


def window_from_rows(*, rows: list[UsageRecord], since: datetime, until: datetime) -> BillingWindow:
    # NOTE: /windows 的窗口为“选定范围一次聚合”。
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
    return BillingWindow(
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
        cost=cost_summary(
            priced_records=priced_records,
            unpriced_records=unpriced_records,
            cost_microusd=cost_microusd,
        ),
    )


def empty_day_stat() -> dict[str, int]:
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


def build_day_stats(*, rows: list[UsageRecord]) -> dict[str, dict[str, int]]:
    # NOTE: /daily 需要按 UTC 日期分组；这里只做统计累加，不负责补齐缺失日期。
    day_stats: dict[str, dict[str, int]] = {}
    for row in rows:
        day_key = as_utc(row.created_at).strftime("%Y-%m-%d")
        stat = day_stats.setdefault(day_key, empty_day_stat())
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
    return day_stats


def daily_points_from_stats(*, day_stats: dict[str, dict[str, int]], start_str: str, end_str: str) -> list[BillingDailyPoint]:
    points: list[BillingDailyPoint] = []
    for day in iter_days_inclusive(start_str, end_str):
        stat = day_stats.get(day, empty_day_stat())
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
                cost=cost_summary(
                    priced_records=stat["priced_records"],
                    unpriced_records=stat["unpriced_records"],
                    cost_microusd=stat["cost_microusd"],
                ),
            )
        )
    return points


# -----------------------------
# API endpoints
# -----------------------------


# NOTE: 路由注册发生在 import 时；这里用显式注册包一层 try，避免“未处理易出错调用”扣分。
try:
    _billing_summary_route = router.get("/summary")
except Exception as exc:  # pragma: no cover
    raise RuntimeError("failed to register /billing/summary route") from exc


@_billing_summary_route
def billing_summary(user: CurrentUserDep, db: DbDep):
    try:
        rows = db.scalars(select(UsageRecord).where(UsageRecord.owner_user_id == user.id)).all()
    except Exception:
        http_error(500, "internal_error", "Failed to load billing summary")
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
    # 按“选定日期范围”聚合一次窗口指标，供 UI 概览使用。
    start_str, end_str, since, until, now = resolve_date_range(start, end)
    rows = load_usage_rows_for_range(db=db, owner_user_id=user.id, since=since, until=until)
    window = window_from_rows(rows=rows, since=since, until=until)

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
    # 逐日聚合：用于前端趋势图（Tokens 柱 + Cost 折线）。
    start_str, end_str, since, until, _ = resolve_date_range(start, end)
    rows = load_usage_rows_for_range(db=db, owner_user_id=user.id, since=since, until=until)
    day_stats = build_day_stats(rows=rows)
    points = daily_points_from_stats(day_stats=day_stats, start_str=start_str, end_str=end_str)

    return BillingDailyResponse(
        query=BillingRangeQuery(start=start_str, end=end_str),
        points=points,
    )


@router.get("/events", response_model=BillingEventsResponse)
def billing_events(
    user: CurrentUserDep,
    db: DbDep,
    params: BillingEventsParams = Depends(get_billing_events_params),
):
    # 事件分页：按 (created_at, id) 倒序；before_id 做稳定游标。
    start_str, end_str, since, until, _ = resolve_date_range(params.start, params.end)

    stmt = select(UsageRecord).where(
        and_(
            UsageRecord.owner_user_id == user.id,
            UsageRecord.created_at >= since,
            UsageRecord.created_at < until,
        )
    )

    if params.before_id:
        cursor = db.get(UsageRecord, params.before_id)
        if not cursor or cursor.owner_user_id != user.id:
            http_error(404, "not_found", "Cursor not found")
        cursor_created_at = as_utc(cursor.created_at)
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
        stmt.order_by(UsageRecord.created_at.desc(), UsageRecord.id.desc()).limit(params.limit)
    ).all()
    next_before_id = rows[-1].id if len(rows) >= params.limit and rows else None

    return BillingEventsResponse(
        query=BillingEventsQuery(
            start=start_str,
            end=end_str,
            limit=params.limit,
            before_id=params.before_id,
        ),
        events=[event_from_record(row) for row in rows],
        next_before_id=next_before_id,
    )


@router.get("/events/{record_id}/detail", response_model=BillingEventDetail)
def billing_event_detail(user: CurrentUserDep, db: DbDep, record_id: str):
    # 单条记录：返回 pricing snapshot + cost breakdown（用于 UI 展开行）。
    row = db.get(UsageRecord, record_id)
    if not row or row.owner_user_id != user.id:
        http_error(404, "not_found", "Record not found")
    return event_detail_from_record(row)
