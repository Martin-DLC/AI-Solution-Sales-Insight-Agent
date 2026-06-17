from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any

import pytest

from llm.config import LLMConfig
from llm.errors import LLMJSONDecodeError, LLMRequestError, LLMResponseError
from llm.factory import create_llm_client
from llm.models import LLMMessage, LLMRole
from llm.openai_compatible import OpenAICompatibleClient


@dataclass
class FakeModel:
    id: str


@dataclass
class FakeMessage:
    content: str | None


@dataclass
class FakeChoice:
    message: FakeMessage
    finish_reason: str = "stop"


@dataclass
class FakeUsage:
    prompt_tokens: int | None = 3
    completion_tokens: int | None = 4
    total_tokens: int | None = 7


@dataclass
class FakeResponse:
    choices: list[FakeChoice]
    model: str = "fake-response-model"
    id: str = "resp_123"
    usage: FakeUsage = field(default_factory=FakeUsage)


class FakeModelsResource:
    def __init__(self, models: list[str] | None = None, error: Exception | None = None) -> None:
        self._models = models or ["model-a", "model-b"]
        self._error = error

    def list(self) -> Any:
        if self._error:
            raise self._error
        return type("ModelList", (), {"data": [FakeModel(model_id) for model_id in self._models]})()


class FakeCompletionsResource:
    def __init__(self, response: FakeResponse | None = None, error: Exception | None = None) -> None:
        self.response = response or FakeResponse([FakeChoice(FakeMessage("hello"))])
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class FakeChatResource:
    def __init__(self, completions: FakeCompletionsResource) -> None:
        self.completions = completions


class FakeSDKClient:
    def __init__(
        self,
        *,
        models: FakeModelsResource | None = None,
        completions: FakeCompletionsResource | None = None,
    ) -> None:
        self.models = models or FakeModelsResource()
        self.chat = FakeChatResource(completions or FakeCompletionsResource())


def make_config(api_key: str = "sk-test-secret") -> LLMConfig:
    return LLMConfig(
        api_key=api_key,
        base_url="https://api.example.com",
        model="model-a",
    )


def make_client(fake_sdk: FakeSDKClient | None = None) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(make_config(), sdk_client=fake_sdk or FakeSDKClient())


def sample_messages() -> list[LLMMessage]:
    return [LLMMessage(role=LLMRole.user, content="Say hello")]


def test_list_model_ids_returns_model_list() -> None:
    client = make_client(FakeSDKClient(models=FakeModelsResource(["a", "b"])))

    assert client.list_model_ids() == ["a", "b"]


def test_complete_text_converts_messages() -> None:
    completions = FakeCompletionsResource()
    client = make_client(FakeSDKClient(completions=completions))

    client.complete_text(sample_messages())

    assert completions.calls[0]["messages"] == [{"role": "user", "content": "Say hello"}]


def test_complete_text_extracts_content_and_usage() -> None:
    client = make_client()

    response = client.complete_text(sample_messages())

    assert response.content == "hello"
    assert response.usage.total_tokens == 7


def test_method_args_override_temperature_and_max_tokens() -> None:
    completions = FakeCompletionsResource()
    client = make_client(FakeSDKClient(completions=completions))

    client.complete_text(sample_messages(), temperature=0.3, max_tokens=12)

    assert completions.calls[0]["temperature"] == 0.3
    assert completions.calls[0]["max_tokens"] == 12


def test_api_exception_is_converted_to_llm_request_error() -> None:
    client = make_client(FakeSDKClient(completions=FakeCompletionsResource(error=RuntimeError("boom"))))

    with pytest.raises(LLMRequestError, match="boom"):
        client.complete_text(sample_messages())


def test_empty_choices_raise_llm_request_error() -> None:
    client = make_client(FakeSDKClient(completions=FakeCompletionsResource(FakeResponse([]))))

    with pytest.raises(LLMRequestError, match="choices"):
        client.complete_text(sample_messages())


def test_empty_content_raises_llm_response_error() -> None:
    response = FakeResponse([FakeChoice(FakeMessage("  "))])
    client = make_client(FakeSDKClient(completions=FakeCompletionsResource(response)))

    with pytest.raises(LLMResponseError, match="empty"):
        client.complete_text(sample_messages())


def test_complete_json_sets_json_object_response_format() -> None:
    completions = FakeCompletionsResource(FakeResponse([FakeChoice(FakeMessage('{"ok": true}'))]))
    client = make_client(FakeSDKClient(completions=completions))

    client.complete_json([LLMMessage(role=LLMRole.user, content="Return JSON please")])

    assert completions.calls[0]["response_format"] == {"type": "json_object"}


