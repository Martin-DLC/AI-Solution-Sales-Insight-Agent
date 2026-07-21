from __future__ import annotations

import json
from enum import Enum
from typing import Any

from agent.model_providers.base import ModelProviderResponse
from agent.recovery.models import ErrorType


class MockProviderFailureMode(str, Enum):
    none = "none"
    model_timeout = "model_timeout"
    model_schema_invalid = "model_schema_invalid"
    model_unavailable = "model_unavailable"


class MockModelProvider:
    def __init__(
        self,
        *,
        provider_name: str = "mock_primary",
        model_name: str = "mock-model-v1",
        failure_mode: MockProviderFailureMode | str = MockProviderFailureMode.none,
    ) -> None:
        self.provider_name = provider_name
        self.model_name = model_name
        self.failure_mode = MockProviderFailureMode(failure_mode)
        self.supports_tool_calling = False
        self.supports_structured_output = True
        self.supports_long_context = False
        self.supports_streaming = False
        self.cost_profile = "placeholder"
        self.latency_profile = "local_fast"
        self.data_policy = "local_mock_no_network"

    def health_check(self) -> bool:
        return self.failure_mode is not MockProviderFailureMode.model_unavailable

    def generate(self, prompt: str, **kwargs: Any) -> ModelProviderResponse:
        if self.failure_mode is MockProviderFailureMode.model_timeout:
            raise TimeoutError(ErrorType.model_timeout.value)
        if self.failure_mode is MockProviderFailureMode.model_unavailable:
            raise RuntimeError(ErrorType.model_unavailable.value)
        if self.failure_mode is MockProviderFailureMode.model_schema_invalid:
            return ModelProviderResponse(
                provider_name=self.provider_name,
                model_name=self.model_name,
                content="not-json",
                parsed_json={},
                input_tokens=_estimate_tokens(prompt),
                output_tokens=1,
            )
        parsed = {
            "provider": self.provider_name,
            "model": self.model_name,
            "summary": "deterministic mock response",
        }
        content = json.dumps(parsed, ensure_ascii=False)
        return ModelProviderResponse(
            provider_name=self.provider_name,
            model_name=self.model_name,
            content=content,
            parsed_json=parsed,
            input_tokens=_estimate_tokens(prompt),
            output_tokens=_estimate_tokens(content),
            estimated_cost="0",
        )

    def estimate_cost(self, input_text: str, output_text: str) -> str | None:
        return "0"


def _estimate_tokens(value: str) -> int:
    normalized = " ".join(value.split())
    return max(1, len(normalized) // 4) if normalized else 0
