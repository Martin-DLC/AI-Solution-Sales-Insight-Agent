from __future__ import annotations

from agent.workflow_c.executor import execute_node
from agent.workflow_c.nodes import SourceIndexingNode
from agent.workflow_c.services import WorkflowServices
from agent.workflow_c.solution_validation import (
    build_solution_catalog,
    validate_recommendation_in_retrieved_candidates,
    validate_solution_recommendation,
)
from agent.workflow_c.solution_retrieval import retrieve_solution_candidates
from agent.workflow_c.fake_llm import FakeWorkflowLLMClient, default_ai_opportunity_response
from dataio.runtime_cases import load_runtime_cases
from schemas.common_models import EvidenceSourceType, OpportunitySuitability
from schemas.solution_models import AIOpportunity, SolutionRecommendation


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


def retrieved_solutions():
    return retrieve_solution_candidates(
        case=dev_01_case(),
        source_index=source_index(),
        ai_opportunities=opportunities(),
        underlying_pains=[],
        business_impacts=[],
    )


def recommendation(**overrides) -> SolutionRecommendation:
    payload = {
        "recommendation_id": "REC-01",
        "solution_id": "客服辅助回复方案",
        "solution_name": "客服辅助回复方案",
        "fit_level": "medium",
        "related_opportunity_ids": ["OPP-01"],
        "recommended_scope": "围绕CRM线索数据进行销售跟进洞察的POC验证。",
        "fit_reasons": ["该方案来自输入方案库，且与线索跟进效率问题相关。"],
        "prerequisites": ["确认CRM数据字段和访问方式"],
        "delivery_risks": ["数据字段质量不足可能影响POC效果判断。"],
        "excluded_capabilities": ["不承诺完整销售自动化闭环。"],
        "knowledge_references": [
            {
                "source_id": "SOLUTION-04",
                "source_type": "solution_library",
                "evidence_summary": "方案库中列出了客服辅助回复方案。",
            }
        ],
        "confidence": "medium",
    }
    payload.update(overrides)
    return SolutionRecommendation.model_validate(payload)


def test_build_solution_catalog_success() -> None:
    catalog = build_solution_catalog(dev_01_case(), source_index())

    assert list(catalog) == dev_01_case().available_solution_library


def test_solution_catalog_only_contains_solution_library() -> None:
    catalog = build_solution_catalog(dev_01_case(), source_index())

    assert all(item.source_type is EvidenceSourceType.solution_library for item in catalog.values())


def test_solution_catalog_matches_available_solution_library() -> None:
    catalog = build_solution_catalog(dev_01_case(), source_index())

    assert set(catalog) == set(dev_01_case().available_solution_library)


def test_unknown_solution_id_fails() -> None:
    issues = validate_solution_recommendation(
        recommendation=recommendation(solution_id="unknown-solution"),
        recommendation_index=0,
        solution_catalog=build_solution_catalog(dev_01_case(), source_index()),
        ai_opportunities=opportunities(),
    )

    assert any(issue.location.endswith("solution_id") for issue in issues)


def test_unknown_related_opportunity_id_fails() -> None:
    issues = validate_solution_recommendation(
        recommendation=recommendation(related_opportunity_ids=["OPP-NOPE"]),
        recommendation_index=0,
        solution_catalog=build_solution_catalog(dev_01_case(), source_index()),
        ai_opportunities=opportunities(),
    )

    assert any("related_opportunity_ids" in issue.location for issue in issues)


def test_missing_knowledge_reference_fails() -> None:
    payload = recommendation()
    payload.knowledge_references.clear()

    issues = validate_solution_recommendation(
        recommendation=payload,
        recommendation_index=0,
        solution_catalog=build_solution_catalog(dev_01_case(), source_index()),
        ai_opportunities=opportunities(),
    )

    assert any("knowledge_references" in issue.location for issue in issues)


