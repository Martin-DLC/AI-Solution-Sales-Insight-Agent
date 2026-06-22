from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from agent.workflow_c.deal_scoring import (
    DealScoringError,
    build_fallback_evidence,
    calculate_deal_score,
    collect_model_evidence,
    deduplicate_evidence,
    determine_deal_score_level,
    has_fact_category,
    has_information_gap,
    normalize_rule_text,
)
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
from agent.workflow_c.nodes import SourceIndexingNode
from agent.workflow_c.retrieval_models import SolutionRetrievalResult
from agent.workflow_c.services import WorkflowServices
from agent.workflow_c.solution_retrieval import retrieve_solution_candidates
from agent.workflow_c.state import (
    AnalysisMode,
    ContextSufficiencyResult,
    FactExtractionResult,
    SourceIndexItem,
    SourceIndexResult,
)
from dataio.runtime_cases import load_runtime_cases
from schemas.common_models import (
    BusinessDimension,
    ConfidenceLevel,
    ContextQuality,
    DealScoreDimensionName,
    DealScoreLevel,
    EvidenceReference,
    EvidenceSourceType,
    InformationGapCategory,
    IntentLevel,
    OpportunitySuitability,
    SalesRole,
    SalesStage,
    SeverityLevel,
    SolutionFitLevel,
)
from schemas.decision_models import DEAL_SCORE_WEIGHTS
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


def source_index() -> SourceIndexResult:
    return execute_node(
        SourceIndexingNode(),
        {"validated_case": dev_01_case()},
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )["source_index"]


def context(
    quality: ContextQuality = ContextQuality.partially_sufficient,
) -> ContextSufficiencyResult:
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
        reasoning_summary="当前材料足够进行受限分析，但仍有关键缺口。",
    )


def fact_extraction(payload: dict | None = None) -> FactExtractionResult:
    return FactExtractionResult.model_validate(payload or default_fact_response())


def explicit_needs(payload: dict | None = None) -> list[ExplicitNeed]:
    return [
        ExplicitNeed.model_validate(item)
        for item in (payload or default_explicit_need_response())["explicit_needs"]
    ]


def pains(payload: dict | None = None) -> list[UnderlyingPain]:
    return [
        UnderlyingPain.model_validate(item)
        for item in (payload or default_underlying_pain_response())["underlying_pains"]
    ]


def impacts(payload: dict | None = None) -> list[BusinessImpact]:
    return [
        BusinessImpact.model_validate(item)
        for item in (payload or default_business_impact_response())["business_impacts"]
    ]


def buying_intent(**overrides) -> BuyingIntent:
    payload = deepcopy(default_buying_intent_response()["buying_intent"])
    payload.update(overrides)
    return BuyingIntent.model_validate(payload)


def stakeholders(payload: dict | None = None) -> list[Stakeholder]:
    return [
        Stakeholder.model_validate(item)
        for item in (payload or default_stakeholder_response())["stakeholder_map"]
    ]


def gaps(payload: dict | None = None) -> list[InformationGap]:
    return [
        InformationGap.model_validate(item)
        for item in (payload or default_information_gap_response())["information_gaps"]
    ]


def opportunities(payload: dict | None = None) -> list[AIOpportunity]:
    return [
        AIOpportunity.model_validate(item)
        for item in (payload or default_ai_opportunity_response())["ai_opportunities"]
    ]


def recommendations(payload: dict | None = None) -> list[SolutionRecommendation]:
    return [
        SolutionRecommendation.model_validate(item)
        for item in (payload or default_solution_recommendation_response())[
            "solution_recommendations"
        ]
    ]


def retrieved(
    *,
    ai_opportunities: list[AIOpportunity] | None = None,
    top_k: int = 5,
) -> SolutionRetrievalResult:
    selected = ai_opportunities or opportunities()
    return retrieve_solution_candidates(
        case=dev_01_case(),
        source_index=source_index(),
        ai_opportunities=selected,
        underlying_pains=pains(),
        business_impacts=impacts(),
        top_k=top_k,
    )


