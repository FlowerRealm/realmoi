from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..db import SessionLocal
from ..models import ModelPricing, UsageRecord
from ..services.pricing import Pricing, TokenUsage, compute_cost_microusd


def ingest_usage_record(*, job_id: str, owner_user_id: str, attempt: int, job_dir: Path) -> None:
    """Read usage.json for one attempt and persist usage_records row.

    Args:
        job_id: Job identifier.
        owner_user_id: Job owner id.
        attempt: Attempt number.
        job_dir: Job root directory.
    """

    usage_path = job_dir / "output" / "artifacts" / f"attempt_{attempt}" / "usage.json"
    if not usage_path.exists():
        return

    try:
        usage_obj = json.loads(usage_path.read_text(encoding="utf-8"))
    except Exception:
        return

    usage = usage_obj.get("usage") or {}
    model = str(usage_obj.get("model") or "")
    if not model:
        return

    token_usage = TokenUsage(
        input_tokens=int(usage.get("input_tokens") or 0),
        cached_input_tokens=int(usage.get("cached_input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        cached_output_tokens=int(usage.get("cached_output_tokens") or 0),
    )

    with SessionLocal() as db:
        pricing_row = db.get(ModelPricing, model)
        if (
            not pricing_row
            or pricing_row.input_microusd_per_1m_tokens is None
            or pricing_row.cached_input_microusd_per_1m_tokens is None
            or pricing_row.output_microusd_per_1m_tokens is None
            or pricing_row.cached_output_microusd_per_1m_tokens is None
        ):
            cost = None
            snap = (None, None, None, None)
        else:
            pricing = Pricing(
                currency=pricing_row.currency,
                input_microusd_per_1m_tokens=pricing_row.input_microusd_per_1m_tokens,
                cached_input_microusd_per_1m_tokens=pricing_row.cached_input_microusd_per_1m_tokens,
                output_microusd_per_1m_tokens=pricing_row.output_microusd_per_1m_tokens,
                cached_output_microusd_per_1m_tokens=pricing_row.cached_output_microusd_per_1m_tokens,
            )
            cost = compute_cost_microusd(token_usage, pricing)
            snap = (
                pricing.input_microusd_per_1m_tokens,
                pricing.cached_input_microusd_per_1m_tokens,
                pricing.output_microusd_per_1m_tokens,
                pricing.cached_output_microusd_per_1m_tokens,
            )

        rec = UsageRecord(
            job_id=job_id,
            owner_user_id=owner_user_id,
            stage="generate",
            model=model,
            codex_thread_id=str(usage_obj.get("codex_thread_id") or "") or None,
            input_tokens=token_usage.input_tokens,
            cached_input_tokens=token_usage.cached_input_tokens,
            output_tokens=token_usage.output_tokens,
            cached_output_tokens=token_usage.cached_output_tokens,
            currency="USD",
            input_microusd_per_1m_tokens=snap[0],
            cached_input_microusd_per_1m_tokens=snap[1],
            output_microusd_per_1m_tokens=snap[2],
            cached_output_microusd_per_1m_tokens=snap[3],
            cost_microusd=cost,
        )
        db.add(rec)
        db.commit()


def ingest_usage_payload(*, job_id: str, owner_user_id: str, attempt: int, payload: dict[str, Any]) -> None:
    """Persist one usage_records row from usage payload.

    Args:
        job_id: Job identifier.
        owner_user_id: Job owner id.
        attempt: Attempt number (kept for symmetry; UsageRecord schema doesn't store it).
        payload: Usage payload (same as output/artifacts/attempt_{attempt}/usage.json).
    """

    usage = payload.get("usage") or {}
    model = str(payload.get("model") or "")
    if not model:
        return

    token_usage = TokenUsage(
        input_tokens=int(usage.get("input_tokens") or 0),
        cached_input_tokens=int(usage.get("cached_input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        cached_output_tokens=int(usage.get("cached_output_tokens") or 0),
    )

    with SessionLocal() as db:
        pricing_row = db.get(ModelPricing, model)
        if (
            not pricing_row
            or pricing_row.input_microusd_per_1m_tokens is None
            or pricing_row.cached_input_microusd_per_1m_tokens is None
            or pricing_row.output_microusd_per_1m_tokens is None
            or pricing_row.cached_output_microusd_per_1m_tokens is None
        ):
            cost = None
            snap = (None, None, None, None)
        else:
            pricing = Pricing(
                currency=pricing_row.currency,
                input_microusd_per_1m_tokens=pricing_row.input_microusd_per_1m_tokens,
                cached_input_microusd_per_1m_tokens=pricing_row.cached_input_microusd_per_1m_tokens,
                output_microusd_per_1m_tokens=pricing_row.output_microusd_per_1m_tokens,
                cached_output_microusd_per_1m_tokens=pricing_row.cached_output_microusd_per_1m_tokens,
            )
            cost = compute_cost_microusd(token_usage, pricing)
            snap = (
                pricing.input_microusd_per_1m_tokens,
                pricing.cached_input_microusd_per_1m_tokens,
                pricing.output_microusd_per_1m_tokens,
                pricing.cached_output_microusd_per_1m_tokens,
            )

        rec = UsageRecord(
            job_id=job_id,
            owner_user_id=owner_user_id,
            stage="generate",
            model=model,
            codex_thread_id=str(payload.get("codex_thread_id") or "") or None,
            input_tokens=token_usage.input_tokens,
            cached_input_tokens=token_usage.cached_input_tokens,
            output_tokens=token_usage.output_tokens,
            cached_output_tokens=token_usage.cached_output_tokens,
            currency="USD",
            input_microusd_per_1m_tokens=snap[0],
            cached_input_microusd_per_1m_tokens=snap[1],
            output_microusd_per_1m_tokens=snap[2],
            cached_output_microusd_per_1m_tokens=snap[3],
            cost_microusd=cost,
        )
        db.add(rec)
        db.commit()
