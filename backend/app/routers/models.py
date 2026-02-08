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


@router.get("", response_model=list[ModelItem])
def list_models(_: CurrentUserDep, db: DbDep):
    enabled_channels = {
        item.channel
        for item in list_upstream_channels(db=db, include_disabled=False)
        if item.channel
    }

    items = db.scalars(select(ModelPricing).where(ModelPricing.is_active == True)).all()  # noqa: E712
    result: list[ModelItem] = []
    for item in items:
        channel = (item.upstream_channel or "").strip()
        if not channel:
            continue
        if channel not in enabled_channels:
            continue

        if None in (
            item.input_microusd_per_1m_tokens,
            item.cached_input_microusd_per_1m_tokens,
            item.output_microusd_per_1m_tokens,
            item.cached_output_microusd_per_1m_tokens,
        ):
            continue
        result.append(
            ModelItem(
                model=item.model,
                upstream_channel=channel,
                display_name=f"[{channel}] {item.model}",
                currency=item.currency,
                unit=item.unit,
                input_microusd_per_1m_tokens=item.input_microusd_per_1m_tokens,
                cached_input_microusd_per_1m_tokens=item.cached_input_microusd_per_1m_tokens,
                output_microusd_per_1m_tokens=item.output_microusd_per_1m_tokens,
                cached_output_microusd_per_1m_tokens=item.cached_output_microusd_per_1m_tokens,
            )
        )
    result.sort(key=lambda x: (x.upstream_channel.lower(), x.model.lower()))
    return result


@router.get("/live", response_model=list[ModelItem])
def list_live_models(_: CurrentUserDep, db: DbDep):
    enabled_channels = [
        item.channel
        for item in list_upstream_channels(db=db, include_disabled=False)
        if item.channel
    ]
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
            has_valid_pricing = bool(
                priced
                and None
                not in (
                    priced.input_microusd_per_1m_tokens,
                    priced.cached_input_microusd_per_1m_tokens,
                    priced.output_microusd_per_1m_tokens,
                    priced.cached_output_microusd_per_1m_tokens,
                )
            )
            result.append(
                ModelItem(
                    model=model,
                    upstream_channel=channel,
                    display_name=f"[{channel}] {model}",
                    currency=(priced.currency if priced else "USD") if has_valid_pricing else "USD",
                    unit=(priced.unit if priced else "1M_TOKENS") if has_valid_pricing else "1M_TOKENS",
                    input_microusd_per_1m_tokens=priced.input_microusd_per_1m_tokens if has_valid_pricing else 0,
                    cached_input_microusd_per_1m_tokens=(
                        priced.cached_input_microusd_per_1m_tokens if has_valid_pricing else 0
                    ),
                    output_microusd_per_1m_tokens=priced.output_microusd_per_1m_tokens if has_valid_pricing else 0,
                    cached_output_microusd_per_1m_tokens=(
                        priced.cached_output_microusd_per_1m_tokens if has_valid_pricing else 0
                    ),
                )
            )

    result.sort(key=lambda x: (x.upstream_channel.lower(), x.model.lower()))
    return result
