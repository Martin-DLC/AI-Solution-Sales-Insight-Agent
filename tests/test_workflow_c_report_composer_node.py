from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent.workflow_c import (
    FakeWorkflowLLMClient,
    WorkflowServices,
    build_analysis_id,
    create_initial_state,
    run_architecture_c_skeleton,
)
from agent.workflow_c.executor import execute_node
from agent.workflow_c.nodes.report_composer import ReportComposerNode
from agent.workflow_c.state import FailureCategory, WorkflowNodeName, WorkflowStatus
from dataio.runtime_cases import load_runtime_cases
from schemas.output_models import SalesInsightReport


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def complete_state() -> dict:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )
    return dict(snapshot)


def test_report_composer_node_runs_without_llm_calls() -> None:
    state = complete_state()
    client = FakeWorkflowLLMClient.with_default_batch4b_responses()

    patch = execute_node(ReportComposerNode(), state, WorkflowServices(llm=client))

    assert client.total_calls == 0
    assert isinstance(patch["report_draft"], SalesInsightReport)
    assert patch["current_node"] is WorkflowNodeName.report_composer


def test_contract_prompt_version_and_output_fields() -> None:
    contract = ReportComposerNode.contract

    assert contract.prompt_version is None
    assert contract.produced_state_fields == ("report_draft",)
    assert contract.output_model.__name__ == "ReportComposerNodeOutput"
    assert "risk_traces" not in contract.required_state_fields
    assert "action_traces" not in contract.required_state_fields


def test_solution_recommendations_missing_still_composes() -> None:
    state = complete_state()
    state.pop("solution_recommendations", None)

    patch = execute_node(
        ReportComposerNode(),
        state,
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert patch["report_draft"].solution_recommendations == []


def test_missing_dependency_failure_has_no_report_draft() -> None:
    patch = execute_node(
        ReportComposerNode(),
        create_initial_state(dev_01_case()),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert patch["workflow_status"] is WorkflowStatus.awaiting_human_review
    assert patch["failures"][0].failure_category is FailureCategory.missing_dependency
    assert "report_draft" not in patch


def test_schema_failure_does_not_write_report_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.workflow_c.nodes import report_composer as module

    monkeypatch.setattr(module, "compose_sales_insight_report", lambda **kwargs: None)
    patch = execute_node(
        ReportComposerNode(),
        complete_state(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert patch["workflow_status"] is WorkflowStatus.awaiting_human_review
    assert patch["failures"][0].failure_category is FailureCategory.schema_validation
    assert "report_draft" not in patch


def test_node_does_not_generate_final_report_or_modify_upstream_state() -> None:
    state = complete_state()
    before = {
        key: value.model_dump(mode="json") if hasattr(value, "model_dump") else value
        for key, value in state.items()
    }

    patch = execute_node(
        ReportComposerNode(),
        state,
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert "final_report" not in patch
    assert "final_report" not in state
    after = {
        key: value.model_dump(mode="json") if hasattr(value, "model_dump") else value
        for key, value in state.items()
    }
    assert after == before


def test_utc_now_called_once_and_analysis_id_uses_run_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.workflow_c.nodes import report_composer as module

    state = complete_state()
    calls = []
    fixed = datetime(2026, 6, 23, 12, 30, tzinfo=UTC)

    def fake_utc_now():
        calls.append("called")
        return fixed

    monkeypatch.setattr(module, "utc_now", fake_utc_now)
    patch = execute_node(
        ReportComposerNode(),
        state,
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert calls == ["called"]
    assert patch["report_draft"].generated_at == fixed
    assert patch["report_draft"].analysis_id == build_analysis_id(
        run_id=state["run_id"],
        case_id=state["validated_case"].case_id,
    )
