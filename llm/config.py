from __future__ import annotations

import os
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError, field_validator

from llm.errors import LLMConfigurationError


class LLMConfig(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    provider: Literal["openai_compatible"] = "openai_compatible"
    api_key: SecretStr
    base_url: str
    model: str
    timeout_seconds: float = 90
    max_retries: int = 2
    max_tokens: int = 8192
    temperature: float = 0

    @field_validator("api_key")
    @classmethod
    def api_key_must_not_be_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("LLM API key is required.")
        return value

    @field_validator("base_url")
    @classmethod
    def base_url_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("LLM base URL is required.")
        return value

    @field_validator("model")
    @classmethod
    def model_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("LLM model name is required.")
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def timeout_must_be_in_range(cls, value: float) -> float:
        if value <= 0 or value > 300:
            raise ValueError("LLM timeout must be greater than 0 and no more than 300 seconds.")
        return value

    @field_validator("max_retries")
    @classmethod
    def max_retries_must_be_in_range(cls, value: int) -> int:
        if value < 0 or value > 5:
            raise ValueError("LLM max_retries must be between 0 and 5.")
        return value

    @field_validator("max_tokens")
    @classmethod
    def max_tokens_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("LLM max_tokens must be greater than 0.")
        return value

    @field_validator("temperature")
    @classmethod
    def temperature_must_be_in_range(cls, value: float) -> float:
        if value < 0 or value > 2:
            raise ValueError("LLM temperature must be between 0 and 2.")
        return value

    @classmethod
    def from_env(cls) -> "LLMConfig":
        load_dotenv()
        raw_config: dict[str, Any] = {
            "provider": os.getenv("LLM_PROVIDER", "openai_compatible"),
            "api_key": os.getenv("LLM_API_KEY"),
            "base_url": os.getenv("LLM_BASE_URL"),
            "model": os.getenv("LLM_MODEL"),
            "timeout_seconds": os.getenv("LLM_TIMEOUT_SECONDS", "90"),
            "max_retries": os.getenv("LLM_MAX_RETRIES", "2"),
            "max_tokens": os.getenv("LLM_MAX_TOKENS", "8192"),
            "temperature": os.getenv("LLM_TEMPERATURE", "0"),
        }
        try:
            return cls.model_validate(raw_config)
        except ValidationError as exc:
            raise LLMConfigurationError(f"Invalid LLM configuration: {_summarize_validation(exc)}") from exc

    def redacted_summary(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "api_key_configured": bool(self.api_key.get_secret_value()),
        }

    def __repr__(self) -> str:
        return f"LLMConfig({self.redacted_summary()!r})"

    def __str__(self) -> str:
        return repr(self)


def _summarize_validation(error: ValidationError) -> str:
    parts: list[str] = []
    for item in error.errors():
        location = ".".join(str(part) for part in item.get("loc", ()))
        message = item.get("msg", "validation error")
        parts.append(f"{location}: {message}" if location else message)
    return "; ".join(parts)
