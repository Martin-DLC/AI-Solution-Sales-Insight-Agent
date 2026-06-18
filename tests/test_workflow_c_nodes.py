from __future__ import annotations

import pytest

from agent.workflow_c.executor import execute_node
from agent.workflow_c.fake_llm import FakeWorkflowLLMClient
from agent.workflow_c.nodes import (
    ContextSufficiencyNode,
    FakeFactExtractionNode,
    HumanReviewGateNode,
    InputValidationNode,
    SourceIndexingNode,
)
from agent.workflow_c.services import WorkflowServices
from agent.workflow_c.state import AnalysisMode, WorkflowStatus
from dataio.runtime_cases import load_runtime_cases
from schemas.common_models import EvidenceSourceType


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def services(client: FakeWorkflowLLMClient | None = None) -> WorkflowServices:
    return WorkflowServices(llm=client or FakeWorkflowLLMClient.with_default_fact_response())


def validated_state():
    case = dev_01_case()
    return {"case_input": case, "validated_case": case}


def fact_state(categories: list[str]):
    patch = execute_node(SourceIndexingNode(), validated_state(), services())
    client = FakeWorkflowLLMClient.with_default_fact_response()
    payload = client.responses_by_node[next(iter(client.responses_by_node))].copy()
    for fact, category in zip(payload["facts"], categories):
        fact["category"] = category
    client.responses_by_node[next(iter(client.responses_by_node))] = payload
    fact_patch = execute_node(
        FakeFactExtractionNode(),
        {**validated_state(), "source_index": patch["source_index"]},
        services(client),
    )
    return {**validated_state(), "source_index": patch["source_index"], **fact_patch}


def test_input_validation_loads_valid_dev_01_case() -> None:
    patch = execute_node(InputValidationNode(), {"case_input": dev_01_case()}, services())

    assert patch["validated_case"].case_id == "DEV-01"


def test_invalid_case_id_fails() -> None:
    bad = dev_01_case().model_dump(mode="json")
    bad["case_id"] = "DEV-1"

    patch = execute_node(InputValidationNode(), {"case_input": bad}, services())

    assert patch["workflow_status"] is WorkflowStatus.failed


def test_source_index_order_is_correct() -> None:
    patch = execute_node(SourceIndexingNode(), validated_state(), services())

    assert [item.source_id for item in patch["source_index"].items[:2]] == ["PROFILE-01", "MTG-01"]


def test_salesperson_note_verified_stays_false() -> None:
    patch = execute_node(SourceIndexingNode(), validated_state(), services())

    note = next(item for item in patch["source_index"].items if item.source_id == "NOTE-01")
    assert note.verified is False


def test_solution_source_type_is_solution_library() -> None:
    patch = execute_node(SourceIndexingNode(), validated_state(), services())

    solution = next(item for item in patch["source_index"].items if item.source_id == "SOLUTION-01")
    assert solution.source_type is EvidenceSourceType.solution_library


def test_same_input_indexes_identically() -> None:
    first = execute_node(SourceIndexingNode(), validated_state(), services())
    second = execute_node(SourceIndexingNode(), validated_state(), services())

    assert first["source_index"].model_dump(mode="json") == second["source_index"].model_dump(mode="json")


def test_fake_fact_node_calls_llm_once() -> None:
    source = execute_node(SourceIndexingNode(), validated_state(), services())
    client = FakeWorkflowLLMClient.with_default_fact_response()

    execute_node(FakeFactExtractionNode(), {**validated_state(), "source_index": source["source_index"]}, services(client))

    assert client.call_count == 1


def test_fake_fact_node_does_not_auto_fill_schema_errors() -> None:
    source = execute_node(SourceIndexingNode(), validated_state(), services())
    client = FakeWorkflowLLMClient.with_default_fact_response()
    client.schema_error_payloads[FakeFactExtractionNode().contract.name] = {"facts": []}

    patch = execute_node(FakeFactExtractionNode(), {**validated_state(), "source_index": source["source_index"]}, services(client))

    assert "fact_extraction" not in patch


def test_context_sufficient_returns_full_analysis() -> None:
    state = fact_state(["business_goal", "pain_or_problem", "stakeholders"])

    patch = execute_node(ContextSufficiencyNode(), state, services())

    assert patch["context_sufficiency"].analysis_mode is AnalysisMode.full_analysis


def test_context_partial_returns_partial_analysis() -> None:
    state = fact_state(["business_goal", "pain_or_problem", "other"])
    case = dev_01_case().model_copy(deep=True)
    case.customer_profile.publicly_stated_goals = []
    case.customer_profile.current_systems = []
    case.known_constraints = []
    case.meeting.participants = []
    state["validated_case"] = case

    patch = execute_node(ContextSufficiencyNode(), state, services())

    assert patch["context_sufficiency"].analysis_mode is AnalysisMode.partial_analysis


def test_context_insufficient_returns_clarification_only() -> None:
    case = dev_01_case().model_copy(deep=True)
    case.customer_profile.publicly_stated_goals = []
    case.customer_profile.current_systems = []
    case.known_constraints = []
    case.meeting.participants = []
    payload_state = fact_state(["other"])
    payload_state["validated_case"] = case
    payload_state["fact_extraction"].facts[0].category = "other"
    payload_state["fact_extraction"].facts = [payload_state["fact_extraction"].facts[0]]

    patch = execute_node(ContextSufficiencyNode(), payload_state, services())

    assert patch["context_sufficiency"].analysis_mode is AnalysisMode.clarification_only


def test_human_review_gate_defaults_pending() -> None:
    patch = execute_node(HumanReviewGateNode(), {"case_input": dev_01_case()}, services())

    assert patch["human_review_decision"].status.value == "pending"


def test_human_review_gate_blocks_external_actions() -> None:
    patch = execute_node(HumanReviewGateNode(), {"case_input": dev_01_case()}, services())

    assert "发送客户邮件" in patch["human_review_decision"].blocked_actions
