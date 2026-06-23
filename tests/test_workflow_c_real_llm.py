from __future__ import annotations

import copy

import pytest

from agent.workflow_c.real_llm import RealWorkflowLLMClient
from agent.workflow_c.state import WorkflowNodeName
from agent.workflow_c.services import WorkflowLLMResult
from llm import LLMConfig, LLMMessage, LLMRole, LLMUsage
from llm.errors import LLMJSONDecodeError, LLMRequestError
from llm.models import LLMResponse


class FakeLLMClient:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.complete_json_calls = 0
        self.messages_seen: list[list[LLMMessage]] = []

    def list_model_ids(self) -> list[str]:
        return ["fake-model"]

    def complete_text(self, messages, *, temperature=None, max_tokens=None):
        raise AssertionError("Workflow C real adapter must use complete_json")

    def complete_json(self, messages, *, temperature=None, max_tokens=None):
        self.complete_json_calls += 1
        self.messages_seen.append(messages)
        if self.error is not None:
            raise self.error
        return LLMResponse(
            content='{"ok": true}',
            parsed_json={"ok": True},
            model="fake-response-model",
            response_id="resp-1",
            finish_reason="stop",
            usage=LLMUsage(prompt_tokens=11, completion_tokens=7, total_tokens=18),
            latency_ms=23,
        )


def make_config(api_key: str = "sk-test-secret") -> LLMConfig:
    return LLMConfig(
        api_key=api_key,
        base_url="https://api.example.com",
        model="configured-model",
    )


def messages() -> list[LLMMessage]:
    return [
        LLMMessage(role=LLMRole.system, content="Return JSON."),
        LLMMessage(role=LLMRole.user, content="Return {\"ok\": true} as JSON."),
    ]


def test_success_response_maps_to_workflow_result() -> None:
    adapter = RealWorkflowLLMClient(FakeLLMClient(), make_config())

    result = adapter.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())

    assert isinstance(result, WorkflowLLMResult)
    assert result.content == '{"ok": true}'
    assert result.parsed_json == {"ok": True}
    assert result.model == "fake-response-model"
    assert result.usage.total_tokens == 18
    assert result.latency_ms == 23


def test_complete_json_is_called_once() -> None:
    fake = FakeLLMClient()
    adapter = RealWorkflowLLMClient(fake, make_config())

    adapter.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())

    assert fake.complete_json_calls == 1


def test_call_record_starts_at_sequence_one_and_records_node() -> None:
    adapter = RealWorkflowLLMClient(FakeLLMClient(), make_config())

    adapter.complete_json_for_node(WorkflowNodeName.explicit_need, messages())

    record = adapter.call_records[0]
    assert record.sequence == 1
    assert record.node_name is WorkflowNodeName.explicit_need
    assert record.status == "success"


def test_success_record_keeps_messages_and_raw_content() -> None:
    adapter = RealWorkflowLLMClient(FakeLLMClient(), make_config())

    adapter.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())

    record = adapter.call_records[0]
    assert record.messages[0] == {"role": "system", "content": "Return JSON."}
    assert record.raw_content == '{"ok": true}'
    assert record.parsed_json == {"ok": True}


def test_usage_and_models_are_recorded() -> None:
    adapter = RealWorkflowLLMClient(FakeLLMClient(), make_config())

    adapter.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())

    record = adapter.call_records[0]
    assert record.configured_model == "configured-model"
    assert record.response_model == "fake-response-model"
    assert record.usage.prompt_tokens == 11


def test_llm_request_error_is_re_raised_and_recorded() -> None:
    adapter = RealWorkflowLLMClient(
        FakeLLMClient(error=LLMRequestError("request failed")),
        make_config(),
    )

    with pytest.raises(LLMRequestError):
        adapter.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())

    record = adapter.call_records[0]
    assert record.status == "failed"
    assert record.error_type == "LLMRequestError"


def test_failure_record_safely_truncates_error_message() -> None:
    long_message = f"sk-test-secret {'x' * 1200}"
    adapter = RealWorkflowLLMClient(
        FakeLLMClient(error=LLMRequestError(long_message)),
        make_config(),
    )

    with pytest.raises(LLMRequestError):
        adapter.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())

    record = adapter.call_records[0]
    assert len(record.error_message or "") <= 1000
    assert "sk-test-secret" not in (record.error_message or "")


def test_json_decode_error_preserves_raw_content_in_record() -> None:
    adapter = RealWorkflowLLMClient(
        FakeLLMClient(
            error=LLMJSONDecodeError(
                raw_content="{bad json",
                json_error_message="Expecting property name",
                json_error_position=1,
            )
        ),
        make_config(),
    )

    with pytest.raises(LLMJSONDecodeError):
        adapter.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())

    assert adapter.call_records[0].raw_content == "{bad json"


def test_records_do_not_contain_test_api_key() -> None:
    adapter = RealWorkflowLLMClient(
        FakeLLMClient(error=LLMRequestError("sk-test-secret failed")),
        make_config(),
    )

    with pytest.raises(LLMRequestError):
        adapter.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())

    dumped = adapter.call_records[0].model_dump_json()
    assert "sk-test-secret" not in dumped


def test_messages_are_not_modified() -> None:
    fake = FakeLLMClient()
    adapter = RealWorkflowLLMClient(fake, make_config())
    original_messages = messages()
    before = copy.deepcopy(original_messages)

    adapter.complete_json_for_node(WorkflowNodeName.fact_extraction, original_messages)

    assert original_messages == before
    assert fake.messages_seen[0] is original_messages
