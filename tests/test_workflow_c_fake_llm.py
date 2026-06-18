from __future__ import annotations

import os
import socket

import pytest

from agent.workflow_c.fake_llm import FakeWorkflowLLMClient
from agent.workflow_c.state import WorkflowNodeName
from llm.errors import LLMRequestError
from llm.models import LLMMessage, LLMRole


def messages() -> list[LLMMessage]:
    return [LLMMessage(role=LLMRole.user, content="Return JSON")]


def test_default_fact_response_succeeds() -> None:
    client = FakeWorkflowLLMClient.with_default_fact_response()

    result = client.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())

    assert result.parsed_json["facts"]


def test_initial_total_calls_is_zero() -> None:
    client = FakeWorkflowLLMClient.with_default_fact_response()

    assert client.total_calls == 0


def test_records_total_call_count() -> None:
    client = FakeWorkflowLLMClient.with_default_fact_response()
    client.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())

    assert client.call_count == 1
    assert client.total_calls == 1


def test_two_calls_increment_total_calls_to_two() -> None:
    client = FakeWorkflowLLMClient.with_default_fact_response()
    client.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())
    client.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())

    assert client.total_calls == 2


def test_records_call_count_by_node() -> None:
    client = FakeWorkflowLLMClient.with_default_fact_response()
    client.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())

    assert client.calls_by_node[WorkflowNodeName.fact_extraction] == 1
    assert client.calls_for_node(WorkflowNodeName.fact_extraction) == 1
    assert client.calls_for_node("fact_extraction") == 1


def test_request_error_can_be_simulated() -> None:
    client = FakeWorkflowLLMClient.with_default_fact_response()
    client.request_error_nodes.add(WorkflowNodeName.fact_extraction)

    with pytest.raises(LLMRequestError):
        client.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())

    assert client.total_calls == 1


def test_factory_accepts_request_error_nodes() -> None:
    client = FakeWorkflowLLMClient.with_default_fact_response(
        request_error_nodes={"fact_extraction"}
    )

    with pytest.raises(LLMRequestError):
        client.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())


def test_invalid_json_can_be_simulated() -> None:
    client = FakeWorkflowLLMClient.with_default_fact_response()
    client.invalid_json_nodes.add(WorkflowNodeName.fact_extraction)

    result = client.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())

    assert result.parsed_json is None
    assert result.content == "{not valid json"
    assert client.total_calls == 1


def test_factory_accepts_invalid_json_nodes() -> None:
    client = FakeWorkflowLLMClient.with_default_fact_response(
        invalid_json_nodes={"fact_extraction"}
    )

    result = client.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())

    assert result.parsed_json is None


def test_schema_error_payload_can_be_simulated() -> None:
    client = FakeWorkflowLLMClient.with_default_fact_response()
    client.schema_error_payloads[WorkflowNodeName.fact_extraction] = {"facts": []}

    result = client.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())

    assert result.parsed_json == {"facts": []}


def test_factory_accepts_string_node_names() -> None:
    client = FakeWorkflowLLMClient.with_default_fact_response(
        invalid_json_nodes={"fact_extraction"}
    )

    client.complete_json_for_node("fact_extraction", messages())

    assert client.calls_for_node("fact_extraction") == 1


def test_mutually_exclusive_failure_modes_fail() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        FakeWorkflowLLMClient.with_default_fact_response(
            request_error_nodes={"fact_extraction"},
            invalid_json_nodes={"fact_extraction"},
        )


def test_total_calls_is_read_only() -> None:
    client = FakeWorkflowLLMClient.with_default_fact_response()

    with pytest.raises(AttributeError):
        client.total_calls = 10


def test_fake_llm_does_not_read_env(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_getenv(name, default=None):
        raise AssertionError("env should not be read")

    monkeypatch.setattr(os, "getenv", fail_getenv)
    client = FakeWorkflowLLMClient.with_default_fact_response()

    assert client.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())


def test_fake_llm_does_not_access_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_socket(*args, **kwargs):
        raise AssertionError("network should not be used")

    monkeypatch.setattr(socket, "socket", fail_socket)
    client = FakeWorkflowLLMClient.with_default_fact_response()

    assert client.complete_json_for_node(WorkflowNodeName.fact_extraction, messages())


def test_fake_response_does_not_contain_hard_failure_traps() -> None:
    result = FakeWorkflowLLMClient.with_default_fact_response().complete_json_for_node(
        WorkflowNodeName.fact_extraction, messages()
    )

    assert "hard_failure_traps" not in result.content


def test_fake_response_does_not_contain_solution_blacklist() -> None:
    result = FakeWorkflowLLMClient.with_default_fact_response().complete_json_for_node(
        WorkflowNodeName.fact_extraction, messages()
    )

    assert "solution_blacklist" not in result.content
