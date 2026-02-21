#
# Usage/pricing helpers.
#
from __future__ import annotations

from dataclasses import dataclass


MICROUSD_PER_USD = 1_000_000
TOKENS_PER_UNIT = 1_000_000


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    cached_output_tokens: int


@dataclass(frozen=True)
class Pricing:
    currency: str
    input_microusd_per_1m_tokens: int
    cached_input_microusd_per_1m_tokens: int
    output_microusd_per_1m_tokens: int
    cached_output_microusd_per_1m_tokens: int


def compute_cost_microusd(usage: TokenUsage, pricing: Pricing) -> int:
    """
    Compute cost in microusd.

    This uses integer division to avoid floating-point drift.
    """

    numerator = (
        usage.input_tokens * pricing.input_microusd_per_1m_tokens
        + usage.cached_input_tokens * pricing.cached_input_microusd_per_1m_tokens
        + usage.output_tokens * pricing.output_microusd_per_1m_tokens
        + usage.cached_output_tokens * pricing.cached_output_microusd_per_1m_tokens
    )
    return numerator // TOKENS_PER_UNIT


def microusd_to_amount_str(cost_microusd: int) -> str:
    whole = cost_microusd // MICROUSD_PER_USD
    frac = cost_microusd % MICROUSD_PER_USD
    return f"{whole}.{frac:06d}"