def test_non_solution_library_reference_fails() -> None:
    payload = recommendation(
        knowledge_references=[
            {
                "source_id": "MTG-01",
                "source_type": "meeting_transcript",
                "evidence_summary": "会议不是方案知识库引用。",
            },
            {
                "source_id": "SOLUTION-01",
                "source_type": "solution_library",
                "evidence_summary": "方案库中列出了AI客服知识问答方案。",
            },
        ]
    )

    issues = validate_solution_recommendation(
        recommendation=payload,
        recommendation_index=0,
        solution_catalog=build_solution_catalog(dev_01_case(), source_index()),
        ai_opportunities=opportunities(),
    )

    assert any(issue.location.endswith("source_type") for issue in issues)


def test_source_id_mismatch_fails() -> None:
    issues = validate_solution_recommendation(
        recommendation=recommendation(
            knowledge_references=[
                {
                    "source_id": "SOLUTION-02",
                    "source_type": "solution_library",
                    "evidence_summary": "错误方案引用。",
                }
            ]
        ),
        recommendation_index=0,
        solution_catalog=build_solution_catalog(dev_01_case(), source_index()),
        ai_opportunities=opportunities(),
    )

    assert any(issue.location.endswith("source_id") for issue in issues)


def test_knowledge_reference_points_to_wrong_solution_fails() -> None:
    issues = validate_solution_recommendation(
        recommendation=recommendation(solution_id="RAG企业知识库方案"),
        recommendation_index=0,
        solution_catalog=build_solution_catalog(dev_01_case(), source_index()),
        ai_opportunities=opportunities(),
    )

    assert any("knowledge_references" in issue.location for issue in issues)


def test_eligible_opportunity_can_be_recommended() -> None:
    issues = validate_solution_recommendation(
        recommendation=recommendation(),
        recommendation_index=0,
        solution_catalog=build_solution_catalog(dev_01_case(), source_index()),
        ai_opportunities=opportunities(),
    )

    assert issues == []


def test_recommendation_must_be_in_retrieved_candidates() -> None:
    issues = validate_recommendation_in_retrieved_candidates(
        recommendation=recommendation(solution_id="AI客服知识问答方案"),
        recommendation_index=0,
        retrieved_solutions=retrieved_solutions(),
    )

    assert any("retrieved solution candidates" in issue.message for issue in issues)


def test_recommendation_candidate_reference_must_match_retrieved_source() -> None:
    issues = validate_recommendation_in_retrieved_candidates(
        recommendation=recommendation(
            knowledge_references=[
                {
                    "source_id": "SOLUTION-01",
                    "source_type": "solution_library",
                    "evidence_summary": "错误方案引用。",
                }
            ]
        ),
        recommendation_index=0,
        retrieved_solutions=retrieved_solutions(),
    )

    assert any("candidate source_id" in issue.message for issue in issues)


def test_not_suitable_for_ai_opportunity_cannot_be_recommended() -> None:
    opp = opportunities()[0].model_copy(
        update={
            "suitability": OpportunitySuitability.not_suitable_for_ai,
            "major_limitations": ["当前问题不适合AI处理。"],
        }
    )

    issues = validate_solution_recommendation(
        recommendation=recommendation(),
        recommendation_index=0,
        solution_catalog=build_solution_catalog(dev_01_case(), source_index()),
        ai_opportunities=[opp],
    )

    assert any("eligible" in issue.message for issue in issues)


def test_insufficient_information_opportunity_cannot_be_recommended() -> None:
    opp = opportunities()[0].model_copy(
        update={
            "suitability": OpportunitySuitability.insufficient_information,
            "major_limitations": ["信息不足，不能推荐方案。"],
        }
    )

    issues = validate_solution_recommendation(
        recommendation=recommendation(),
        recommendation_index=0,
        solution_catalog=build_solution_catalog(dev_01_case(), source_index()),
        ai_opportunities=[opp],
    )

    assert any("eligible" in issue.message for issue in issues)


def test_issue_does_not_include_full_customer_text() -> None:
    issues = validate_solution_recommendation(
        recommendation=recommendation(solution_id="unknown-solution"),
        recommendation_index=0,
        solution_catalog=build_solution_catalog(dev_01_case(), source_index()),
        ai_opportunities=opportunities(),
    )

    assert all("会议纪要" not in (issue.input_summary or "") for issue in issues)


def test_does_not_read_reference_pack() -> None:
    catalog = build_solution_catalog(dev_01_case(), source_index())

    assert "reference" not in repr(catalog).casefold()
