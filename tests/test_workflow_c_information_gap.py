from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from agent.workflow_c.executor import execute_node
from agent.workflow_c.fake_llm import (
    FakeWorkflowLLMClient,
    default_buying_intent_response,
    default_fact_response,
    default_information_gap_response,
    default_stakeholder_response,
)
from agent.workflow_c.nodes import InformationGapNode, SourceIndexingNode
from agent.workflow_c.services import WorkflowLLMResult, WorkflowServices
from agent.workflow_c.state import (
    AnalysisMode,
    ContextSufficiencyResult,
    FactExtractionResult,
    FailureCategory,
    WorkflowNodeName,
)
from dataio.runtime_cases import load_runtime_cases
from llm.models import LLMMessage, LLMUsage
from schemas.common_models import ContextQuality, SalesRole
from schemas.insight_models import BuyingIntent, Stakeholder


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def source_index():
    patch = execute_node(
        SourceIndexingNode(),
        {"validated_case": dev_01_case()},
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )
    return patch["source_index"]


def partial_context() -> ContextSufficiencyResult:
    return ContextSufficiencyResult(
        context_quality=ContextQuality.partially_sufficient,
        analysis_mode=AnalysisMode.partial_analysis,
        available_categories=["business_goal", "pain_or_problem", "stakeholders"],
        missing_categories=["budget", "timeline"],
        blocking_gaps=[],
        reasoning_summary="已有需求和参与者信息，但预算与时间线仍需确认。",
    )


def clarification_context(blocking_gaps: list[str] | None = None) -> ContextSufficiencyResult:
    return ContextSufficiencyResult(
        context_quality=ContextQuality.insufficient,
        analysis_mode=AnalysisMode.clarification_only,
        available_categories=["other"],
        missing_categories=["business_goal", "stakeholders", "budget"],
        blocking_gaps=blocking_gaps or ["business_goal", "stakeholders"],
        reasoning_summary="核心业务目标和关键参与方信息不足，需要先澄清。",
    )


def state_with_dependencies(
    *,
    context_sufficiency: ContextSufficiencyResult | None = None,
    buying_intent: BuyingIntent | None = None,
    stakeholder_map: list[Stakeholder] | None = None,
) -> dict:
    return {
        "source_index": source_index(),
        "context_sufficiency": context_sufficiency or partial_context(),
        "fact_extraction": FactExtractionResult.model_validate(default_fact_response()),
        "buying_intent": (
            buying_intent
            or BuyingIntent.model_validate(default_buying_intent_response()["buying_intent"])
        ),
        "stakeholder_map": (
            stakeholder_map
            if stakeholder_map is not None
            else [
                Stakeholder.model_validate(item)
                for item in default_stakeholder_response()["stakeholder_map"]
            ]
        ),
    }


def client_with_payload(payload: dict) -> FakeWorkflowLLMClient:
    return FakeWorkflowLLMClient(
        responses_by_node={WorkflowNodeName.information_gap: payload}
    )


def run_payload(payload: dict, state: dict | None = None):
    return execute_node(
        InformationGapNode(),
        state or state_with_dependencies(),
        WorkflowServices(llm=client_with_payload(payload)),
    )


class ContentOnlyClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def complete_json_for_node(
        self,
        node_name: WorkflowNodeName,
        messages: list[LLMMessage],
    ) -> WorkflowLLMResult:
        self.calls += 1
        return WorkflowLLMResult(
            content=json.dumps(self.payload, ensure_ascii=False),
            parsed_json=None,
            model="content-only",
            usage=LLMUsage(),
            latency_ms=1,
        )


def gap(
    *,
    gap_id: str = "GAP-X",
    category: str = "budget",
    description: str = "客户是否已有正式预算仍未确认。",
    priority: str = "medium",
    business_impact: str = "预算不清会影响方案范围判断。",
    question_to_ask: str = "本项目是否已有正式预算或预算审批计划？",
) -> dict:
    return {
        "gap_id": gap_id,
        "category": category,
        "description": description,
        "priority": priority,
        "business_impact": business_impact,
        "question_to_ask": question_to_ask,
        "recommended_owner": "sales",
    }


def test_valid_full_analysis_response_passes() -> None:
    patch = run_payload(default_information_gap_response())

    assert len(patch["information_gaps"]) == 2


def test_valid_clarification_only_response_passes() -> None:
    state = state_with_dependencies(
        context_sufficiency=clarification_context(["stakeholders"])
    )

    patch = run_payload(default_information_gap_response(), state)

    assert patch["information_gaps"][1].category.value == "authority"


def test_node_calls_llm_once() -> None:
    client = FakeWorkflowLLMClient.with_default_batch2b_responses()

    execute_node(
        InformationGapNode(),
        state_with_dependencies(),
        WorkflowServices(llm=client),
    )

    assert client.calls_for_node(WorkflowNodeName.information_gap) == 1


