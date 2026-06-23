from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Iterable, TypeVar

from agent.workflow_c.state import ContextSufficiencyResult, FactExtractionResult
from schemas.common_models import (
    ClaimType,
    ConfidenceLevel,
    ContextQuality,
    EvaluationFlagType,
    EvidenceSourceType,
    InformationGapCategory,
    SalesRole,
    SeverityLevel,
)
from schemas.decision_models import CustomerFollowUp, DealScore, NextBestAction
from schemas.input_models import EvaluationCaseInput
from schemas.insight_models import (
    BusinessImpact,
    BuyingIntent,
    ExplicitNeed,
    InformationGap,
    Stakeholder,
    UnderlyingPain,
)
from schemas.output_models import (
    EvaluationFlag,
    ExecutiveSummary,
    ReliabilitySummary,
    SalesInsightReport,
)
from schemas.solution_models import AIOpportunity, Risk, SolutionRecommendation

T = TypeVar("T")


def utc_now() -> datetime:
    return datetime.now(UTC)


def build_analysis_id(
    *,
    run_id: str,
    case_id: str,
) -> str:
    digest = hashlib.sha256(f"{run_id}:{case_id}".encode("utf-8")).hexdigest()[:12]
    return f"analysis-{case_id}-{digest}"


def compose_sales_insight_report(
    *,
    analysis_id: str,
    generated_at: datetime,
    validated_case: EvaluationCaseInput,
    fact_extraction: FactExtractionResult,
    context_sufficiency: ContextSufficiencyResult,
    explicit_needs: list[ExplicitNeed],
    underlying_pains: list[UnderlyingPain],
    business_impacts: list[BusinessImpact],
    buying_intent: BuyingIntent,
    stakeholder_map: list[Stakeholder],
    information_gaps: list[InformationGap],
    ai_opportunities: list[AIOpportunity],
    solution_recommendations: list[SolutionRecommendation] | None,
    deal_score: DealScore,
    risks_and_objections: list[Risk],
    next_best_actions: list[NextBestAction],
) -> SalesInsightReport:
    recommendations = _copy_list(solution_recommendations or [])
    report = SalesInsightReport(
        schema_version="1.0",
        case_id=validated_case.case_id,
        analysis_id=analysis_id,
        generated_at=generated_at,
        executive_summary=_build_executive_summary(
            buying_intent=buying_intent,
            deal_score=deal_score,
            explicit_needs=explicit_needs,
            business_impacts=business_impacts,
            ai_opportunities=ai_opportunities,
            solution_recommendations=recommendations,
            risks_and_objections=risks_and_objections,
            information_gaps=information_gaps,
            stakeholder_map=stakeholder_map,
        ),
        customer_context=fact_extraction.customer_context_draft.model_copy(deep=True),
        explicit_needs=_copy_list(explicit_needs),
        underlying_pains=_copy_list(underlying_pains),
        business_impacts=_copy_list(business_impacts),
        buying_intent=buying_intent.model_copy(deep=True),
        stakeholder_map=_copy_list(stakeholder_map),
        information_gaps=_copy_list(information_gaps),
        ai_opportunities=_copy_list(ai_opportunities),
        solution_recommendations=recommendations,
        risks_and_objections=_copy_list(risks_and_objections),
        deal_score=deal_score.model_copy(deep=True),
        next_best_actions=_copy_list(next_best_actions),
        customer_followup=_build_customer_followup(
            validated_case=validated_case,
            information_gaps=information_gaps,
            stakeholder_map=stakeholder_map,
            risks_and_objections=risks_and_objections,
            next_best_actions=next_best_actions,
        ),
        reliability_summary=_build_reliability_summary(
            fact_extraction=fact_extraction,
            context_sufficiency=context_sufficiency,
            explicit_needs=explicit_needs,
            underlying_pains=underlying_pains,
            business_impacts=business_impacts,
            ai_opportunities=ai_opportunities,
            risks_and_objections=risks_and_objections,
            deal_score=deal_score,
            information_gaps=information_gaps,
            stakeholder_map=stakeholder_map,
            solution_recommendations=recommendations,
        ),
        evaluation_flags=_build_evaluation_flags(
            context_sufficiency=context_sufficiency,
            fact_extraction=fact_extraction,
            stakeholder_map=stakeholder_map,
            information_gaps=information_gaps,
            risks_and_objections=risks_and_objections,
            solution_recommendations=recommendations,
        ),
    )
    return report


def _copy_list(values: Iterable[T]) -> list[T]:
    return [
        value.model_copy(deep=True) if hasattr(value, "model_copy") else value
        for value in values
    ]