def zero_retrieval() -> SolutionRetrievalResult:
    return SolutionRetrievalResult(
        query_text="NO_ELIGIBLE_AI_OPPORTUNITY",
        eligible_opportunity_ids=[],
        top_k=5,
        candidate_count=0,
        candidates=[],
    )


def score(**overrides):
    args = {
        "source_index": source_index(),
        "context_sufficiency": context(),
        "fact_extraction": fact_extraction(),
        "explicit_needs": explicit_needs(),
        "underlying_pains": pains(),
        "business_impacts": impacts(),
        "buying_intent": buying_intent(),
        "stakeholder_map": stakeholders(),
        "information_gaps": gaps(),
        "ai_opportunities": opportunities(),
        "retrieved_solutions": retrieved(),
        "solution_recommendations": recommendations(),
    }
    args.update(overrides)
    return calculate_deal_score(**args)


def dimension(result, name: DealScoreDimensionName):
    return next(item for item in result.dimensions if item.dimension is name)


def test_normalize_rule_text() -> None:
    assert normalize_rule_text(" Budget  Plan ") == "budget plan"


def test_deduplicate_evidence_preserves_order() -> None:
    evidence = explicit_needs()[0].evidence
    assert deduplicate_evidence([evidence[0], evidence[0]]) == [evidence[0]]


def test_collect_model_evidence_uses_real_evidence_fields_only() -> None:
    collected = collect_model_evidence([explicit_needs()[0], object()])

    assert collected == explicit_needs()[0].evidence


def test_has_information_gap_uses_structured_category() -> None:
    assert has_information_gap(gaps(), {InformationGapCategory.budget})


def test_has_fact_category_uses_fixed_aliases() -> None:
    payload = default_fact_response()
    payload["facts"][0]["category"] = "预算"
    assert has_fact_category(fact_extraction(payload), {"budget", "预算"})


def test_generates_exactly_seven_dimensions() -> None:
    assert len(score().dimensions) == 7


def test_all_max_scores_match_deal_score_weights() -> None:
    result = score()

    assert {item.dimension: item.max_score for item in result.dimensions} == DEAL_SCORE_WEIGHTS


def test_total_score_equals_sum_of_dimensions() -> None:
    result = score()

    assert result.total_score == sum(item.score for item in result.dimensions)


def test_same_input_result_is_identical() -> None:
    first = score().model_dump(mode="json")
    second = score().model_dump(mode="json")

    assert first == second


def test_each_dimension_has_evidence() -> None:
    assert all(item.evidence for item in score().dimensions)


def test_business_need_counts_needs_pains_and_impacts() -> None:
    result = score()

    assert dimension(result, DealScoreDimensionName.business_need).score == 10


def test_business_need_is_capped_at_twenty() -> None:
    need_payload = default_explicit_need_response()
    need_payload["explicit_needs"].append(
        {**need_payload["explicit_needs"][0], "need_id": "NEED-02", "description": "客户还明确希望减少人工整理线索。"}
    )
    pain_payload = default_underlying_pain_response()
    pain_payload["underlying_pains"].append(
        {**pain_payload["underlying_pains"][0], "pain_id": "PAIN-02", "description": "人工流程可能导致客户响应延迟。"}
    )
    impact_payload = default_business_impact_response()
    impact_payload["business_impacts"].append(
        {**impact_payload["business_impacts"][0], "impact_id": "IMPACT-02", "description": "响应延迟可能影响潜在客户转化。"}
    )

    result = score(
        explicit_needs=explicit_needs(need_payload),
        underlying_pains=pains(pain_payload),
        business_impacts=impacts(impact_payload),
    )

    assert dimension(result, DealScoreDimensionName.business_need).score == 20


def test_no_business_impact_makes_business_value_zero() -> None:
    result = score(business_impacts=[])

    assert dimension(result, DealScoreDimensionName.business_value).score == 0


def test_qualitative_business_impact_scores_eight() -> None:
    result = score()

    assert dimension(result, DealScoreDimensionName.business_value).score == 8