def test_complete_json_parses_valid_json_object() -> None:
    client = make_client(
        FakeSDKClient(
            completions=FakeCompletionsResource(FakeResponse([FakeChoice(FakeMessage('{"ok": true}'))]))
        )
    )

    response = client.complete_json([LLMMessage(role=LLMRole.user, content="Return JSON")])

    assert response.parsed_json == {"ok": True}


def test_complete_json_without_json_instruction_fails_before_call() -> None:
    completions = FakeCompletionsResource()
    client = make_client(FakeSDKClient(completions=completions))

    with pytest.raises(LLMRequestError, match="JSON mode"):
        client.complete_json(sample_messages())

    assert completions.calls == []


def test_complete_json_invalid_json_fails() -> None:
    client = make_client(
        FakeSDKClient(completions=FakeCompletionsResource(FakeResponse([FakeChoice(FakeMessage("nope"))])))
    )

    with pytest.raises(LLMJSONDecodeError, match="valid JSON"):
        client.complete_json([LLMMessage(role=LLMRole.user, content="Return JSON")])


def test_complete_json_invalid_json_error_keeps_raw_content() -> None:
    raw_content = "This is not JSON but should be preserved."
    client = make_client(
        FakeSDKClient(
            completions=FakeCompletionsResource(FakeResponse([FakeChoice(FakeMessage(raw_content))]))
        )
    )

    with pytest.raises(LLMJSONDecodeError) as exc_info:
        client.complete_json([LLMMessage(role=LLMRole.user, content="Return JSON")])

    assert exc_info.value.raw_content == raw_content
    assert exc_info.value.content_length == len(raw_content)
    assert exc_info.value.json_error_position == 0


def test_json_decode_error_string_does_not_include_raw_content() -> None:
    raw_content = "Customer-specific ordinary text that should not be in logs."
    client = make_client(
        FakeSDKClient(
            completions=FakeCompletionsResource(FakeResponse([FakeChoice(FakeMessage(raw_content))]))
        )
    )

    with pytest.raises(LLMJSONDecodeError) as exc_info:
        client.complete_json([LLMMessage(role=LLMRole.user, content="Return JSON")])

    assert raw_content not in str(exc_info.value)
    assert raw_content not in repr(exc_info.value)


def test_complete_json_markdown_code_fence_fails_strict_json() -> None:
    raw_content = '```json\n{"ok": true}\n```'
    client = make_client(
        FakeSDKClient(
            completions=FakeCompletionsResource(FakeResponse([FakeChoice(FakeMessage(raw_content))]))
        )
    )

    with pytest.raises(LLMJSONDecodeError) as exc_info:
        client.complete_json([LLMMessage(role=LLMRole.user, content="Return JSON")])

    assert exc_info.value.raw_content == raw_content


def test_complete_json_array_fails() -> None:
    client = make_client(
        FakeSDKClient(completions=FakeCompletionsResource(FakeResponse([FakeChoice(FakeMessage("[1]"))])))
    )

    with pytest.raises(LLMResponseError, match="JSON object"):
        client.complete_json([LLMMessage(role=LLMRole.user, content="Return JSON")])


def test_json_response_parsed_json_is_set() -> None:
    client = make_client(
        FakeSDKClient(
            completions=FakeCompletionsResource(FakeResponse([FakeChoice(FakeMessage('{"status":"ok"}'))]))
        )
    )

    response = client.complete_json([LLMMessage(role=LLMRole.user, content="Return JSON")])

    assert response.parsed_json == {"status": "ok"}


def test_api_key_is_not_in_exception_message() -> None:
    secret = "sk-secret-should-not-leak"
    client = OpenAICompatibleClient(
        make_config(secret),
        sdk_client=FakeSDKClient(completions=FakeCompletionsResource(error=RuntimeError(secret))),
    )

    with pytest.raises(LLMRequestError) as exc_info:
        client.complete_text(sample_messages())

    assert secret not in str(exc_info.value)


def test_latency_ms_is_non_negative() -> None:
    response = make_client().complete_text(sample_messages())

    assert response.latency_ms >= 0


def test_create_llm_client_returns_correct_implementation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("llm.factory.OpenAICompatibleClient", lambda config: ("client", config.model))

    client = create_llm_client(make_config())

    assert client == ("client", "model-a")


def test_importing_module_does_not_create_network_client() -> None:
    module = importlib.import_module("llm.openai_compatible")

    assert hasattr(module, "OpenAICompatibleClient")
