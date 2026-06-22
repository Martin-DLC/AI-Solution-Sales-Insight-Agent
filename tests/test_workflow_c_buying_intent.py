from __future__ import annotations

import json

from agent.workflow_c.executor import execute_node
from agent.workflow_c.fake_llm import (
    FakeWorkflowLLMClient,
    default_business_impact_response,
    default_buying_intent_response,
    default_explicit_need_response,
    default_fact_response,
    default_underlying_pain_response,
)
from agent.workflow_c.nodes import BuyingIntentNode, SourceIndexingNode
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
from schemas.common_models import ClaimType, ConfidenceLevel, ContextQuality, IntentLevel, SalesStage
from schemas.insight_models import BusinessImpact, ExplicitNeed, UnderlyingPain


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def context(quality: ContextQuality = ContextQuality.partially_sufficient) -> ContextSufficiencyResult:
    mode = {
        ContextQuality.sufficient: AnalysisMode.full_analysis,
        ContextQuality.partially_sufficient: AnalysisMode.partial_analysis,
        ContextQuality.insufficient: AnalysisMode.clarification_only,
    }[quality]
    return ContextSufficiencyResult(
        context_quality=quality,
        analysis_mode=mode,
        available_categories=["business_goal"],
        missing_categories=["budget"],
        blocking_gaps=[],
        reasoning_summary="Context is sufficient enough for this node test.",
    )


def state_with_dependencies(quality: ContextQuality = ContextQuality.partially_sufficient):
    case = dev_01_case()
    source_patch = execute_node(
        SourceIndexingNode(),
        {"validated_case": case},
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )
    return {
        "validated_case": case,
        "source_index": source_patch["source_index"],
        "context_sufficiency": context(quality),
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
    }


def client_with_payload(payload: dict) -> FakeWorkflowLLMClient:
    return FakeWorkflowLLMClient(responses_by_node={WorkflowNodeName.buying_intent: payload})


def run_payload(payload: dict, quality: ContextQuality = ContextQuality.partially_sufficient):
    return execute_node(
        BuyingIntentNode(),
        state_with_dependencies(quality),
        WorkflowServices(llm=client_with_payload(payload)),
    )


class ContentOnlyClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def complete_json_for_node(self, node_name: WorkflowNodeName, messages: list[LLMMessage]) -> WorkflowLLMResult:
        self.calls += 1
        return WorkflowLLMResult(
            content=json.dumps(self.payload, ensure_ascii=False),
            parsed_json=None,
            model="content-only",
            usage=LLMUsage(),
            latency_ms=1,
        )


def test_valid_response_passes() -> None:
    patch = run_payload(default_buying_intent_response())

    assert patch["buying_intent"].intent_level is IntentLevel.medium_high


def test_node_calls_llm_once() -> None:
    client = FakeWorkflowLLMClient.with_default_batch2a_responses()

    execute_node(BuyingIntentNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert client.calls_for_node(WorkflowNodeName.buying_intent) == 1


def test_prompt_version_is_correct() -> None:
    patch = run_payload(default_buying_intent_response())

    assert patch["node_records"][0].prompt_version == "buying_intent_v1"


def test_content_json_without_parsed_json_passes() -> None:
    client = ContentOnlyClient(default_buying_intent_response())

    patch = execute_node(BuyingIntentNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert patch["buying_intent"].sales_stage is SalesStage.discovery
    assert client.calls == 1


def test_invalid_json_fails() -> None:
    client = FakeWorkflowLLMClient.with_default_batch2a_responses(invalid_json_nodes={"buying_intent"})

    patch = execute_node(BuyingIntentNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert patch["failures"][0].failure_category is FailureCategory.json_parse


def test_schema_missing_field_fails() -> None:
    payload = default_buying_intent_response()
    del payload["buying_intent"]["reasoning_summary"]

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_without_any_signal_fails() -> None:
    payload = default_buying_intent_response()
    payload["buying_intent"]["positive_signals"] = []
    payload["buying_intent"]["negative_signals"] = []
    payload["buying_intent"]["unknown_factors"] = []

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_medium_high_without_positive_signal_fails() -> None:
    payload = default_buying_intent_response()
    payload["buying_intent"]["positive_signals"] = []

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_partially_sufficient_high_fails() -> None:
    payload = default_buying_intent_response()
    payload["buying_intent"]["intent_level"] = IntentLevel.high.value

    patch = run_payload(payload, ContextQuality.partially_sufficient)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_insufficient_direct_call_fails() -> None:
    patch = run_payload(default_buying_intent_response(), ContextQuality.insufficient)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_high_intent_only_sales_note_fails() -> None:
    payload = default_buying_intent_response()
    payload["buying_intent"]["positive_signals"] = ["NOTE-01 销售备注认为客户很积极"]
    payload["buying_intent"]["reasoning_summary"] = "NOTE-01 是唯一支持中高意向的来源。"

    patch = run_payload(payload, ContextQuality.sufficient)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_solution_library_reference_fails() -> None:
    payload = default_buying_intent_response()
    payload["buying_intent"]["positive_signals"] = ["SOLUTION-01 表明客户适配方案"]

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_reference_case_reference_fails() -> None:
    payload = default_buying_intent_response()
    payload["buying_intent"]["reasoning_summary"] = "REFERENCE-01 支撑该购买意向判断。"

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_meeting_based_signal_passes() -> None:
    payload = default_buying_intent_response()
    payload["buying_intent"]["positive_signals"] = ["MTG-01 客户明确表达业务需求"]

    patch = run_payload(payload)

    assert patch["buying_intent"].positive_signals == ["MTG-01 客户明确表达业务需求"]


def test_node_does_not_auto_add_unknown_factors() -> None:
    payload = default_buying_intent_response()
    payload["buying_intent"]["intent_level"] = IntentLevel.medium.value
    payload["buying_intent"]["unknown_factors"] = []

    patch = run_payload(payload)

    assert patch["buying_intent"].unknown_factors == []


def test_node_does_not_modify_intent_level() -> None:
    payload = default_buying_intent_response()
    payload["buying_intent"]["intent_level"] = IntentLevel.low.value

    patch = run_payload(payload)

    assert patch["buying_intent"].intent_level is IntentLevel.low


def test_failure_does_not_write_buying_intent() -> None:
    payload = default_buying_intent_response()
    payload["buying_intent"]["positive_signals"] = []

    patch = run_payload(payload)

    assert "buying_intent" not in patch


def test_does_not_generate_deal_score() -> None:
    patch = run_payload(default_buying_intent_response())

    assert "deal_score" not in patch
