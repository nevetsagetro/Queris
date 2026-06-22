from decimal import Decimal

import pytest

from queris.usage import GenerationUsage, TokenPricing


def test_generation_usage_adds_and_subtracts_snapshots() -> None:
    earlier = GenerationUsage(input_tokens=10, output_tokens=2, total_tokens=12)
    request = GenerationUsage(input_tokens=5, output_tokens=3, total_tokens=8)
    later = earlier + request

    assert later - earlier == request


def test_generation_usage_rejects_inconsistent_total() -> None:
    with pytest.raises(ValueError, match="input plus output"):
        GenerationUsage(input_tokens=5, output_tokens=3, total_tokens=7)


def test_generation_usage_rejects_non_monotonic_snapshot() -> None:
    with pytest.raises(ValueError, match="monotonic"):
        GenerationUsage(total_tokens=1) - GenerationUsage(total_tokens=2)


def test_token_pricing_estimates_decimal_cost() -> None:
    usage = GenerationUsage(input_tokens=20, output_tokens=4, total_tokens=24)
    pricing = TokenPricing(
        input_usd_per_million=Decimal("1"),
        output_usd_per_million=Decimal("2"),
    )

    assert pricing.estimate_cost(usage) == Decimal("0.000028")