def test_quantified_business_impact_adds_points() -> None:
    payload = default_business_impact_response()
    payload["business_impacts"][0]["quantified"] = True
    payload["business_impacts"][0]["current_value"] = "当前平均响应为2天"

    result = score(business_impacts=impacts(payload))

    assert dimension(result, DealScoreDimensionName.business_value).score == 12


def test_multiple_business_dimensions_add_points() -> None:
    payload = default_business_impact_response()
    payload["business_impacts"].append(
        {
            **payload["business_impacts"][0],
            "impact_id": "IMPACT-02",
            "description": "体验改善可能提升客户服务满意度。",
            "impact_type": BusinessDimension.customer_experience.value,
        }
    )

    result = score(business_impacts=impacts(payload))

    assert dimension(result, DealScoreDimensionName.business_value).score == 11


def test_budget_fact_scores_fifteen() -> None:
    payload = default_fact_response()
    payload["facts"].append(
        {
            **payload["facts"][0],
            "fact_id": "FACT-BUDGET",
            "category": "budget",
            "statement": "客户明确已有项目预算。",
        }
    )

    result = score(fact_extraction=fact_extraction(payload), information_gaps=[])

    assert dimension(result, DealScoreDimensionName.budget).score == 15


def test_budget_gap_scores_three() -> None:
    assert dimension(score(), DealScoreDimensionName.budget).score == 3


def test_unknown_budget_is_not_treated_as_approved() -> None:
    result = score(information_gaps=[], buying_intent=buying_intent(intent_level=IntentLevel.medium.value))

    assert dimension(result, DealScoreDimensionName.budget).score == 9


def test_confirmed_decision_maker_and_budget_owner_scores_authority_fifteen() -> None:
    payload = default_stakeholder_response()
    payload["stakeholder_map"][0]["sales_role"] = SalesRole.decision_maker.value
    payload["stakeholder_map"].append(
        {
            **payload["stakeholder_map"][0],
            "stakeholder_id": "STK-BUDGET",
            "name_or_role": "预算负责人",
            "sales_role": SalesRole.budget_owner.value,
        }
    )

    result = score(stakeholder_map=stakeholders(payload), information_gaps=[])

    assert dimension(result, DealScoreDimensionName.authority).score == 15


def test_unconfirmed_key_role_does_not_score_as_confirmed() -> None:
    result = score(stakeholder_map=stakeholders(), information_gaps=[])

    assert dimension(result, DealScoreDimensionName.authority).score == 6


def test_authority_gap_caps_authority_score() -> None:
    payload = default_stakeholder_response()
    payload["stakeholder_map"][0]["sales_role"] = SalesRole.decision_maker.value
    payload["stakeholder_map"].append(
        {
            **payload["stakeholder_map"][0],
            "stakeholder_id": "STK-BUDGET",
            "name_or_role": "预算负责人",
            "sales_role": SalesRole.budget_owner.value,
        }
    )

    result = score(stakeholder_map=stakeholders(payload))

    assert dimension(result, DealScoreDimensionName.authority).score == 8


def test_timeline_fact_scores_ten() -> None:
    payload = default_fact_response()
    payload["facts"].append(
        {
            **payload["facts"][0],
            "fact_id": "FACT-TIMELINE",
            "category": "timeline",
            "statement": "客户明确希望下季度完成POC。",
        }
    )

    result = score(fact_extraction=fact_extraction(payload), information_gaps=[])

    assert dimension(result, DealScoreDimensionName.timeline).score == 10


def test_timeline_gap_scores_two() -> None:
    payload = default_information_gap_response()
    payload["information_gaps"][0]["category"] = InformationGapCategory.timeline.value

    result = score(information_gaps=gaps(payload))

    assert dimension(result, DealScoreDimensionName.timeline).score == 2


def test_no_eligible_opportunity_solution_fit_zero() -> None:
    blocked = [
        opportunities()[0].model_copy(
            update={
                "suitability": OpportunitySuitability.not_suitable_for_ai,
                "major_limitations": ["当前问题不适合AI处理。"],
            }
        )
    ]

    result = score(ai_opportunities=blocked, retrieved_solutions=zero_retrieval(), solution_recommendations=[])

    assert dimension(result, DealScoreDimensionName.solution_fit).score == 0


