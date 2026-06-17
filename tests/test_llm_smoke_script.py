from __future__ import annotations

from dataclasses import dataclass

import pytest

from llm.errors import LLMRequestError
from llm.models import LLMResponse, LLMUsage
from scripts import smoke_test_llm


@dataclass
class FakeConfig:
    model: str = "fake-model"

    def redacted_summary(self) -> dict[str, object]:
        return {
            "provider": "openai_compatible",
            "base_url": "https://api.example.com",
            "model": self.model,
            "api_key_configured": True,
        }


class FakeClient:
    def __init__(self, *, model_ids: list[str] | None = None, error: Exception | None = None) -> None:
        self.model_ids = model_ids or ["fake-model"]
        self.error = error

    def list_model_ids(self) -> list[str]:
        if self.error:
            raise self.error
        return self.model_ids

    def complete_json(self, messages, *, max_tokens=None, temperature=None):
        if self.error:
            raise self.error
        return LLMResponse(
            content='{"status":"ok","message":"PONG"}',
            parsed_json={"status": "ok", "message": "PONG"},
            model="fake-model",
            response_id="resp_123",
            finish_reason="stop",
            usage=LLMUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
            latency_ms=5,
        )


def test_without_live_does_not_call_create_llm_client(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_create_llm_client(config=None):
        nonlocal called
        called = True
        return FakeClient()

    monkeypatch.setattr(smoke_test_llm, "create_llm_client", fake_create_llm_client)

    smoke_test_llm.main([])

    assert called is False


def test_without_live_returns_zero() -> None:
    assert smoke_test_llm.main([]) == 0


def test_live_success_path_uses_fake_client(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(smoke_test_llm.LLMConfig, "from_env", lambda: FakeConfig())
    monkeypatch.setattr(smoke_test_llm, "create_llm_client", lambda config: FakeClient())

    result = smoke_test_llm.main(["--live"])

    assert result == 0
    assert "LLM smoke test passed." in capsys.readouterr().out


def test_live_model_not_in_model_list_returns_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smoke_test_llm.LLMConfig, "from_env", lambda: FakeConfig())
    monkeypatch.setattr(
        smoke_test_llm,
        "create_llm_client",
        lambda config: FakeClient(model_ids=["other-model"]),
    )

    assert smoke_test_llm.main(["--live"]) == 1


def test_live_api_failure_returns_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smoke_test_llm.LLMConfig, "from_env", lambda: FakeConfig())
    monkeypatch.setattr(
        smoke_test_llm,
        "create_llm_client",
        lambda config: FakeClient(error=LLMRequestError("network failed")),
    )

    assert smoke_test_llm.main(["--live"]) == 1


def test_output_does_not_contain_test_api_key(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(smoke_test_llm.LLMConfig, "from_env", lambda: FakeConfig())
    monkeypatch.setattr(smoke_test_llm, "create_llm_client", lambda config: FakeClient())

    smoke_test_llm.main(["--live"])
    output = capsys.readouterr().out

    assert "sk-test-secret" not in output
