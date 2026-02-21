from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from ..deps import AdminUserDep, DbDep
from ..models import ModelPricing
from ..utils.errors import http_error
from .admin_common import commit_db


router = APIRouter()


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
    commit_db(db)
    return {"ok": True}

