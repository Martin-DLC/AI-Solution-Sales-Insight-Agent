from __future__ import annotations

import json

from agent.workflow_c.executor import execute_node
from agent.workflow_c.fake_llm import (
    FakeWorkflowLLMClient,
    default_ai_opportunity_response,
    default_business_impact_response,
    default_explicit_need_response,
    default_fact_response,
    default_information_gap_response,
    default_underlying_pain_response,
)
from agent.workflow_c.nodes import AIOpportunityNode, SourceIndexingNode
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
from schemas.common_models import ClaimType, ContextQuality, EvidenceSourceType
from schemas.insight_models import BusinessImpact, ExplicitNeed, InformationGap, UnderlyingPain


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def partial_context() -> ContextSufficiencyResult:
    return ContextSufficiencyResult(
        context_quality=ContextQuality.partially_sufficient,
        analysis_mode=AnalysisMode.partial_analysis,
        available_categories=["business_goal", "pain_or_problem"],
        missing_categories=["budget"],
        blocking_gaps=[],
        reasoning_summary="已有业务问题和需求，但预算与数据细节仍需要确认。",
    )


def insufficient_context() -> ContextSufficiencyResult:
    return ContextSufficiencyResult(
        context_quality=ContextQuality.insufficient,
        analysis_mode=AnalysisMode.clarification_only,
        available_categories=["other"],
        missing_categories=["business_goal"],
        blocking_gaps=["business_goal"],
        reasoning_summary="核心业务目标不足，需要先澄清再分析。",
    )


def state_with_dependencies(context: ContextSufficiencyResult | None = None) -> dict:
    source_patch = execute_node(
        SourceIndexingNode(),
        {"validated_case": dev_01_case()},
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )
    return {
        "validated_case": dev_01_case(),
        "source_index": source_patch["source_index"],
        "context_sufficiency": context or partial_context(),
        "fact_extraction": FactExtractionResult.model_validate(default_fact_response()),
        "explicit_needs": [
            ExplicitNeed.model_validate(item)
            for item in default_explicit_need_response()["explicit_needs"]
        ],
        "underlying_pains": [
            UnderlyingPain.model_validate(item)
            for item in default_underlying_pain_response()["underlying_pains"]
        ],
        "business_impacts": [
            BusinessImpact.model_validate(item)
            for item in default_business_impact_response()["business_impacts"]
        ],
        "information_gaps": [
            InformationGap.model_validate(item)
            for item in default_information_gap_response()["information_gaps"]
        ],
    }


def client_with_payload(payload: dict) -> FakeWorkflowLLMClient:
    return FakeWorkflowLLMClient(
        responses_by_node={WorkflowNodeName.ai_opportunity: payload}
    )


