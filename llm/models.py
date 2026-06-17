from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class LLMRole(str, Enum):
    system = "system"
    user = "user"
    assistant = "assistant"


class LLMMessage(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    role: LLMRole
    content: str

    @field_validator("content")
    @classmethod
    def content_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("LLM message content is required.")
        return value


class LLMUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    @field_validator("prompt_tokens", "completion_tokens", "total_tokens")
    @classmethod
    def token_counts_must_not_be_negative(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("LLM token counts must be zero or greater.")
        return value


class LLMResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str
    parsed_json: dict[str, Any] | None = None
    model: str
    response_id: str | None = None
    finish_reason: str | None = None
    usage: LLMUsage
    latency_ms: int

    @field_validator("content")
    @classmethod
    def content_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("LLM response content is required.")
        return value

    @field_validator("latency_ms")
    @classmethod
    def latency_must_not_be_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("LLM latency must be zero or greater.")
        return value