def test_eligible_opportunity_with_zero_candidates_solution_fit_four() -> None:
    result = score(retrieved_solutions=zero_retrieval(), solution_recommendations=[])

    assert dimension(result, DealScoreDimensionName.solution_fit).score == 4


def test_candidates_without_recommendation_solution_fit_seven() -> None:
    result = score(solution_recommendations=[])

    assert dimension(result, DealScoreDimensionName.solution_fit).score == 7


def test_high_fit_suitable_now_can_score_fifteen() -> None:
    opp = [
        opportunities()[0].model_copy(update={"suitability": OpportunitySuitability.suitable_now})
    ]
    rec = recommendations()[0].model_copy(update={"fit_level": SolutionFitLevel.high})

    result = score(ai_opportunities=opp, retrieved_solutions=retrieved(ai_opportunities=opp), solution_recommendations=[rec])

    assert dimension(result, DealScoreDimensionName.solution_fit).score == 15


def test_suitable_for_poc_caps_solution_fit_at_twelve() -> None:
    rec = recommendations()[0].model_copy(update={"fit_level": SolutionFitLevel.high})

    result = score(solution_recommendations=[rec])

    assert dimension(result, DealScoreDimensionName.solution_fit).score == 12


def test_suitable_after_prerequisites_caps_solution_fit_at_ten() -> None:
    opp = [
        opportunities()[0].model_copy(
            update={
                "suitability": OpportunitySuitability.suitable_after_prerequisites,
                "prerequisites": ["先确认数据权限"],
            }
        )
    ]
    rec = recommendations()[0].model_copy(update={"fit_level": SolutionFitLevel.high})

    result = score(ai_opportunities=opp, retrieved_solutions=retrieved(ai_opportunities=opp), solution_recommendations=[rec])

    assert dimension(result, DealScoreDimensionName.solution_fit).score == 10


def test_delivery_gap_categories_deduct_once_each() -> None:
    payload = default_information_gap_response()
    payload["information_gaps"] = [
        {
            **payload["information_gaps"][0],
            "gap_id": "GAP-DATA",
            "category": InformationGapCategory.data.value,
        },
        {
            **payload["information_gaps"][1],
            "gap_id": "GAP-SEC",
            "category": InformationGapCategory.security.value,
        },
    ]

    result = score(information_gaps=gaps(payload), solution_recommendations=[])

    assert dimension(result, DealScoreDimensionName.delivery_readiness).score == 5


def test_duplicate_delivery_gap_category_deducts_once() -> None:
    payload = default_information_gap_response()
    payload["information_gaps"] = [
        {
            **payload["information_gaps"][0],
            "gap_id": "GAP-DATA-1",
            "category": InformationGapCategory.data.value,
            "description": "数据权限未确认。",
            "question_to_ask": "数据权限如何确认？",
        },
        {
            **payload["information_gaps"][1],
            "gap_id": "GAP-DATA-2",
            "category": InformationGapCategory.data.value,
            "description": "数据质量未确认。",
            "question_to_ask": "数据质量如何确认？",
        },
    ]

    result = score(information_gaps=gaps(payload), solution_recommendations=[])

    assert dimension(result, DealScoreDimensionName.delivery_readiness).score == 7


def test_recommendation_prerequisites_deduct_delivery_readiness() -> None:
    rec = recommendations()[0].model_copy(update={"delivery_risks": []})

    result = score(solution_recommendations=[rec], information_gaps=[])

    assert dimension(result, DealScoreDimensionName.delivery_readiness).score == 7


def test_delivery_risk_deducts_delivery_readiness() -> None:
    rec = recommendations()[0].model_copy(update={"prerequisites": []})

    result = score(solution_recommendations=[rec], information_gaps=[])

    assert dimension(result, DealScoreDimensionName.delivery_readiness).score == 8


def test_opportunity_prerequisite_deducts_delivery_readiness() -> None:
    result = score(solution_recommendations=[], information_gaps=[])

    assert dimension(result, DealScoreDimensionName.delivery_readiness).score == 9


