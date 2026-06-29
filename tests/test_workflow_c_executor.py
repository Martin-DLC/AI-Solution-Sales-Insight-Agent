from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel

import agent.workflow_c.executor as executor_module
from agent.workflow_c.contracts import NodeContract, NodeFailurePolicy
from agent.workflow_c.executor import execute_node
from agent.workflow_c.services import WorkflowServices
from agent.workflow_c.state import FailureCategory, WorkflowNodeName, WorkflowStatus
from agent.workflow_c.fake_llm import FakeWorkflowLLMClient
from schemas.common_models import StrictBaseModel


class DummyOutput(StrictBaseModel):
    value: str


class DummyNode:
    def __init__(
        self,
        *,
        required=("input",),
        produced=("value",),
        output_model: type[BaseModel] = DummyOutput,
        policy=NodeFailurePolicy.require_human_review,
        patch: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.contract = NodeContract(
            name=WorkflowNodeName.explicit_need,
            required_state_fields=required,
            produced_state_fields=produced,
            output_model=output_model,
            failure_policy=policy,
        )
        self.patch = patch if patch is not None else {"value": "ok"}
        self.error = error

    def run(self, state, services):
        if self.error:
            raise self.error
        return self.patch


def services() -> WorkflowServices:
    return WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response())


class FrozenClock:
    def __init__(self, values: list[datetime]) -> None:
        self._values = iter(values)

    def now(self, tz: object | None = None) -> datetime:
        return next(self._values)


def test_success_node_returns_business_patch() -> None:
    patch = execute_node(DummyNode(), {"input": "x"}, services())

    assert patch["value"] == "ok"


def test_success_records_node_execution() -> None:
    patch = execute_node(DummyNode(), {"input": "x"}, services())

    assert patch["node_records"][0].status.value == "succeeded"


def test_missing_dependency_generates_failure() -> None:
    patch = execute_node(DummyNode(), {}, services())

    assert patch["failures"][0].failure_category is FailureCategory.missing_dependency


def test_input_validation_failure_sets_workflow_failed() -> None:
    node = DummyNode(
        required=("case_input",),
        produced=("validated_case",),
        policy=NodeFailurePolicy.fail_workflow,
        patch={"validated_case": {"case_id": "bad"}},
    )
    node.contract = NodeContract(
        name=WorkflowNodeName.input_validation,
        required_state_fields=("case_input",),
        produced_state_fields=("validated_case",),
        output_model=DummyOutput,
        failure_policy=NodeFailurePolicy.fail_workflow,
    )

    patch = execute_node(node, {}, services())

    assert patch["workflow_status"] is WorkflowStatus.failed


def test_regular_node_failure_awaits_human_review() -> None:
    patch = execute_node(DummyNode(error=RuntimeError("boom")), {"input": "x"}, services())

    assert patch["workflow_status"] is WorkflowStatus.awaiting_human_review


def test_extra_returned_field_fails() -> None:
    patch = execute_node(DummyNode(patch={"value": "ok", "extra": "bad"}), {"input": "x"}, services())

    assert patch["failures"][0].failure_category is FailureCategory.internal_error


def test_missing_returned_field_fails() -> None:
    patch = execute_node(DummyNode(patch={}), {"input": "x"}, services())

    assert patch["failures"][0].failure_category is FailureCategory.internal_error


def test_pydantic_failure_generates_schema_validation() -> None:
    patch = execute_node(DummyNode(patch={"value": ""}), {"input": "x"}, services())

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_failure_does_not_write_business_output() -> None:
    patch = execute_node(DummyNode(patch={"value": ""}), {"input": "x"}, services())

    assert "value" not in patch


def test_exception_message_redacts_api_key() -> None:
    patch = execute_node(
        DummyNode(error=RuntimeError("sk-test-secret failed")),
        {"input": "x"},
        services(),
    )

    assert "sk-test-secret" not in patch["failures"][0].message


def test_executor_does_not_mutate_state() -> None:
    state = {"input": "x"}
    execute_node(DummyNode(), state, services())

    assert state == {"input": "x"}


def test_latency_is_non_negative() -> None:
    patch = execute_node(DummyNode(), {"input": "x"}, services())

    assert patch["node_records"][0].latency_ms >= 0


def test_success_path_node_record_normalizes_backwards_wall_clock(monkeypatch) -> None:
    started_at = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)
    clock = FrozenClock([started_at, started_at - timedelta(seconds=2)])
    perf_counter_values = iter([100.0, 100.004])
    monkeypatch.setattr(executor_module, "datetime", clock)
    monkeypatch.setattr(
        executor_module.time,
        "perf_counter",
        lambda: next(perf_counter_values),
    )

    patch = execute_node(DummyNode(), {"input": "x"}, services())
    record = patch["node_records"][0]

    assert record.started_at == started_at
    assert record.completed_at >= record.started_at
    assert record.latency_ms >= 0
    assert record.completed_at == started_at + timedelta(milliseconds=4)


def test_failure_path_node_record_normalizes_backwards_wall_clock(monkeypatch) -> None:
    started_at = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)
    clock = FrozenClock([started_at, started_at - timedelta(seconds=3)])
    perf_counter_values = iter([200.0, 200.006])
    monkeypatch.setattr(executor_module, "datetime", clock)
    monkeypatch.setattr(
        executor_module.time,
        "perf_counter",
        lambda: next(perf_counter_values),
    )

    patch = execute_node(DummyNode(error=RuntimeError("boom")), {"input": "x"}, services())
    record = patch["node_records"][0]

    assert patch["failures"][0].occurred_at == record.completed_at
    assert record.started_at == started_at
    assert record.completed_at >= record.started_at
    assert record.latency_ms >= 0
    assert record.completed_at == started_at + timedelta(milliseconds=6)
