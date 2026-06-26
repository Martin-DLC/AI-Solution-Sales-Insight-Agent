from __future__ import annotations

from decimal import Decimal

from evaluation.model_benchmark.pricing import (
    FLASH_V4_2026_06,
    PRO_V4_2026_06,
    estimate_request_cost,
)


def test_flash_cost_estimate_uses_cache_miss_pricing() -> None:
    cost = estimate_request_cost(
        prompt_tokens=1000,
        completion_tokens=500,
        pricing_profile=FLASH_V4_2026_06,
    )
    assert cost == Decimal("0.002000")


def test_pro_cost_estimate_uses_expected_profile() -> None:
    cost = estimate_request_cost(
        prompt_tokens=1000,
        completion_tokens=500,
        pricing_profile=PRO_V4_2026_06,
    )
    assert cost == Decimal("0.006000")


def test_missing_tokens_return_none() -> None:
    assert estimate_request_cost(
        prompt_tokens=None,
        completion_tokens=500,
        pricing_profile=FLASH_V4_2026_06,
    ) is None


def test_cost_precision_stays_decimal() -> None:
    cost = estimate_request_cost(
        prompt_tokens=123,
        completion_tokens=456,
        pricing_profile=PRO_V4_2026_06,
    )
    assert isinstance(cost, Decimal)
    assert cost == Decimal("0.003105")
