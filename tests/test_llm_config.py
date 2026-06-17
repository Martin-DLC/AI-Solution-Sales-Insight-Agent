from __future__ import annotations

import pytest

from llm.config import LLMConfig
from llm.errors import LLMConfigurationError


VALID_ENV = {
    "LLM_PROVIDER": "openai_compatible",
    "LLM_API_KEY": "sk-test-secret",
    "LLM_BASE_URL": "https://api.example.com",
    "LLM_MODEL": "example-model",
    "LLM_TIMEOUT_SECONDS": "30.5",
    "LLM_MAX_RETRIES": "3",
    "LLM_MAX_TOKENS": "1024",
    "LLM_TEMPERATURE": "0.7",
}


def apply_env(monkeypatch: pytest.MonkeyPatch, values: dict[str, str | None]) -> None:
    monkeypatch.setattr("llm.config.load_dotenv", lambda: None)
    for key in VALID_ENV:
        monkeypatch.delenv(key, raising=False)
    for key, value in values.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def test_valid_env_creates_config(monkeypatch: pytest.MonkeyPatch) -> None:
    apply_env(monkeypatch, VALID_ENV)

    config = LLMConfig.from_env()

    assert config.provider == "openai_compatible"
    assert config.model == "example-model"


def test_missing_api_key_raises_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {**VALID_ENV, "LLM_API_KEY": ""}
    apply_env(monkeypatch, env)

    with pytest.raises(LLMConfigurationError):
        LLMConfig.from_env()


def test_missing_model_name_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {**VALID_ENV, "LLM_MODEL": ""}
    apply_env(monkeypatch, env)

    with pytest.raises(LLMConfigurationError):
        LLMConfig.from_env()


def test_timeout_less_than_or_equal_to_zero_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {**VALID_ENV, "LLM_TIMEOUT_SECONDS": "0"}
    apply_env(monkeypatch, env)

    with pytest.raises(LLMConfigurationError):
        LLMConfig.from_env()


def test_timeout_greater_than_300_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {**VALID_ENV, "LLM_TIMEOUT_SECONDS": "301"}
    apply_env(monkeypatch, env)

    with pytest.raises(LLMConfigurationError):
        LLMConfig.from_env()


def test_max_retries_greater_than_5_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {**VALID_ENV, "LLM_MAX_RETRIES": "6"}
    apply_env(monkeypatch, env)

    with pytest.raises(LLMConfigurationError):
        LLMConfig.from_env()


def test_temperature_outside_range_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {**VALID_ENV, "LLM_TEMPERATURE": "2.1"}
    apply_env(monkeypatch, env)

    with pytest.raises(LLMConfigurationError):
        LLMConfig.from_env()


def test_redacted_summary_does_not_include_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    apply_env(monkeypatch, VALID_ENV)

    summary = LLMConfig.from_env().redacted_summary()

    assert "sk-test-secret" not in str(summary)
    assert summary["api_key_configured"] is True


def test_str_and_repr_do_not_include_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    apply_env(monkeypatch, VALID_ENV)

    config = LLMConfig.from_env()

    assert "sk-test-secret" not in str(config)
    assert "sk-test-secret" not in repr(config)


def test_numeric_env_vars_are_converted(monkeypatch: pytest.MonkeyPatch) -> None:
    apply_env(monkeypatch, VALID_ENV)

    config = LLMConfig.from_env()

    assert config.timeout_seconds == 30.5
    assert config.max_retries == 3
    assert config.max_tokens == 1024
    assert config.temperature == 0.7