def test_delivery_readiness_not_below_zero() -> None:
    payload = default_information_gap_response()
    payload["information_gaps"] = [
        {
            **payload["information_gaps"][0],
            "gap_id": f"GAP-{category.value}",
            "category": category.value,
            "description": f"{category.value}仍未确认。",
            "question_to_ask": f"请确认{category.value}？",
        }
        for category in (
            InformationGapCategory.data,
            InformationGapCategory.integration,
            InformationGapCategory.security,
            InformationGapCategory.compliance,
            InformationGapCategory.delivery_readiness,
        )
    ]

    result = score(information_gaps=gaps(payload))

    assert dimension(result, DealScoreDimensionName.delivery_readiness).score == 0


@pytest.mark.parametrize(
    ("total", "level"),
    [
        (80, DealScoreLevel.high),
        (65, DealScoreLevel.medium_high),
        (45, DealScoreLevel.medium),
        (25, DealScoreLevel.low),
        (24, DealScoreLevel.very_low),
    ],
)
def test_score_level_boundaries(total: int, level: DealScoreLevel) -> None:
    assert determine_deal_score_level(total) is level


def test_confidence_high_when_sufficient_and_few_high_gaps() -> None:
    result = score(context_sufficiency=context(ContextQuality.sufficient), information_gaps=[])

    assert result.confidence is ConfidenceLevel.high


def test_confidence_medium_when_partially_sufficient() -> None:
    assert score().confidence is ConfidenceLevel.medium


def test_confidence_low_when_insufficient() -> None:
    result = score(context_sufficiency=context(ContextQuality.insufficient))

    assert result.confidence is ConfidenceLevel.low


def test_score_limiters_are_unique() -> None:
    result = score()

    assert len(result.score_limiters) == len(set(result.score_limiters))


def test_conditions_to_increase_score_are_stable() -> None:
    first = score().conditions_to_increase_score
    second = score().conditions_to_increase_score

    assert first == second


def test_reasoning_summary_says_not_probability() -> None:
    assert "不等于成交概率" in score().reasoning_summary


def test_fallback_evidence_uses_real_source_id() -> None:
    evidence = build_fallback_evidence(
        source_index=source_index(),
        dimension=DealScoreDimensionName.budget,
        summary="当前材料未确认预算。",
    )

    assert evidence.source_id == "MTG-01"


def test_fallback_evidence_does_not_include_full_source_content() -> None:
    index = source_index()
    evidence = build_fallback_evidence(
        source_index=index,
        dimension=DealScoreDimensionName.timeline,
        summary="当前材料未确认时间表。",
    )

    assert index.items[1].content not in evidence.evidence_summary


def test_fallback_evidence_raises_without_usable_source() -> None:
    index = SourceIndexResult(
        items=[
            SourceIndexItem(
                source_id="NOTE-01",
                source_type=EvidenceSourceType.salesperson_note,
                source_order=1,
                title="Note",
                content="Unverified note",
                verified=False,
            )
        ],
        source_count=1,
    )

    with pytest.raises(DealScoringError):
        build_fallback_evidence(
            source_index=index,
            dimension=DealScoreDimensionName.budget,
            summary="当前材料未确认预算。",
        )


def test_does_not_modify_input_objects() -> None:
    source = source_index()
    before = source.model_dump(mode="json")
    calculate_deal_score(
        source_index=source,
        context_sufficiency=context(),
        fact_extraction=fact_extraction(),
        explicit_needs=explicit_needs(),
        underlying_pains=pains(),
        business_impacts=impacts(),
        buying_intent=buying_intent(),
        stakeholder_map=stakeholders(),
        information_gaps=gaps(),
        ai_opportunities=opportunities(),
        retrieved_solutions=retrieved(),
        solution_recommendations=recommendations(),
    )

    assert source.model_dump(mode="json") == before


def test_deal_scoring_does_not_read_reference_pack() -> None:
    source = Path("agent/workflow_c/deal_scoring.py").read_text(encoding="utf-8")

    assert "HiddenReferencePack" not in source
    assert "evaluation_references" not in source
