from __future__ import annotations

from backend.app.services.pricing import Pricing, TokenUsage, compute_cost_microusd, microusd_to_amount_str


def test_compute_cost_microusd_basic():
    usage = TokenUsage(input_tokens=1_000_000, cached_input_tokens=0, output_tokens=0, cached_output_tokens=0)
    pricing = Pricing(
        currency="USD",
        input_microusd_per_1m_tokens=1_000_000,
        cached_input_microusd_per_1m_tokens=0,
        output_microusd_per_1m_tokens=0,
        cached_output_microusd_per_1m_tokens=0,
    )
    assert compute_cost_microusd(usage, pricing) == 1_000_000
    assert microusd_to_amount_str(1_000_000) == "1.000000"


def test_compute_cost_microusd_truncates_fractional():
    usage = TokenUsage(input_tokens=1, cached_input_tokens=0, output_tokens=0, cached_output_tokens=0)
    pricing = Pricing(
        currency="USD",
        input_microusd_per_1m_tokens=1_000_000,
        cached_input_microusd_per_1m_tokens=0,
        output_microusd_per_1m_tokens=0,
        cached_output_microusd_per_1m_tokens=0,
    )
    assert compute_cost_microusd(usage, pricing) == 1  # 1 token at $1 / 1M tokens => 1 microusd