def _build_executive_summary(
    *,
    buying_intent: BuyingIntent,
    deal_score: DealScore,
    explicit_needs: list[ExplicitNeed],
    business_impacts: list[BusinessImpact],
    ai_opportunities: list[AIOpportunity],
    solution_recommendations: list[SolutionRecommendation],
    risks_and_objections: list[Risk],
    information_gaps: list[InformationGap],
    stakeholder_map: list[Stakeholder],
) -> ExecutiveSummary:
    need_text = _join_limited([need.description for need in explicit_needs], limit=2)
    impact_text = _join_limited([impact.description for impact in business_impacts], limit=2)
    opportunity_text = ai_opportunities[0].name if ai_opportunities else "暂无可用AI机会"
    if solution_recommendations:
        recommendation_text = f"已形成候选方案：{solution_recommendations[0].solution_name}"
    else:
        recommendation_text = "当前未形成可推荐候选方案"
    risk_text = _primary_risk_text(risks_and_objections)
    gap_text = _join_limited([gap.description for gap in information_gaps], limit=2)
    confirmed_decision_maker = any(
        stakeholder.sales_role is SalesRole.decision_maker and stakeholder.confirmed
        for stakeholder in stakeholder_map
    )
    decision_text = "已确认决策人" if confirmed_decision_maker else "决策角色仍需确认"
    return ExecutiveSummary(
        opportunity_summary=(
            f"主要需求：{need_text}。主要影响：{impact_text}。"
        ),
        overall_intent=buying_intent.intent_level,
        current_stage=buying_intent.sales_stage,
        recommended_strategy=(
            f"以人工审核后的分步推进为主；Deal Score {deal_score.total_score}/100"
            f" 表示商机成熟度，不等于成交概率；{gap_text}。"
        ),
        primary_opportunity=f"{opportunity_text}；{recommendation_text}。",
        primary_risk=f"{risk_text}；{decision_text}。",
        confidence=deal_score.confidence,
    )


def _primary_risk_text(risks: list[Risk]) -> str:
    for severity in (
        SeverityLevel.critical,
        SeverityLevel.high,
        SeverityLevel.medium,
        SeverityLevel.low,
    ):
        for risk in risks:
            if risk.severity is severity:
                return risk.description
    return "暂无结构化风险"


def _build_customer_followup(
    *,
    validated_case: EvaluationCaseInput,
    information_gaps: list[InformationGap],
    stakeholder_map: list[Stakeholder],
    risks_and_objections: list[Risk],
    next_best_actions: list[NextBestAction],
) -> CustomerFollowUp:
    agenda = _dedupe(
        [gap.question_to_ask for gap in information_gaps[:3]]
        + [action.objective for action in next_best_actions[:2]]
    )
    if not agenda:
        agenda = ["确认下一次沟通的业务问题和所需材料"]
    materials = _dedupe(
        [item for action in next_best_actions[:2] for item in action.required_inputs]
        + ["人工审核后的会议摘要"]
    )
    review_claims = _dedupe(
        [
            stakeholder.next_validation
            for stakeholder in stakeholder_map
            if not stakeholder.confirmed and stakeholder.next_validation
        ]
        + [risk.mitigation for risk in risks_and_objections[:2]]
    )
    return CustomerFollowUp(
        internal_summary=(
            "报告草稿已由已校验节点结果确定性组装，客户发送前仍需人工审核。"
        ),
        customer_email_subject=f"{validated_case.case_id} 下一步澄清事项草稿",
        customer_email_body=(
            "感谢本次沟通。我们建议下一步先确认关键业务问题、参与角色和所需资料，"
            "再由双方共同判断后续验证范围。本邮件内容为草稿，需人工审核后使用。"
        ),
        next_meeting_agenda=agenda,
        materials_to_prepare=materials,
        claims_requiring_human_review=review_claims or ["报告草稿需人工审核后再对外使用"],
    )


