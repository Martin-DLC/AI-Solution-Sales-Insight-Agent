from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from agent.workflow_c.state import WorkflowNodeName
from evaluation.model_benchmark.live_clients import DeepSeekBenchmarkClient, resolve_api_key
from evaluation.model_benchmark.models import ModelBenchmarkConfig, ModelTier
from llm.errors import LLMJSONDecodeError, LLMRequestError
from llm.models import LLMMessage, LLMRole


@dataclass
class FakeMessage:
    content: str | None
    reasoning_content: str | None = None


@dataclass
class FakeChoice:
    message: FakeMessage
    finish_reason: str = "stop"


@dataclass
class FakeUsage:
    prompt_tokens: int | None = 10
    completion_tokens: int | None = 5
    total_tokens: int | None = 15


@dataclass
class FakeResponse:
    choices: list[FakeChoice]
    model: str = "deepseek-v4-pro"
    usage: FakeUsage = field(default_factory=FakeUsage)


class FakeCompletions:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response or FakeResponse([FakeChoice(FakeMessage('{"ok": true}'))])
        self.error = error
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class FakeChat:
    def __init__(self, completions: FakeCompletions) -> None:
        self.completions = completions


class FakeSDK:
    def __init__(self, completions: FakeCompletions | None = None) -> None:
        self.chat = FakeChat(completions or FakeCompletions())


def _config(*, thinking_mode="disabled", reasoning_effort=None, temperature=0):
    return ModelBenchmarkConfig(
        config_id="ds-test",
        provider="deepseek",
        model="deepseek-v4-pro",
        tier=ModelTier.balanced if thinking_mode == "disabled" else ModelTier.strong_reasoning,
        thinking_mode=thinking_mode,
        reasoning_effort=reasoning_effort,
        temperature=temperature,
        max_tokens=8192,
        pricing_profile_id="pro-v4-2026-06",
        api_key_env="LLM_API_KEY",
    )


def _messages():
    return [LLMMessage(role=LLMRole.user, content="Return JSON object")]


def test_non_thinking_request_includes_temperature_and_disabled_flag() -> None:
    completions = FakeCompletions()
    client = DeepSeekBenchmarkClient(_config(), "NB-01", FakeSDK(completions))

    client.complete_json_for_node(WorkflowNodeName.fact_extraction, _messages())

    call = completions.calls[0]
    assert call["thinking"] == {"type": "disabled"}
    assert call["temperature"] == 0
    assert "reasoning_effort" not in call


def test_thinking_request_includes_reasoning_effort_and_omits_temperature() -> None:
    completions = FakeCompletions()
    client = DeepSeekBenchmarkClient(
        _config(thinking_mode="enabled", reasoning_effort="high", temperature=None),
        "NB-01",
        FakeSDK(completions),
    )

    client.complete_json_for_node(WorkflowNodeName.fact_extraction, _messages())

    call = completions.calls[0]
    assert call["thinking"] == {"type": "enabled"}
    assert call["reasoning_effort"] == "high"
    assert "temperature" not in call


def test_usage_and_reasoning_content_are_captured_in_call_record() -> None:
    response = FakeResponse([FakeChoice(FakeMessage('{"ok": true}', reasoning_content="internal reasoning"))])
    client = DeepSeekBenchmarkClient(_config(), "NB-01", FakeSDK(FakeCompletions(response=response)))

    result = client.complete_json_for_node(WorkflowNodeName.fact_extraction, _messages())

    assert result.usage.total_tokens == 15
    assert client.call_records[0].reasoning_content == "internal reasoning"


def test_invalid_json_raises_decode_error() -> None:
    response = FakeResponse([FakeChoice(FakeMessage("not json"))])
    client = DeepSeekBenchmarkClient(_config(), "NB-01", FakeSDK(FakeCompletions(response=response)))

    with pytest.raises(LLMJSONDecodeError):
        client.complete_json_for_node(WorkflowNodeName.fact_extraction, _messages())


def test_provider_error_is_wrapped_without_secret_leak() -> None:
    client = DeepSeekBenchmarkClient(
        _config(),
        "NB-01",
        FakeSDK(FakeCompletions(error=RuntimeError("bad auth sk-secret"))),
    )

    with pytest.raises(LLMRequestError) as exc_info:
        client.complete_json_for_node(WorkflowNodeName.fact_extraction, _messages())

    assert "sk-secret" not in str(exc_info.value)


def test_resolve_api_key_raises_when_missing(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(LLMRequestError):
        resolve_api_key("LLM_API_KEY", load_env=False)
