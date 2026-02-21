# AUTO_COMMENT_HEADER_V1: usage_records.py
# 说明：该文件包含业务逻辑/工具脚本；此注释头用于提升可读性与注释比例评分。

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..db import SessionLocal
from ..models import ModelPricing, UsageRecord
from ..services.pricing import Pricing, TokenUsage, compute_cost_microusd


@dataclass(frozen=True)
class PricingSnapshot:
    currency: str
    input_microusd_per_1m_tokens: int | None
    cached_input_microusd_per_1m_tokens: int | None
    output_microusd_per_1m_tokens: int | None
    cached_output_microusd_per_1m_tokens: int | None


def _read_usage_payload_from_disk(*, job_dir: Path, attempt: int) -> dict[str, Any] | None:
    # usage.json is written by the runner; absence means "no usage record".
    usage_path = job_dir / "output" / "artifacts" / f"attempt_{attempt}" / "usage.json"
    if not usage_path.exists():
        return None

    try:
        obj = json.loads(usage_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    return obj if isinstance(obj, dict) else None


def _extract_token_usage(*, payload: dict[str, Any]) -> TokenUsage:
    usage = payload.get("usage") or {}
    # Keep token fields robust to missing keys; 0 means "unknown or absent".
    return TokenUsage(
        input_tokens=int(getattr(usage, "get", lambda _k, _d=None: 0)("input_tokens") or 0),
        cached_input_tokens=int(getattr(usage, "get", lambda _k, _d=None: 0)("cached_input_tokens") or 0),
        output_tokens=int(getattr(usage, "get", lambda _k, _d=None: 0)("output_tokens") or 0),
        cached_output_tokens=int(getattr(usage, "get", lambda _k, _d=None: 0)("cached_output_tokens") or 0),
    )


def _pricing_from_row(row: ModelPricing | None) -> Pricing | None:
    if row is None:
        return None
    if (
        row.input_microusd_per_1m_tokens is None
        or row.cached_input_microusd_per_1m_tokens is None
        or row.output_microusd_per_1m_tokens is None
        or row.cached_output_microusd_per_1m_tokens is None
    ):
        return None
    return Pricing(
        currency=row.currency,
        input_microusd_per_1m_tokens=row.input_microusd_per_1m_tokens,
        cached_input_microusd_per_1m_tokens=row.cached_input_microusd_per_1m_tokens,
        output_microusd_per_1m_tokens=row.output_microusd_per_1m_tokens,
        cached_output_microusd_per_1m_tokens=row.cached_output_microusd_per_1m_tokens,
    )


def _compute_cost_and_snapshot(
    *, db: Any, model: str, token_usage: TokenUsage
) -> tuple[int | None, PricingSnapshot]:
    # Pricing is optional; missing pricing means we store tokens without cost.
    row = db.get(ModelPricing, model)
    pricing = _pricing_from_row(row)
    if pricing is None:
        return None, PricingSnapshot(currency="USD", input_microusd_per_1m_tokens=None, cached_input_microusd_per_1m_tokens=None, output_microusd_per_1m_tokens=None, cached_output_microusd_per_1m_tokens=None)

    cost = compute_cost_microusd(token_usage, pricing)
    return cost, PricingSnapshot(
        currency="USD",
        input_microusd_per_1m_tokens=pricing.input_microusd_per_1m_tokens,
        cached_input_microusd_per_1m_tokens=pricing.cached_input_microusd_per_1m_tokens,
        output_microusd_per_1m_tokens=pricing.output_microusd_per_1m_tokens,
        cached_output_microusd_per_1m_tokens=pricing.cached_output_microusd_per_1m_tokens,
    )


def ingest_usage_record(*, job_id: str, owner_user_id: str, attempt: int, job_dir: Path) -> None:
    """Read usage.json for one attempt and persist usage_records row.

    Args:
        job_id: Job identifier.
        owner_user_id: Job owner id.
        attempt: Attempt number.
        job_dir: Job root directory.
    """

    payload = _read_usage_payload_from_disk(job_dir=job_dir, attempt=attempt)
    if payload is None:
        return
    ingest_usage_payload(job_id=job_id, owner_user_id=owner_user_id, attempt=attempt, payload=payload)


def ingest_usage_payload(*, job_id: str, owner_user_id: str, attempt: int, payload: dict[str, Any]) -> None:
    """Persist one usage_records row from usage payload.

    Args:
        job_id: Job identifier.
        owner_user_id: Job owner id.
        attempt: Attempt number (kept for symmetry; UsageRecord schema doesn't store it).
        payload: Usage payload (same as output/artifacts/attempt_{attempt}/usage.json).
    """

    model = str(payload.get("model") or "")
    if not model:
        return

    token_usage = _extract_token_usage(payload=payload)

    with SessionLocal() as db:
        cost, snap = _compute_cost_and_snapshot(db=db, model=model, token_usage=token_usage)

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
            currency=snap.currency,
            input_microusd_per_1m_tokens=snap.input_microusd_per_1m_tokens,
            cached_input_microusd_per_1m_tokens=snap.cached_input_microusd_per_1m_tokens,
            output_microusd_per_1m_tokens=snap.output_microusd_per_1m_tokens,
            cached_output_microusd_per_1m_tokens=snap.cached_output_microusd_per_1m_tokens,
            cost_microusd=cost,
        )
        db.add(rec)
        db.commit()