def test_prompt_version_is_correct() -> None:
    patch = run_payload(default_information_gap_response())

    assert patch["node_records"][0].prompt_version == "information_gap_v1"


def test_content_json_without_parsed_json_passes() -> None:
    client = ContentOnlyClient(default_information_gap_response())

    patch = execute_node(
        InformationGapNode(),
        state_with_dependencies(),
        WorkflowServices(llm=client),
    )

    assert patch["information_gaps"][0].gap_id == "GAP-01"
    assert client.calls == 1


def test_invalid_json_fails() -> None:
    client = FakeWorkflowLLMClient.with_default_batch2b_responses(
        invalid_json_nodes={"information_gap"}
    )

    patch = execute_node(
        InformationGapNode(),
        state_with_dependencies(),
        WorkflowServices(llm=client),
    )

    assert patch["failures"][0].failure_category is FailureCategory.json_parse


def test_schema_missing_field_fails() -> None:
    payload = default_information_gap_response()
    del payload["information_gaps"][0]["question_to_ask"]

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_empty_information_gaps_fail() -> None:
    patch = run_payload({"information_gaps": []})

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_duplicate_gap_id_fails() -> None:
    payload = {"information_gaps": [gap(gap_id="GAP-1"), gap(gap_id="GAP-1")]}

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_duplicate_description_fails() -> None:
    payload = {
        "information_gaps": [
            gap(gap_id="GAP-1", description="预算状态未确认"),
            gap(gap_id="GAP-2", description=" 预算状态未确认 "),
        ]
    }

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_duplicate_question_fails() -> None:
    payload = {
        "information_gaps": [
            gap(gap_id="GAP-1", question_to_ask="预算审批由谁确认？"),
            gap(gap_id="GAP-2", question_to_ask=" 预算审批由谁确认？ "),
        ]
    }

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_short_question_fails() -> None:
    patch = run_payload({"information_gaps": [gap(question_to_ask="预算？")]})

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_vague_question_fails() -> None:
    patch = run_payload({"information_gaps": [gap(question_to_ask="后续确认")]})

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_clarification_only_without_blocking_gap_coverage_fails() -> None:
    state = state_with_dependencies(
        context_sufficiency=clarification_context(["stakeholders"])
    )
    payload = {"information_gaps": [gap(category="budget")]}

    patch = run_payload(payload, state)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_clarification_only_with_blocking_gap_coverage_passes() -> None:
    state = state_with_dependencies(
        context_sufficiency=clarification_context(["stakeholders"])
    )
    payload = {"information_gaps": [gap(category="authority")]}

    patch = run_payload(payload, state)

    assert patch["information_gaps"][0].category.value == "authority"


def test_unconfirmed_decision_maker_without_authority_gap_fails() -> None:
    payload = {"information_gaps": [gap(category="budget")]}

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_unconfirmed_decision_maker_with_authority_gap_passes() -> None:
    payload = {"information_gaps": [gap(category="authority")]}

    patch = run_payload(payload)

    assert patch["information_gaps"][0].category.value == "authority"


def test_unconfirmed_budget_owner_with_decision_process_gap_passes() -> None:
    stakeholder_payload = default_stakeholder_response()["stakeholder_map"]
    stakeholder_payload[1]["sales_role"] = SalesRole.budget_owner.value
    stakeholder_map = [Stakeholder.model_validate(item) for item in stakeholder_payload]
    state = state_with_dependencies(stakeholder_map=stakeholder_map)
    payload = {"information_gaps": [gap(category="decision_process")]}

    patch = run_payload(payload, state)

    assert patch["information_gaps"][0].category.value == "decision_process"


def test_buying_intent_unknown_factors_with_empty_gap_fails() -> None:
    patch = run_payload({"information_gaps": []})

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_node_does_not_auto_generate_gap() -> None:
    patch = run_payload({"information_gaps": []})

    assert "information_gaps" not in patch


def test_node_does_not_modify_context_sufficiency() -> None:
    state = state_with_dependencies()
    before = state["context_sufficiency"].model_dump(mode="json")

    run_payload(default_information_gap_response(), state)

    assert state["context_sufficiency"].model_dump(mode="json") == before


def test_failure_does_not_write_information_gaps() -> None:
    patch = run_payload({"information_gaps": []})

    assert "information_gaps" not in patch


def test_does_not_generate_next_best_action() -> None:
    patch = run_payload(default_information_gap_response())

    assert "next_best_actions" not in patch


def test_does_not_generate_deal_score() -> None:
    patch = run_payload(default_information_gap_response())

    assert "deal_score" not in patch


def test_node_does_not_read_reference_pack() -> None:
    source = Path("agent/workflow_c/nodes/information_gap.py").read_text(encoding="utf-8")

    assert "evaluation_references" not in source
    assert "HiddenReferencePack" not in source