def _build_reliability_summary(
    *,
    fact_extraction: FactExtractionResult,
    context_sufficiency: ContextSufficiencyResult,
    explicit_needs: list[ExplicitNeed],
    underlying_pains: list[UnderlyingPain],
    business_impacts: list[BusinessImpact],
    ai_opportunities: list[AIOpportunity],
    risks_and_objections: list[Risk],
    deal_score: DealScore,
    information_gaps: list[InformationGap],
    stakeholder_map: list[Stakeholder],
    solution_recommendations: list[SolutionRecommendation],
) -> ReliabilitySummary:
    claims = (
        [fact.claim_type for fact in fact_extraction.facts]
        + [need.claim_type for need in explicit_needs]
        + [pain.claim_type for pain in underlying_pains]
        + [impact.claim_type for impact in business_impacts]
        + [opportunity.claim_type for opportunity in ai_opportunities]
        + [risk.claim_type for risk in risks_and_objections]
    )
    critical_gap_count = sum(
        1 for gap in information_gaps if gap.priority is SeverityLevel.critical
    )
    unconfirmed_stakeholders = [
        stakeholder for stakeholder in stakeholder_map if not stakeholder.confirmed
    ]
    if (
        context_sufficiency.context_quality is ContextQuality.sufficient
        and deal_score.confidence is ConfidenceLevel.high
    ):
        confidence = ConfidenceLevel.high
    elif (
        context_sufficiency.context_quality is ContextQuality.insufficient
        or critical_gap_count > 0
        or len(unconfirmed_stakeholders) >= 2
    ):
        confidence = ConfidenceLevel.low
    else:
        confidence = ConfidenceLevel.medium
    recommendation_rate = _knowledge_grounded_rate(solution_recommendations)
    reasons = ["MVP报告草稿必须经过人工审核"]
    if fact_extraction.unknown_fields:
        reasons.append(f"仍存在未知字段：{', '.join(fact_extraction.unknown_fields[:3])}")
    if unconfirmed_stakeholders:
        reasons.append("存在未确认干系人或决策角色")
    if not solution_recommendations:
        reasons.append("当前没有结构化方案推荐")
    return ReliabilitySummary(
        overall_confidence=confidence,
        fact_count=sum(1 for claim in claims if claim is ClaimType.fact),
        inference_count=sum(1 for claim in claims if claim is ClaimType.inference),
        assumption_count=sum(1 for claim in claims if claim is ClaimType.assumption),
        unknown_count=sum(1 for claim in claims if claim is ClaimType.unknown)
        + len(fact_extraction.unknown_fields),
        unsupported_claim_count=0,
        knowledge_grounded_recommendation_rate=recommendation_rate,
        critical_information_gap_count=critical_gap_count,
        human_review_required=True,
        human_review_reasons=_dedupe(reasons),
    )


def _knowledge_grounded_rate(recommendations: list[SolutionRecommendation]) -> float:
    if not recommendations:
        return 0.0
    grounded = 0
    for recommendation in recommendations:
        if any(
            reference.source_type is EvidenceSourceType.solution_library
            for reference in recommendation.knowledge_references
        ):
            grounded += 1
    return grounded / len(recommendations)


def _build_evaluation_flags(
    *,
    context_sufficiency: ContextSufficiencyResult,
    fact_extraction: FactExtractionResult,
    stakeholder_map: list[Stakeholder],
    information_gaps: list[InformationGap],
    risks_and_objections: list[Risk],
    solution_recommendations: list[SolutionRecommendation],
) -> list[EvaluationFlag]:
    flags = [
        EvaluationFlag(
            flag=EvaluationFlagType.human_review_required,
            severity=SeverityLevel.medium,
            description="报告草稿在对外使用前必须经过人工审核。",
            affected_fields=["customer_followup", "executive_summary"],
        )
    ]
    gap_categories = {gap.category for gap in information_gaps}
    unknown_fields = set(fact_extraction.unknown_fields)
    if "budget" in unknown_fields or InformationGapCategory.budget in gap_categories:
        flags.append(
            EvaluationFlag(
                flag=EvaluationFlagType.unknown_budget,
                severity=SeverityLevel.high,
                description="预算信息仍未确认。",
                affected_fields=["information_gaps", "deal_score"],
            )
        )
    if any(
        stakeholder.sales_role is SalesRole.decision_maker and not stakeholder.confirmed
        for stakeholder in stakeholder_map
    ) or InformationGapCategory.authority in gap_categories:
        flags.append(
            EvaluationFlag(
                flag=EvaluationFlagType.unknown_decision_maker,
                severity=SeverityLevel.high,
                description="决策角色仍未确认。",
                affected_fields=["stakeholder_map", "information_gaps"],
            )
        )
    if InformationGapCategory.timeline in gap_categories:
        flags.append(
            EvaluationFlag(
                flag=EvaluationFlagType.unknown_timeline,
                severity=SeverityLevel.medium,
                description="客户时间计划仍未确认。",
                affected_fields=["information_gaps"],
            )
        )
    if context_sufficiency.context_quality is not ContextQuality.sufficient:
        flags.append(
            EvaluationFlag(
                flag=EvaluationFlagType.low_context_quality,
                severity=SeverityLevel.medium,
                description="上下文仍不足以直接形成最终报告。",
                affected_fields=["reliability_summary", "information_gaps"],
            )
        )
    if not solution_recommendations:
        flags.append(
            EvaluationFlag(
                flag=EvaluationFlagType.solution_without_knowledge_reference,
                severity=SeverityLevel.medium,
                description="当前没有基于方案库引用的推荐。",
                affected_fields=["solution_recommendations"],
            )
        )
    if any(risk.severity in {SeverityLevel.critical, SeverityLevel.high} for risk in risks_and_objections):
        flags.append(
            EvaluationFlag(
                flag=EvaluationFlagType.human_review_required,
                severity=SeverityLevel.high,
                description="存在高等级风险，需要人工复核。",
                affected_fields=["risks_and_objections", "next_best_actions"],
            )
        )
    return flags


def _join_limited(values: list[str], *, limit: int) -> str:
    selected = [value for value in values if value][:limit]
    return "；".join(selected) if selected else "暂无结构化信息"


def _dedupe(values: Iterable[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            continue
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
