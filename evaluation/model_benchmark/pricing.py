from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


_SIX_PLACES = Decimal("0.000001")
_MILLION = Decimal("1000000")


@dataclass(frozen=True)
class PricingProfile:
    pricing_profile_id: str
    currency: str
    checked_at: str
    source_name: str
    cache_miss_input_cny_per_million: Decimal
    cache_hit_input_cny_per_million: Decimal
    output_cny_per_million: Decimal


FLASH_V4_2026_06 = PricingProfile(
    pricing_profile_id="flash-v4-2026-06",
    currency="CNY",
    checked_at="2026-06-26",
    source_name="DeepSeek V4 Pilot Snapshot",
    cache_miss_input_cny_per_million=Decimal("1.0"),
    cache_hit_input_cny_per_million=Decimal("0.02"),
    output_cny_per_million=Decimal("2.0"),
)

PRO_V4_2026_06 = PricingProfile(
    pricing_profile_id="pro-v4-2026-06",
    currency="CNY",
    checked_at="2026-06-26",
    source_name="DeepSeek V4 Pilot Snapshot",
    cache_miss_input_cny_per_million=Decimal("3.0"),
    cache_hit_input_cny_per_million=Decimal("0.025"),
    output_cny_per_million=Decimal("6.0"),
)

PRICING_PROFILES: dict[str, PricingProfile] = {
    FLASH_V4_2026_06.pricing_profile_id: FLASH_V4_2026_06,
    PRO_V4_2026_06.pricing_profile_id: PRO_V4_2026_06,
}


def get_pricing_profile(pricing_profile_id: str) -> PricingProfile:
    try:
        return PRICING_PROFILES[pricing_profile_id]
    except KeyError as exc:
        raise ValueError(f"Unknown pricing profile: {pricing_profile_id}") from exc


def estimate_request_cost(
    *,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    pricing_profile: PricingProfile,
) -> Decimal | None:
    if prompt_tokens is None or completion_tokens is None:
        return None
    prompt_cost = (Decimal(prompt_tokens) / _MILLION) * pricing_profile.cache_miss_input_cny_per_million
    completion_cost = (Decimal(completion_tokens) / _MILLION) * pricing_profile.output_cny_per_million
    return (prompt_cost + completion_cost).quantize(_SIX_PLACES)
