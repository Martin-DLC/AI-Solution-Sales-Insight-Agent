from __future__ import annotations

from typing import Any, Protocol

from pydantic import Field

from schemas.common_models import StrictBaseModel


class ModelProviderResponse(StrictBaseModel):
    provider_name: str
    model_name: str
    content: str
    parsed_json: dict[str, Any] = Field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: str | None = None


class BaseModelProvider(Protocol):
    provider_name: str
    model_name: str
    supports_tool_calling: bool
    supports_structured_output: bool
    supports_long_context: bool
    supports_streaming: bool
    cost_profile: str
    latency_profile: str
    data_policy: str

    def health_check(self) -> bool:
        ...

    def generate(self, prompt: str, **kwargs: Any) -> ModelProviderResponse:
        ...

    def estimate_cost(self, input_text: str, output_text: str) -> str | None:
        ...
