from __future__ import annotations

from typing import Protocol

from llm.models import LLMMessage, LLMResponse


class LLMClient(Protocol):
    def list_model_ids(self) -> list[str]:
        ...

    def complete_text(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        ...

    def complete_json(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        ...
