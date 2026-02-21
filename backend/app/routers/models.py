from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from ..deps import CurrentUserDep, DbDep
from ..models import ModelPricing
from ..services.upstream_models import UpstreamModelsError, list_upstream_model_ids
from ..services.upstream_channels import list_upstream_channels


router = APIRouter(prefix="/models", tags=["models"])


class ModelItem(BaseModel):
    model: str
    upstream_channel: str = ""
    display_name: str
    currency: str
    unit: str
    input_microusd_per_1m_tokens: int
    cached_input_microusd_per_1m_tokens: int
    output_microusd_per_1m_tokens: int
    cached_output_microusd_per_1m_tokens: int


def enabled_channels_set(*, db: DbDep) -> set[str]:
    # Only expose models for currently enabled upstream channels.
    return {item.channel for item in list_upstream_channels(db=db, include_disabled=False) if item.channel}


def pricing_complete(row: ModelPricing) -> bool:
    return None not in (
        row.input_microusd_per_1m_tokens,
        row.cached_input_microusd_per_1m_tokens,
        row.output_microusd_per_1m_tokens,
        row.cached_output_microusd_per_1m_tokens,
    )


def priced_model_item(*, channel: str, row: ModelPricing) -> ModelItem:
    return ModelItem(
        model=row.model,
        upstream_channel=channel,
        display_name=f"[{channel}] {row.model}",
        currency=row.currency,
        unit=row.unit,
        input_microusd_per_1m_tokens=row.input_microusd_per_1m_tokens,
        cached_input_microusd_per_1m_tokens=row.cached_input_microusd_per_1m_tokens,
        output_microusd_per_1m_tokens=row.output_microusd_per_1m_tokens,
        cached_output_microusd_per_1m_tokens=row.cached_output_microusd_per_1m_tokens,
    )


def live_model_item(*, channel: str, model: str, priced: ModelPricing | None) -> ModelItem:
    has_valid_pricing = bool(priced and pricing_complete(priced))
    if has_valid_pricing and priced is not None:
        return ModelItem(
            model=model,
            upstream_channel=channel,
            display_name=f"[{channel}] {model}",
            currency=priced.currency,
            unit=priced.unit,
            input_microusd_per_1m_tokens=priced.input_microusd_per_1m_tokens,
            cached_input_microusd_per_1m_tokens=priced.cached_input_microusd_per_1m_tokens,
            output_microusd_per_1m_tokens=priced.output_microusd_per_1m_tokens,
            cached_output_microusd_per_1m_tokens=priced.cached_output_microusd_per_1m_tokens,
        )
    return ModelItem(
        model=model,
        upstream_channel=channel,
        display_name=f"[{channel}] {model}",
        currency="USD",
        unit="1M_TOKENS",
        input_microusd_per_1m_tokens=0,
        cached_input_microusd_per_1m_tokens=0,
        output_microusd_per_1m_tokens=0,
        cached_output_microusd_per_1m_tokens=0,
    )


@router.get("", response_model=list[ModelItem])
def list_models(_: CurrentUserDep, db: DbDep):
    enabled_channels = enabled_channels_set(db=db)
    items = db.scalars(select(ModelPricing).where(ModelPricing.is_active == True)).all()  # noqa: E712
    result: list[ModelItem] = []
    for item in items:
        channel = (item.upstream_channel or "").strip()
        if not channel or channel not in enabled_channels:
            continue
        if not pricing_complete(item):
            continue
        result.append(priced_model_item(channel=channel, row=item))
    result.sort(key=lambda x: (x.upstream_channel.lower(), x.model.lower()))
    return result


@router.get("/live", response_model=list[ModelItem])
def list_live_models(_: CurrentUserDep, db: DbDep):
    enabled_channels = sorted(enabled_channels_set(db=db))
    if not enabled_channels:
        return []

    priced_rows = db.scalars(select(ModelPricing).where(ModelPricing.is_active == True)).all()  # noqa: E712
    priced_by_key: dict[tuple[str, str], ModelPricing] = {}
    for row in priced_rows:
        channel = (row.upstream_channel or "").strip()
        model = (row.model or "").strip()
        if not channel or not model:
            continue
        priced_by_key[(channel, model)] = row

    result: list[ModelItem] = []
    for channel in enabled_channels:
        try:
            model_ids = sorted(list_upstream_model_ids(channel=channel, db=db))
        except UpstreamModelsError:
            continue

        for model in model_ids:
            priced = priced_by_key.get((channel, model))
            result.append(live_model_item(channel=channel, model=model, priced=priced))

    result.sort(key=lambda x: (x.upstream_channel.lower(), x.model.lower()))
    return result
