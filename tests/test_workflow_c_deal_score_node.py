from __future__ import annotations

from agent.workflow_c.executor import execute_node
from agent.workflow_c.fake_llm import (
    FakeWorkflowLLMClient,
    default_ai_opportunity_response,
    default_business_impact_response,
    default_buying_intent_response,
    default_explicit_need_response,
    default_fact_response,
    default_information_gap_response,
    default_solution_recommendation_response,
    default_stakeholder_response,
    default_underlying_pain_response,
)
from agent.workflow_c.nodes import DealScoreNode, SourceIndexingNode
from agent.workflow_c.services import WorkflowServices
from agent.workflow_c.solution_retrieval import retrieve_solution_candidates
from agent.workflow_c.state import ContextSufficiencyResult, FailureCategory, FactExtractionResult, WorkflowNodeName
from dataio.runtime_cases import load_runtime_cases
from schemas.insight_models import (
    BusinessImpact,
    BuyingIntent,
    ExplicitNeed,
    InformationGap,
    Stakeholder,
    UnderlyingPain,
)
from schemas.solution_models import AIOpportunity, SolutionRecommendation


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def source_index():
    return execute_node(
        SourceIndexingNode(),
        {"validated_case": dev_01_case()},
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )["source_index"]


def state(solution_recommendations: list[SolutionRecommendation] | None = None) -> dict:
    index = source_index()
    explicit_needs = [
        ExplicitNeed.model_validate(item)
        for item in default_explicit_need_response()["explicit_needs"]
    ]
    underlying_pains = [
        UnderlyingPain.model_validate(item)
        for item in default_underlying_pain_response()["underlying_pains"]
    ]
    business_impacts = [
        BusinessImpact.model_validate(item)
        for item in default_business_impact_response()["business_impacts"]
    ]
    ai_opportunities = [
        AIOpportunity.model_validate(item)
        for item in default_ai_opportunity_response()["ai_opportunities"]
    ]
    return {
        "source_index": index,
        "context_sufficiency": ContextSufficiencyResult(
            context_quality="partially_sufficient",
            analysis_mode="partial_analysis",
            available_categories=["business_goal"],
            missing_categories=["budget"],
            blocking_gaps=[],
            reasoning_summary="当前材料足够进行受限分析，但仍有关键缺口。",
        ),
        "fact_extraction": FactExtractionResult.model_validate(default_fact_response()),
        "explicit_needs": explicit_needs,
        "underlying_pains": underlying_pains,
        "business_impacts": business_impacts,
        "buying_intent": BuyingIntent.model_validate(default_buying_intent_response()["buying_intent"]),
        "stakeholder_map": [
            Stakeholder.model_validate(item)
            for item in default_stakeholder_response()["stakeholder_map"]
        ],
        "information_gaps": [
            InformationGap.model_validate(item)
            for item in default_information_gap_response()["information_gaps"]
        ],
        "ai_opportunities": ai_opportunities,
        "retrieved_solutions": retrieve_solution_candidates(
            case=dev_01_case(),
            source_index=index,
            ai_opportunities=ai_opportunities,
            underlying_pains=underlying_pains,
            business_impacts=business_impacts,
        ),
        "solution_recommendations": solution_recommendations
        if solution_recommendations is not None
        else [
            SolutionRecommendation.model_validate(item)
            for item in default_solution_recommendation_response()["solution_recommendations"]
        ],
    }


def test_deal_score_node_executes_successfully() -> None:
    patch = execute_node(
        DealScoreNode(),
        state(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3b_responses()),
    )

    assert patch["deal_score"].dimensions


def test_deal_score_node_does_not_call_llm() -> None:
    client = FakeWorkflowLLMClient.with_default_batch3b_responses()

    execute_node(DealScoreNode(), state(), WorkflowServices(llm=client))

    assert client.total_calls == 0


def test_deal_score_node_prompt_version_is_none() -> None:
    patch = execute_node(
        DealScoreNode(),
        state(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3b_responses()),
    )

    assert patch["node_records"][0].prompt_version is None


def test_deal_score_node_outputs_declared_field_only() -> None:
    patch = execute_node(
        DealScoreNode(),
        state(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3b_responses()),
    )

    assert "deal_score" in patch
    assert "risks_and_objections" not in patch
    assert "next_best_actions" not in patch
    assert "final_report" not in patch


def test_deal_score_node_calculates_without_recommendations() -> None:
    current = state(solution_recommendations=[])
    current.pop("solution_recommendations")

    patch = execute_node(
        DealScoreNode(),
        current,
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3b_responses()),
    )

    assert patch["deal_score"].total_score >= 0


def test_deal_score_node_uses_recommendations_for_solution_fit() -> None:
    with_rec = execute_node(
        DealScoreNode(),
        state(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3b_responses()),
    )["deal_score"]
    without_rec = execute_node(
        DealScoreNode(),
        state(solution_recommendations=[]),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3b_responses()),
    )["deal_score"]

    assert with_rec.total_score > without_rec.total_score


def test_missing_dependency_fails() -> None:
    current = state()
    current.pop("buying_intent")

    patch = execute_node(
        DealScoreNode(),
        current,
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3b_responses()),
    )

    assert patch["failures"][0].failure_category is FailureCategory.missing_dependency


def test_internal_scoring_failure_enters_failure_state(monkeypatch) -> None:
    from agent.workflow_c.nodes import deal_score as deal_score_module

    def fail(**kwargs):
        raise ValueError("scoring failed")

    monkeypatch.setattr(deal_score_module, "calculate_deal_score", fail)

    patch = execute_node(
        DealScoreNode(),
        state(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3b_responses()),
    )

    assert patch["failures"][0].node_name is WorkflowNodeName.deal_score
    assert "deal_score" not in patch


def test_deal_score_node_does_not_generate_later_outputs() -> None:
    patch = execute_node(
        DealScoreNode(),
        state(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3b_responses()),
    )

    assert "risk" not in patch
    assert "next_best_action" not in patch
    assert "final_report" not in patch
