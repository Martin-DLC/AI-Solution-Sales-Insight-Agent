from __future__ import annotations

import json
import time
from typing import Any

from llm.config import LLMConfig
from llm.errors import LLMJSONDecodeError, LLMRequestError, LLMResponseError
from llm.models import LLMMessage, LLMResponse, LLMUsage


class OpenAICompatibleClient:
    def __init__(self, config: LLMConfig, sdk_client: Any | None = None) -> None:
        self.config = config
        if sdk_client is not None:
            self._client = sdk_client
        else:
            try:
                from openai import OpenAI
            except Exception as exc:
                raise LLMRequestError(
                    "OpenAI SDK is not installed. Install project dependencies before using the live client."
                ) from exc
            self._client = OpenAI(
                api_key=config.api_key.get_secret_value(),
                base_url=config.base_url,
                timeout=config.timeout_seconds,
                max_retries=config.max_retries,
            )

    def list_model_ids(self) -> list[str]:
        try:
            models = self._client.models.list()
        except Exception as exc:
            raise LLMRequestError(f"Failed to list LLM models: {self._safe_error(exc)}") from exc
        return [item.id for item in models.data]

    def complete_text(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        return self._complete(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=None,
            parse_json=False,
        )

    def complete_json(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        if not any("json" in message.content.casefold() for message in messages):
            raise LLMRequestError(
                "JSON mode requires at least one message to explicitly ask for JSON."
            )
        return self._complete(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            parse_json=True,
        )

    def _complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None,
        max_tokens: int | None,
        response_format: dict[str, str] | None,
        parse_json: bool,
    ) -> LLMResponse:
        request_payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [_message_to_sdk(message) for message in messages],
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
        }
        if response_format is not None:
            request_payload["response_format"] = response_format

        started_at = time.perf_counter()
        try:
            response = self._client.chat.completions.create(**request_payload)
        except Exception as exc:
            raise LLMRequestError(f"LLM request failed: {self._safe_error(exc)}") from exc
        latency_ms = max(0, int((time.perf_counter() - started_at) * 1000))

        choices = getattr(response, "choices", None)
        if not choices:
            raise LLMRequestError("LLM response did not include choices.")

        first_choice = choices[0]
        message = getattr(first_choice, "message", None)
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise LLMResponseError("LLM response content is empty.")
        content = content.strip()

        parsed_json: dict[str, Any] | None = None
        if parse_json:
            try:
                decoded = json.loads(content)
            except json.JSONDecodeError as exc:
                raise LLMJSONDecodeError(
                    raw_content=content,
                    json_error_message=exc.msg,
                    json_error_position=exc.pos,
                ) from exc
            if not isinstance(decoded, dict):
                raise LLMResponseError("LLM JSON response must be a JSON object.")
            parsed_json = decoded

        return LLMResponse(
            content=content,
            parsed_json=parsed_json,
            model=getattr(response, "model", self.config.model),
            response_id=getattr(response, "id", None),
            finish_reason=getattr(first_choice, "finish_reason", None),
            usage=_extract_usage(getattr(response, "usage", None)),
            latency_ms=latency_ms,
        )

    def _safe_error(self, error: Exception) -> str:
        message = str(error) or error.__class__.__name__
        secret = self.config.api_key.get_secret_value()
        if secret:
            message = message.replace(secret, "[REDACTED]")
        return message


def _message_to_sdk(message: LLMMessage) -> dict[str, str]:
    return {"role": message.role.value, "content": message.content}


def _extract_usage(raw_usage: Any) -> LLMUsage:
    if raw_usage is None:
        return LLMUsage()
    return LLMUsage(
        prompt_tokens=getattr(raw_usage, "prompt_tokens", None),
        completion_tokens=getattr(raw_usage, "completion_tokens", None),
        total_tokens=getattr(raw_usage, "total_tokens", None),
    )