def run_payload(payload: dict, state: dict | None = None):
    return execute_node(
        AIOpportunityNode(),
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


def test_valid_response_passes() -> None:
    patch = run_payload(default_ai_opportunity_response())

    assert patch["ai_opportunities"][0].opportunity_id == "OPP-01"


def test_node_calls_llm_once() -> None:
    client = FakeWorkflowLLMClient.with_default_batch3a_responses()

    execute_node(AIOpportunityNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert client.calls_for_node(WorkflowNodeName.ai_opportunity) == 1


def test_prompt_version_is_correct() -> None:
    patch = run_payload(default_ai_opportunity_response())

    assert patch["node_records"][0].prompt_version == "ai_opportunity_v1"


def test_content_json_without_parsed_json_passes() -> None:
    client = ContentOnlyClient(default_ai_opportunity_response())

    patch = execute_node(
        AIOpportunityNode(),
        state_with_dependencies(),
        WorkflowServices(llm=client),
    )

    assert patch["ai_opportunities"][0].opportunity_id == "OPP-01"
    assert client.calls == 1


def test_invalid_json_fails() -> None:
    client = FakeWorkflowLLMClient.with_default_batch3a_responses(
        invalid_json_nodes={"ai_opportunity"}
    )

    patch = execute_node(AIOpportunityNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert patch["failures"][0].failure_category is FailureCategory.json_parse


def test_schema_missing_field_fails() -> None:
    payload = default_ai_opportunity_response()
    del payload["ai_opportunities"][0]["name"]

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_related_pain_id_not_found_fails() -> None:
    payload = default_ai_opportunity_response()
    payload["ai_opportunities"][0]["related_pain_ids"] = ["PAIN-NOPE"]

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_claim_type_fact_fails() -> None:
    payload = default_ai_opportunity_response()
    payload["ai_opportunities"][0]["claim_type"] = ClaimType.fact.value

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_claim_type_unknown_fails() -> None:
    payload = default_ai_opportunity_response()
    payload["ai_opportunities"][0]["claim_type"] = ClaimType.unknown.value

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_no_evidence_fails() -> None:
    payload = default_ai_opportunity_response()
    payload["ai_opportunities"][0]["evidence"] = []

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_source_id_not_found_fails() -> None:
    payload = default_ai_opportunity_response()
    payload["ai_opportunities"][0]["evidence"][0]["source_id"] = "BAD-01"

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_source_type_mismatch_fails() -> None:
    payload = default_ai_opportunity_response()
    payload["ai_opportunities"][0]["evidence"][0]["source_type"] = (
        EvidenceSourceType.customer_profile.value
    )

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_solution_library_evidence_fails() -> None:
    payload = default_ai_opportunity_response()
    payload["ai_opportunities"][0]["evidence"] = [
        {
            "source_id": "SOLUTION-01",
            "source_type": EvidenceSourceType.solution_library.value,
            "evidence_summary": "方案库不能作为AI机会依据。",
        }
    ]

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_reference_case_evidence_fails() -> None:
    payload = default_ai_opportunity_response()
    payload["ai_opportunities"][0]["evidence"][0]["source_type"] = (
        EvidenceSourceType.reference_case.value
    )

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_unverified_salesperson_note_alone_fails() -> None:
    payload = default_ai_opportunity_response()
    payload["ai_opportunities"][0]["evidence"] = [
        {
            "source_id": "NOTE-01",
            "source_type": EvidenceSourceType.salesperson_note.value,
            "evidence_summary": "销售备注不能单独支持AI机会。",
        }
    ]

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_meeting_evidence_passes() -> None:
    patch = run_payload(default_ai_opportunity_response())

    assert patch["ai_opportunities"][0].evidence[0].source_id == "MTG-01"


def test_known_constraint_evidence_passes() -> None:
    payload = default_ai_opportunity_response()
    payload["ai_opportunities"][0]["evidence"] = [
        {
            "source_id": "CONSTRAINT-01",
            "source_type": EvidenceSourceType.known_constraint.value,
            "evidence_summary": "客户约束可作为AI机会的验证来源。",
        }
    ]

    patch = run_payload(payload)

    assert patch["ai_opportunities"][0].evidence[0].source_id == "CONSTRAINT-01"


def test_partially_sufficient_suitable_now_fails() -> None:
    payload = default_ai_opportunity_response()
    payload["ai_opportunities"][0]["suitability"] = "suitable_now"

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_partially_sufficient_suitable_for_poc_passes() -> None:
    patch = run_payload(default_ai_opportunity_response())

    assert patch["ai_opportunities"][0].suitability.value == "suitable_for_poc"


def test_insufficient_context_direct_call_fails() -> None:
    patch = run_payload(default_ai_opportunity_response(), state_with_dependencies(insufficient_context()))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_duplicate_opportunity_id_fails() -> None:
    payload = default_ai_opportunity_response()
    clone = payload["ai_opportunities"][0].copy()
    clone["name"] = "另一个机会名称"
    payload["ai_opportunities"].append(clone)

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_failure_does_not_write_ai_opportunities() -> None:
    payload = default_ai_opportunity_response()
    payload["ai_opportunities"][0]["evidence"] = []

    patch = run_payload(payload)

    assert "ai_opportunities" not in patch


def test_does_not_generate_solution_recommendation() -> None:
    patch = run_payload(default_ai_opportunity_response())

    assert "solution_recommendations" not in patch
