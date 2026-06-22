from __future__ import annotations

from agent.workflow_c.executor import execute_node
from agent.workflow_c.fake_llm import (
    FakeWorkflowLLMClient,
    default_ai_opportunity_response,
    default_business_impact_response,
    default_underlying_pain_response,
)
from agent.workflow_c.nodes import SourceIndexingNode
from agent.workflow_c.services import WorkflowServices
from agent.workflow_c.solution_retrieval import (
    NO_ELIGIBLE_AI_OPPORTUNITY_QUERY,
    build_solution_retrieval_query,
    normalize_retrieval_text,
    retrieve_solution_candidates,
    score_solution_candidate,
    tokenize_retrieval_text,
)
from dataio.runtime_cases import load_runtime_cases
from schemas.common_models import OpportunitySuitability
from schemas.insight_models import BusinessImpact, UnderlyingPain
from schemas.solution_models import AIOpportunity


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def source_index():
    return execute_node(
        SourceIndexingNode(),
        {"validated_case": dev_01_case()},
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )["source_index"]


def opportunities() -> list[AIOpportunity]:
    return [
        AIOpportunity.model_validate(item)
        for item in default_ai_opportunity_response()["ai_opportunities"]
    ]


def pains() -> list[UnderlyingPain]:
    return [
        UnderlyingPain.model_validate(item)
        for item in default_underlying_pain_response()["underlying_pains"]
    ]


def impacts() -> list[BusinessImpact]:
    return [
        BusinessImpact.model_validate(item)
        for item in default_business_impact_response()["business_impacts"]
    ]


def test_normalize_retrieval_text_nfkc_lowercases_and_collapses_spaces() -> None:
    assert normalize_retrieval_text("ＡＩ   客服") == "ai 客服"


def test_tokenize_mixed_chinese_and_english_text() -> None:
    tokens = tokenize_retrieval_text("AI客服知识问答 for CRM")

    assert "ai" in tokens
    assert "客服" in tokens
    assert "知识" in tokens
    assert "crm" in tokens
    assert "for" not in tokens


def test_score_solution_candidate_returns_score_and_terms() -> None:
    score, matched_terms = score_solution_candidate(
        "客服 回复 效率",
        "客服辅助回复方案",
    )

    assert score > 0
    assert "客服" in matched_terms


def test_score_solution_candidate_zero_when_no_overlap() -> None:
    score, matched_terms = score_solution_candidate("预算 审批", "售后知识库RAG方案")

    assert score == 0
    assert matched_terms == []


def test_query_uses_only_eligible_opportunities() -> None:
    query, eligible_ids = build_solution_retrieval_query(
        opportunities(),
        pains(),
        impacts(),
    )

    assert eligible_ids == ["OPP-01"]
    assert "销售线索跟进辅助机会" in query
    assert dev_01_case().customer_profile.company_name not in query


def test_query_returns_sentinel_when_no_eligible_opportunity() -> None:
    blocked = [
        opportunities()[0].model_copy(
            update={
                "suitability": OpportunitySuitability.not_suitable_for_ai,
                "major_limitations": ["当前问题不适合AI处理。"],
            }
        )
    ]

    query, eligible_ids = build_solution_retrieval_query(blocked, pains(), impacts())

    assert query == NO_ELIGIBLE_AI_OPPORTUNITY_QUERY
    assert eligible_ids == []


def test_retrieve_solution_candidates_returns_ordered_candidates() -> None:
    result = retrieve_solution_candidates(
        case=dev_01_case(),
        source_index=source_index(),
        ai_opportunities=opportunities(),
        underlying_pains=pains(),
        business_impacts=impacts(),
    )

    assert result.candidate_count >= 1
    assert result.candidates[0].rank == 1
    assert result.candidates[0].source_type.value == "solution_library"
    assert result.candidates[0].solution_id == "客服辅助回复方案"


def test_retrieve_solution_candidates_respects_top_k() -> None:
    result = retrieve_solution_candidates(
        case=dev_01_case(),
        source_index=source_index(),
        ai_opportunities=opportunities(),
        underlying_pains=pains(),
        business_impacts=impacts(),
        top_k=1,
    )

    assert result.candidate_count <= 1


def test_retrieve_solution_candidates_returns_empty_for_no_eligible_opportunity() -> None:
    blocked = [
        opportunities()[0].model_copy(
            update={
                "suitability": OpportunitySuitability.insufficient_information,
                "major_limitations": ["信息不足，不能推荐方案。"],
            }
        )
    ]

    result = retrieve_solution_candidates(
        case=dev_01_case(),
        source_index=source_index(),
        ai_opportunities=blocked,
        underlying_pains=pains(),
        business_impacts=impacts(),
    )

    assert result.candidate_count == 0
    assert result.candidates == []
