from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from pydantic import Field, field_validator

from schemas.common_models import StrictBaseModel


DEFAULT_MODEL_COSTS_PATH = Path("config/model_costs.yaml")


class ModelCostPolicy(StrictBaseModel):
    provider_name: str
    model_name: str
    input_cost_per_1k_tokens: Decimal
    output_cost_per_1k_tokens: Decimal
    currency: str
    pricing_type: str
    notes: str

    @field_validator("input_cost_per_1k_tokens", "output_cost_per_1k_tokens")
    @classmethod
    def costs_must_not_be_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("Model cost values must not be negative.")
        return value


class CostEstimate(StrictBaseModel):
    provider_name: str
    input_tokens: int
    output_tokens: int
    estimated_model_cost: Decimal | None = None
    currency: str | None = None
    cost_is_estimated: bool = True
    warnings: list[str] = Field(default_factory=list)


class CostSummary(StrictBaseModel):
    estimated_model_cost: Decimal | None = None
    currency: str | None = None
    cost_is_estimated: bool = True
    warnings: list[str] = Field(default_factory=list)


class CostTracker:
    def __init__(
        self,
        *,
        policies: dict[str, ModelCostPolicy] | None = None,
        policy_source: str | Path = DEFAULT_MODEL_COSTS_PATH,
    ) -> None:
        self.policy_source = str(policy_source)
        self._policies = policies or load_model_costs(policy_source)

    def estimate_token_count(self, text: str | None) -> int:
        if not text:
            return 0
        normalized = " ".join(text.split())
        if not normalized:
            return 0
        ascii_words = sum(1 for part in normalized.split(" ") if part.isascii())
        non_ascii_chars = sum(1 for char in normalized if not char.isascii() and not char.isspace())
        punctuation = sum(1 for char in normalized if char in ",.;:!?，。；：！？")
        return max(1, ascii_words + (non_ascii_chars + 1) // 2 + punctuation)

    def estimate_model_cost(
        self,
        *,
        provider_name: str,
        input_text: str | None,
        output_text: str | None,
    ) -> CostEstimate:
        return self.estimate_from_usage(
            provider_name=provider_name,
            input_tokens=self.estimate_token_count(input_text),
            output_tokens=self.estimate_token_count(output_text),
        )

    def estimate_from_usage(
        self,
        *,
        provider_name: str,
        input_tokens: int,
        output_tokens: int,
    ) -> CostEstimate:
        policy = self._policies.get(provider_name)
        if policy is None:
            return CostEstimate(
                provider_name=provider_name,
                input_tokens=max(0, input_tokens),
                output_tokens=max(0, output_tokens),
                estimated_model_cost=None,
                currency=None,
                warnings=[f"unknown_provider:{provider_name}"],
            )
        cost = (
            Decimal(max(0, input_tokens)) / Decimal("1000") * policy.input_cost_per_1k_tokens
            + Decimal(max(0, output_tokens)) / Decimal("1000") * policy.output_cost_per_1k_tokens
        )
        return CostEstimate(
            provider_name=provider_name,
            input_tokens=max(0, input_tokens),
            output_tokens=max(0, output_tokens),
            estimated_model_cost=cost.quantize(Decimal("0.000001")),
            currency=policy.currency,
            warnings=[] if policy.pricing_type != "placeholder" else [f"placeholder_pricing:{provider_name}"],
        )

    def summarize_costs(self, run_metrics: object) -> CostSummary:
        amount = getattr(run_metrics, "estimated_model_cost", None)
        return CostSummary(
            estimated_model_cost=amount,
            currency="CNY",
            cost_is_estimated=True,
            warnings=[],
        )


def load_model_costs(path: str | Path = DEFAULT_MODEL_COSTS_PATH) -> dict[str, ModelCostPolicy]:
    resolved = Path(path)
    items = _parse_model_cost_yaml(resolved.read_text(encoding="utf-8"))
    policies = [ModelCostPolicy.model_validate(item) for item in items]
    return {policy.provider_name: policy for policy in policies}


def _parse_model_cost_yaml(content: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line == "models:":
            continue
        if line.startswith("- "):
            if current is not None:
                items.append(current)
            current = {}
            line = line[2:].strip()
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        current[key.strip()] = _parse_scalar(value.strip())
    if current is not None:
        items.append(current)
    return items


def _parse_scalar(value: str) -> object:
    if value.casefold() == "true":
        return True
    if value.casefold() == "false":
        return False
    return value.strip('"').strip("'")
