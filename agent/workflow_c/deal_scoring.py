from __future__ import annotations

from collections.abc import Iterable

from agent.workflow_c.retrieval_models import SolutionRetrievalResult
from agent.workflow_c.state import (
    ContextSufficiencyResult,
    FactExtractionResult,
    SourceIndexItem,
    SourceIndexResult,
)
from schemas.common_models import (
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
from schemas.decision_models import (
    DEAL_SCORE_WEIGHTS,
    DealScore,
    DealScoreDimension,
    score_level_for_total,
)
from schemas.insight_models import (
    BusinessImpact,
    BuyingIntent,
    ExplicitNeed,
    InformationGap,
    Stakeholder,
    UnderlyingPain,
)
from schemas.solution_models import AIOpportunity, SolutionRecommendation


BUDGET_FACT_ALIASES = {"budget", "预算"}
TIMELINE_FACT_ALIASES = {"timeline", "时间表", "时间计划"}

_DELIVERY_GAP_CATEGORIES = {
    InformationGapCategory.data,
    InformationGapCategory.integration,
    InformationGapCategory.security,
    InformationGapCategory.compliance,
    InformationGapCategory.delivery_readiness,
}

_ELIGIBLE_OPPORTUNITY = {
    OpportunitySuitability.suitable_now,
    OpportunitySuitability.suitable_for_poc,
    OpportunitySuitability.suitable_after_prerequisites,
}

_CONDITION_BY_GAP = {
    InformationGapCategory.budget: "确认预算范围、审批状态和资金来源。",
    InformationGapCategory.authority: "确认最终决策人、预算负责人及其参与方式。",
    InformationGapCategory.decision_process: "确认决策链、审批节点和最终签署流程。",
    InformationGapCategory.timeline: "确认采购时间、POC时间和目标上线里程碑。",
    InformationGapCategory.procurement: "确认采购流程、供应商准入和合同要求。",
    InformationGapCategory.data: "确认数据来源、质量、权限和可用范围。",
    InformationGapCategory.integration: "确认系统接口、集成责任和技术边界。",
    InformationGapCategory.security: "完成安全要求、权限管理和数据保护确认。",
    InformationGapCategory.compliance: "完成适用法规和内部合规要求确认。",
    InformationGapCategory.delivery_readiness: "确认客户资源、项目Owner和实施配合能力。",
}


class DealScoringError(Exception):
    pass


def normalize_rule_text(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def deduplicate_evidence(
    evidence: list[EvidenceReference],
) -> list[EvidenceReference]:
    seen: set[tuple[str, EvidenceSourceType, str]] = set()
    result: list[EvidenceReference] = []
    for item in evidence:
        key = (item.source_id, item.source_type, item.evidence_summary)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def collect_model_evidence(
    items: list[object],
) -> list[EvidenceReference]:
    collected: list[EvidenceReference] = []
    for item in items:
        evidence = getattr(item, "evidence", None)
        if isinstance(evidence, list):
            collected.extend(
                reference
                for reference in evidence
                if isinstance(reference, EvidenceReference)
            )
    return deduplicate_evidence(collected)


def build_fallback_evidence(
    *,
    source_index: SourceIndexResult,
    dimension: DealScoreDimensionName,
    summary: str,
) -> EvidenceReference:
    item = _select_fallback_source(source_index)
    return EvidenceReference(
        source_id=item.source_id,
        source_type=item.source_type,
        evidence_summary=(
            f"{dimension.value}：当前材料覆盖情况或信息缺口；{summary}"
        ),
    )


def has_information_gap(
    information_gaps: list[InformationGap],
    categories: set[InformationGapCategory],
) -> bool:
    return any(gap.category in categories for gap in information_gaps)


def has_fact_category(
    fact_extraction: FactExtractionResult,
    aliases: set[str],
) -> bool:
    normalized_aliases = {normalize_rule_text(value) for value in aliases}
    return any(
        normalize_rule_text(fact.category) in normalized_aliases
        for fact in fact_extraction.facts
    )


def determine_deal_score_level(total_score: int) -> DealScoreLevel:
    return score_level_for_total(total_score)


def calculate_deal_score(
    *,
    source_index: SourceIndexResult,
    context_sufficiency: ContextSufficiencyResult,
    fact_extraction: FactExtractionResult,
    explicit_needs: list[ExplicitNeed],
    underlying_pains: list[UnderlyingPain],
    business_impacts: list[BusinessImpact],
    buying_intent: BuyingIntent,
    stakeholder_map: list[Stakeholder],
    information_gaps: list[InformationGap],
    ai_opportunities: list[AIOpportunity],
    retrieved_solutions: SolutionRetrievalResult,
    solution_recommendations: list[SolutionRecommendation] | None = None,
) -> DealScore:
    recommendations = solution_recommendations or []
    dimensions = [
        _score_business_need(source_index, explicit_needs, underlying_pains, business_impacts),
        _score_business_value(source_index, business_impacts),
        _score_budget(source_index, fact_extraction, buying_intent, information_gaps),
        _score_authority(source_index, stakeholder_map, information_gaps),
        _score_timeline(source_index, fact_extraction, buying_intent, information_gaps),
        _score_solution_fit(
            source_index,
            ai_opportunities,
            retrieved_solutions,
            recommendations,
        ),
        _score_delivery_readiness(
            source_index,
            information_gaps,
            ai_opportunities,
            recommendations,
        ),
    ]
    total_score = sum(dimension.score for dimension in dimensions)
    score_level = determine_deal_score_level(total_score)
    return DealScore(
        total_score=total_score,
        score_level=score_level,
        confidence=_determine_confidence(context_sufficiency, information_gaps),
        dimensions=dimensions,
        score_limiters=_build_score_limiters(
            dimensions,
            information_gaps,
            stakeholder_map,
            retrieved_solutions,
        ),
        conditions_to_increase_score=_build_conditions_to_increase_score(
            information_gaps,
            stakeholder_map,
            retrieved_solutions,
        ),
        reasoning_summary=_build_reasoning_summary(dimensions, total_score, score_level),
    )


def _score_business_need(
    source_index: SourceIndexResult,
    explicit_needs: list[ExplicitNeed],
    underlying_pains: list[UnderlyingPain],
    business_impacts: list[BusinessImpact],
) -> DealScoreDimension:
    score = min(
        DEAL_SCORE_WEIGHTS[DealScoreDimensionName.business_need],
        min(len(explicit_needs) * 4, 8)
        + min(len(underlying_pains) * 3, 6)
        + min(len(business_impacts) * 3, 6),
    )
    evidence = collect_model_evidence(
        [*explicit_needs, *underlying_pains, *business_impacts]
    ) or [
        build_fallback_evidence(
            source_index=source_index,
            dimension=DealScoreDimensionName.business_need,
            summary="当前材料未形成明确需求、痛点或影响证据。",
        )
    ]
    return _dimension(
        DealScoreDimensionName.business_need,
        score,
        f"业务需求按显性需求、潜在痛点和业务影响数量规则计算为{score}分。",
        evidence,
    )


def _score_business_value(
    source_index: SourceIndexResult,
    business_impacts: list[BusinessImpact],
) -> DealScoreDimension:
    if not business_impacts:
        score = 0
    else:
        dimensions = {impact.impact_type for impact in business_impacts}
        score = 8
        if any(impact.quantified for impact in business_impacts):
            score += 4
        if len(dimensions) >= 2:
            score += 3
    evidence = collect_model_evidence(business_impacts) or [
        build_fallback_evidence(
            source_index=source_index,
            dimension=DealScoreDimensionName.business_value,
            summary="当前材料尚未形成可引用的业务影响证据。",
        )
    ]
    return _dimension(
        DealScoreDimensionName.business_value,
        min(score, DEAL_SCORE_WEIGHTS[DealScoreDimensionName.business_value]),
        f"业务价值只按业务影响数量、量化状态和影响维度覆盖计算为{min(score, 15)}分。",
        evidence,
    )


def _score_budget(
    source_index: SourceIndexResult,
    fact_extraction: FactExtractionResult,
    buying_intent: BuyingIntent,
    information_gaps: list[InformationGap],
) -> DealScoreDimension:
    budget_facts = _facts_by_category(fact_extraction, BUDGET_FACT_ALIASES)
    if budget_facts:
        score = 15
        evidence = collect_model_evidence(budget_facts)
        reasoning = "预算维度存在明确budget事实，因此按规则计为15分。"
    elif has_information_gap(information_gaps, {InformationGapCategory.budget}):
        score = 3
        evidence = [
            build_fallback_evidence(
                source_index=source_index,
                dimension=DealScoreDimensionName.budget,
                summary="当前材料未确认预算，且预算被列为信息缺口。",
            )
        ]
        reasoning = "预算仍为信息缺口，不能视为已批准预算，因此按规则计为3分。"
    else:
        score = {
            IntentLevel.high: 12,
            IntentLevel.medium_high: 12,
            IntentLevel.medium: 9,
            IntentLevel.low: 6,
            IntentLevel.unknown: 6,
        }[buying_intent.intent_level]
        evidence = [
            build_fallback_evidence(
                source_index=source_index,
                dimension=DealScoreDimensionName.budget,
                summary="当前材料未直接确认预算，按购买意向等级进行受限评分。",
            )
        ]
        reasoning = f"未发现预算事实或预算缺口，按购买意向{buying_intent.intent_level.value}计为{score}分。"
    return _dimension(DealScoreDimensionName.budget, score, reasoning, evidence)


def _score_authority(
    source_index: SourceIndexResult,
    stakeholder_map: list[Stakeholder],
    information_gaps: list[InformationGap],
) -> DealScoreDimension:
    confirmed_roles = {
        stakeholder.sales_role
        for stakeholder in stakeholder_map
        if stakeholder.confirmed
    }
    if {SalesRole.decision_maker, SalesRole.budget_owner}.issubset(confirmed_roles):
        score = 15
    elif confirmed_roles & {SalesRole.decision_maker, SalesRole.budget_owner}:
        score = 12
    elif confirmed_roles & {SalesRole.business_owner, SalesRole.champion}:
        score = 9
    elif confirmed_roles:
        score = 6
    elif stakeholder_map:
        score = 4
    else:
        score = 0

    if has_information_gap(
        information_gaps,
        {InformationGapCategory.authority, InformationGapCategory.decision_process},
    ):
        score = min(score, 8)
    evidence = collect_model_evidence(stakeholder_map) or [
        build_fallback_evidence(
            source_index=source_index,
            dimension=DealScoreDimensionName.authority,
            summary="当前材料未确认关键权限角色或决策链。",
        )
    ]
    return _dimension(
        DealScoreDimensionName.authority,
        score,
        f"权限维度只按confirmed角色和权限信息缺口计算为{score}分。",
        evidence,
    )


def _score_timeline(
    source_index: SourceIndexResult,
    fact_extraction: FactExtractionResult,
    buying_intent: BuyingIntent,
    information_gaps: list[InformationGap],
) -> DealScoreDimension:
    timeline_facts = _facts_by_category(fact_extraction, TIMELINE_FACT_ALIASES)
    if timeline_facts:
        score = 10
        evidence = collect_model_evidence(timeline_facts)
        reasoning = "时间线维度存在明确timeline事实，因此按规则计为10分。"
    elif has_information_gap(information_gaps, {InformationGapCategory.timeline}):
        score = 2
        evidence = [
            build_fallback_evidence(
                source_index=source_index,
                dimension=DealScoreDimensionName.timeline,
                summary="当前材料未确认时间表，且时间线被列为信息缺口。",
            )
        ]
        reasoning = "时间表仍为信息缺口，不能自动生成客户时间表，因此计为2分。"
    else:
        score = {
            SalesStage.procurement: 8,
            SalesStage.contracting: 8,
            SalesStage.poc_planning: 7,
            SalesStage.solution_exploration: 6,
            SalesStage.discovery: 5,
            SalesStage.unknown: 3,
        }[buying_intent.sales_stage]
        evidence = [
            build_fallback_evidence(
                source_index=source_index,
                dimension=DealScoreDimensionName.timeline,
                summary="当前材料未直接确认时间表，按销售阶段进行受限评分。",
            )
        ]
        reasoning = f"未发现时间表事实或缺口，按销售阶段{buying_intent.sales_stage.value}计为{score}分。"
    return _dimension(DealScoreDimensionName.timeline, score, reasoning, evidence)


def _score_solution_fit(
    source_index: SourceIndexResult,
    ai_opportunities: list[AIOpportunity],
    retrieved_solutions: SolutionRetrievalResult,
    recommendations: list[SolutionRecommendation],
) -> DealScoreDimension:
    eligible_by_id = {
        opportunity.opportunity_id: opportunity
        for opportunity in ai_opportunities
        if opportunity.suitability in _ELIGIBLE_OPPORTUNITY
    }
    if not eligible_by_id:
        score = 0
        evidence = collect_model_evidence(ai_opportunities)
        reasoning = "没有可推荐的Eligible AI Opportunity，因此Solution Fit为0分。"
    elif retrieved_solutions.candidate_count == 0:
        score = 4
        evidence = collect_model_evidence(eligible_by_id.values())
        reasoning = "存在Eligible AI Opportunity但没有检索候选，因此Solution Fit受限为4分。"
    elif not recommendations:
        score = 7
        evidence = collect_model_evidence(eligible_by_id.values())
        reasoning = "已有检索候选但没有方案推荐，因此Solution Fit受限为7分。"
    else:
        score = max(
            _recommendation_fit_score(recommendation, eligible_by_id)
            for recommendation in recommendations
        )
        evidence = collect_model_evidence(recommendations) or collect_model_evidence(
            eligible_by_id.values()
        )
        reasoning = f"Solution Fit按最高合法推荐方案及其关联机会适用性限制计算为{score}分。"

    evidence = evidence or [
        build_fallback_evidence(
            source_index=source_index,
            dimension=DealScoreDimensionName.solution_fit,
            summary="当前材料没有足够的方案候选或推荐证据。",
        )
    ]
    return _dimension(DealScoreDimensionName.solution_fit, score, reasoning, evidence)


def _score_delivery_readiness(
    source_index: SourceIndexResult,
    information_gaps: list[InformationGap],
    ai_opportunities: list[AIOpportunity],
    recommendations: list[SolutionRecommendation],
) -> DealScoreDimension:
    gap_categories = {
        gap.category
        for gap in information_gaps
        if gap.category in _DELIVERY_GAP_CATEGORIES
    }
    score = 10 - min(len(gap_categories) * 2, 8)
    if any(recommendation.prerequisites for recommendation in recommendations):
        score -= 2
    if any(recommendation.delivery_risks for recommendation in recommendations):
        score -= 1
    if any(opportunity.prerequisites for opportunity in ai_opportunities):
        score -= 1
    score = max(0, min(10, score))
    evidence = collect_model_evidence([*recommendations, *ai_opportunities]) or [
        build_fallback_evidence(
            source_index=source_index,
            dimension=DealScoreDimensionName.delivery_readiness,
            summary="当前材料覆盖交付准备度或相关信息缺口，但未提供独立证据字段。",
        )
    ]
    return _dimension(
        DealScoreDimensionName.delivery_readiness,
        score,
        f"交付准备度按数据、集成、安全、合规、前置条件和交付风险扣分后为{score}分。",
        evidence,
    )


def _dimension(
    dimension: DealScoreDimensionName,
    score: int,
    reasoning: str,
    evidence: list[EvidenceReference],
) -> DealScoreDimension:
    return DealScoreDimension(
        dimension=dimension,
        score=score,
        max_score=DEAL_SCORE_WEIGHTS[dimension],
        reasoning=reasoning,
        evidence=deduplicate_evidence(evidence),
    )


def _facts_by_category(
    fact_extraction: FactExtractionResult,
    aliases: set[str],
) -> list[object]:
    normalized_aliases = {normalize_rule_text(value) for value in aliases}
    return [
        fact
        for fact in fact_extraction.facts
        if normalize_rule_text(fact.category) in normalized_aliases
    ]


def _recommendation_fit_score(
    recommendation: SolutionRecommendation,
    eligible_by_id: dict[str, AIOpportunity],
) -> int:
    base = {
        SolutionFitLevel.high: 15,
        SolutionFitLevel.medium: 12,
        SolutionFitLevel.low: 7,
        SolutionFitLevel.not_recommended: 3,
    }[recommendation.fit_level]
    caps = [
        {
            OpportunitySuitability.suitable_now: 15,
            OpportunitySuitability.suitable_for_poc: 12,
            OpportunitySuitability.suitable_after_prerequisites: 10,
        }[eligible_by_id[opportunity_id].suitability]
        for opportunity_id in recommendation.related_opportunity_ids
        if opportunity_id in eligible_by_id
    ]
    if not caps:
        return 0
    return min(base, max(caps))


def _determine_confidence(
    context_sufficiency: ContextSufficiencyResult,
    information_gaps: list[InformationGap],
) -> ConfidenceLevel:
    high_gap_count = sum(1 for gap in information_gaps if gap.priority is SeverityLevel.high)
    if (
        context_sufficiency.context_quality is ContextQuality.sufficient
        and high_gap_count <= 1
    ):
        return ConfidenceLevel.high
    if context_sufficiency.context_quality in {
        ContextQuality.sufficient,
        ContextQuality.partially_sufficient,
    }:
        return ConfidenceLevel.medium
    return ConfidenceLevel.low


def _build_score_limiters(
    dimensions: list[DealScoreDimension],
    information_gaps: list[InformationGap],
    stakeholder_map: list[Stakeholder],
    retrieved_solutions: SolutionRetrievalResult,
) -> list[str]:
    limiters: list[str] = []
    for dimension in dimensions:
        if dimension.score < dimension.max_score * 0.6:
            limiters.append(
                f"{dimension.dimension.value}得分低于该维度满分的60%。"
            )
    for gap in information_gaps:
        if gap.priority is SeverityLevel.high:
            limiters.append(f"{gap.category.value}信息缺口：{gap.description}")
    if retrieved_solutions.candidate_count == 0:
        limiters.append("没有检索候选方案，Solution Fit受到限制。")
    confirmed_roles = {
        stakeholder.sales_role
        for stakeholder in stakeholder_map
        if stakeholder.confirmed
    }
    if not confirmed_roles & {SalesRole.decision_maker, SalesRole.budget_owner}:
        limiters.append("尚未确认decision_maker或budget_owner，Authority受到限制。")
    if has_information_gap(information_gaps, {InformationGapCategory.budget}):
        limiters.append("预算仍是信息缺口，Budget受到限制。")
    return _deduplicate_text(limiters)


def _build_conditions_to_increase_score(
    information_gaps: list[InformationGap],
    stakeholder_map: list[Stakeholder],
    retrieved_solutions: SolutionRetrievalResult,
) -> list[str]:
    conditions: list[str] = []
    for gap in information_gaps:
        condition = _CONDITION_BY_GAP.get(gap.category)
        if condition:
            conditions.append(condition)
    if retrieved_solutions.candidate_count == 0:
        conditions.append("补充方案匹配所需的业务、数据和集成信息。")
    confirmed_roles = {
        stakeholder.sales_role
        for stakeholder in stakeholder_map
        if stakeholder.confirmed
    }
    if not confirmed_roles & {SalesRole.decision_maker, SalesRole.budget_owner}:
        conditions.append("确认决策人和预算负责人的角色。")
    return _deduplicate_text(conditions)


def _build_reasoning_summary(
    dimensions: list[DealScoreDimension],
    total_score: int,
    score_level: DealScoreLevel,
) -> str:
    highest_score = max(dimension.score for dimension in dimensions)
    lowest_score = min(dimension.score for dimension in dimensions)
    highest = "、".join(
        dimension.dimension.value
        for dimension in dimensions
        if dimension.score == highest_score
    )
    lowest = "、".join(
        dimension.dimension.value
        for dimension in dimensions
        if dimension.score == lowest_score
    )
    return (
        f"当前商机成熟度为{total_score}分，等级为{score_level.value}。"
        f"主要优势是{highest}，主要限制是{lowest}。"
        "该分数用于衡量商机成熟度，不等于成交概率。"
    )


def _select_fallback_source(source_index: SourceIndexResult) -> SourceIndexItem:
    for item in source_index.items:
        if item.source_id == "MTG-01" or item.source_type is EvidenceSourceType.meeting_transcript:
            return item
    for item in source_index.items:
        if item.source_id == "PROFILE-01" or item.source_type is EvidenceSourceType.customer_profile:
            return item
    for item in source_index.items:
        if item.verified:
            return item
    raise DealScoringError("Deal score fallback evidence requires at least one usable source.")


def _deduplicate_text(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
