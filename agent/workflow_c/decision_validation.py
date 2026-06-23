from __future__ import annotations

from agent.workflow_c.decision_models import ActionTrace, RiskTrace, WorkflowActionType
from agent.workflow_c.solution_validation import validate_related_ids
from agent.workflow_c.state import NodeValidationIssue, SourceIndexResult
from schemas.common_models import (
    ActionPriority,
    DealScoreLevel,
    EvidenceSourceType,
    InformationGapCategory,
    SalesRole,
    SalesStage,
    SeverityLevel,
)
from schemas.decision_models import DealScore, NextBestAction
from schemas.insight_models import BuyingIntent, InformationGap, Stakeholder
from schemas.solution_models import AIOpportunity, Risk


_BLOCKING_GAP_CATEGORIES = {
    InformationGapCategory.budget,
    InformationGapCategory.authority,
    InformationGapCategory.decision_process,
}
_HIGH_SEVERITIES = {SeverityLevel.critical, SeverityLevel.high}
_BLOCKED_EARLY_ACTION_TYPES = {
    WorkflowActionType.commercial_proposal,
    WorkflowActionType.procurement,
    WorkflowActionType.contracting,
}
_LOW_SCORE_ALLOWED_P0_TYPES = {
    WorkflowActionType.clarification,
    WorkflowActionType.qualification,
    WorkflowActionType.stakeholder_alignment,
    WorkflowActionType.technical_validation,
}
_VAGUE_ACTIONS = {
    "持续跟进",
    "加强沟通",
    "保持联系",
    "保持沟通",
    "后续确认",
    "follow up",
    "keep in touch",
}


def validate_related_gap_ids(
    *,
    field_prefix: str,
    referenced_ids: list[str],
    information_gaps: list[InformationGap],
) -> list[NodeValidationIssue]:
    return validate_related_ids(
        field_prefix=field_prefix,
        referenced_ids=referenced_ids,
        allowed_ids={gap.gap_id for gap in information_gaps},
    )


def validate_related_risk_ids(
    *,
    field_prefix: str,
    referenced_ids: list[str],
    risks_and_objections: list[Risk],
) -> list[NodeValidationIssue]:
    allowed_ids = {risk.risk_id.casefold() for risk in risks_and_objections}
    issues: list[NodeValidationIssue] = []
    for index, value in enumerate(referenced_ids):
        if value.casefold() not in allowed_ids:
            issues.append(
                NodeValidationIssue(
                    location=f"{field_prefix}.{index}",
                    error_type="business_rule",
                    message="Referenced risk ID must exist in the current workflow state.",
                    input_summary="unknown_risk_id",
                )
            )
    return issues


def validate_related_opportunity_ids(
    *,
    field_prefix: str,
    referenced_ids: list[str],
    ai_opportunities: list[AIOpportunity],
) -> list[NodeValidationIssue]:
    return validate_related_ids(
        field_prefix=field_prefix,
        referenced_ids=referenced_ids,
        allowed_ids={opportunity.opportunity_id for opportunity in ai_opportunities},
    )


def validate_risk_traces(
    *,
    risk_traces: list[RiskTrace],
    risks_and_objections: list[Risk],
    information_gaps: list[InformationGap],
    ai_opportunities: list[AIOpportunity],
) -> list[NodeValidationIssue]:
    issues: list[NodeValidationIssue] = []
    risk_ids = {risk.risk_id for risk in risks_and_objections}
    for index, trace in enumerate(risk_traces):
        if trace.risk_id not in risk_ids:
            issues.append(
                NodeValidationIssue(
                    location=f"risk_traces.{index}.risk_id",
                    error_type="business_rule",
                    message="Risk trace must reference an existing risk_id.",
                    input_summary=trace.risk_id,
                )
            )
        issues.extend(
            validate_related_gap_ids(
                field_prefix=f"risk_traces.{index}.related_gap_ids",
                referenced_ids=trace.related_gap_ids,
                information_gaps=information_gaps,
            )
        )
        issues.extend(
            validate_related_opportunity_ids(
                field_prefix=f"risk_traces.{index}.related_opportunity_ids",
                referenced_ids=trace.related_opportunity_ids,
                ai_opportunities=ai_opportunities,
            )
        )
    return issues


def validate_risk_evidence(
    *,
    risks_and_objections: list[Risk],
    source_index: SourceIndexResult,
) -> list[NodeValidationIssue]:
    issues: list[NodeValidationIssue] = []
    sources = {item.source_id: item.source_type for item in source_index.items}
    for risk_index, risk in enumerate(risks_and_objections):
        for evidence_index, evidence in enumerate(risk.evidence):
            location = f"risks_and_objections.{risk_index}.evidence.{evidence_index}"
            expected_type = sources.get(evidence.source_id)
            if expected_type is None:
                issues.append(
                    NodeValidationIssue(
                        location=f"{location}.source_id",
                        error_type="business_rule",
                        message="Risk evidence must reference an existing source index item.",
                        input_summary=evidence.source_id,
                    )
                )
            elif evidence.source_type is not expected_type:
                issues.append(
                    NodeValidationIssue(
                        location=f"{location}.source_type",
                        error_type="business_rule",
                        message="Risk evidence source_type must match the source index.",
                        input_summary=evidence.source_type.value,
                    )
                )
            if evidence.source_type is EvidenceSourceType.reference_case:
                issues.append(
                    NodeValidationIssue(
                        location=f"{location}.source_type",
                        error_type="business_rule",
                        message="Workflow C risk evidence must not use hidden reference case data.",
                    )
                )
    return issues


def validate_action_traces(
    *,
    action_traces: list[ActionTrace],
    next_best_actions: list[NextBestAction],
    risks_and_objections: list[Risk],
) -> list[NodeValidationIssue]:
    issues: list[NodeValidationIssue] = []
    action_ids = {action.action_id for action in next_best_actions}
    for index, trace in enumerate(action_traces):
        if trace.action_id not in action_ids:
            issues.append(
                NodeValidationIssue(
                    location=f"action_traces.{index}.action_id",
                    error_type="business_rule",
                    message="Action trace must reference an existing action_id.",
                    input_summary=trace.action_id,
                )
            )
        issues.extend(
            validate_related_risk_ids(
                field_prefix=f"action_traces.{index}.related_risk_ids",
                referenced_ids=trace.related_risk_ids,
                risks_and_objections=risks_and_objections,
            )
        )
    return issues


def validate_p0_action_grounding(
    *,
    action: NextBestAction,
    action_trace: ActionTrace,
    information_gaps: list[InformationGap],
    risks_and_objections: list[Risk],
) -> list[NodeValidationIssue]:
    if action.priority is not ActionPriority.P0:
        return []
    high_gap_ids = {
        gap.gap_id for gap in information_gaps if gap.priority in _HIGH_SEVERITIES
    }
    high_risk_ids = {
        risk.risk_id for risk in risks_and_objections if risk.severity in _HIGH_SEVERITIES
    }
    if set(action.related_gap_ids) & high_gap_ids:
        return []
    if set(action_trace.related_risk_ids) & high_risk_ids:
        return []
    return [
        NodeValidationIssue(
            location=f"next_best_actions.{action.action_id}.priority",
            error_type="business_rule",
            message="P0 actions must be grounded by a high or critical gap or risk.",
            input_summary=action.action_id,
        )
    ]


def validate_action_stage_compatibility(
    *,
    action: NextBestAction,
    action_trace: ActionTrace,
    buying_intent: BuyingIntent,
    deal_score: DealScore,
    information_gaps: list[InformationGap],
    stakeholder_map: list[Stakeholder],
) -> list[NodeValidationIssue]:
    issues: list[NodeValidationIssue] = []
    blocking_gap_exists = any(
        gap.priority in _HIGH_SEVERITIES and gap.category in _BLOCKING_GAP_CATEGORIES
        for gap in information_gaps
    )
    if (
        action.priority is ActionPriority.P0
        and buying_intent.sales_stage in {SalesStage.discovery, SalesStage.unknown}
        and blocking_gap_exists
        and action_trace.action_type in _BLOCKED_EARLY_ACTION_TYPES
    ):
        issues.append(
            NodeValidationIssue(
                location=f"action_traces.{action.action_id}.action_type",
                error_type="business_rule",
                message=(
                    "Early-stage P0 actions must not be commercial, procurement, "
                    "or contracting actions while critical budget, authority, or "
                    "decision process gaps remain."
                ),
                input_summary=action_trace.action_type.value,
            )
        )

    has_confirmed_decision_role = any(
        stakeholder.confirmed
        and stakeholder.sales_role in {SalesRole.decision_maker, SalesRole.budget_owner}
        for stakeholder in stakeholder_map
    )
    if (
        action.priority is ActionPriority.P0
        and not has_confirmed_decision_role
        and action_trace.action_type in _BLOCKED_EARLY_ACTION_TYPES
    ):
        issues.append(
            NodeValidationIssue(
                location=f"action_traces.{action.action_id}.action_type",
                error_type="business_rule",
                message=(
                    "P0 actions must not move to proposal, procurement, or contracting "
                    "before a decision maker or budget owner is confirmed."
                ),
                input_summary=action_trace.action_type.value,
            )
        )

    if (
        action.priority is ActionPriority.P0
        and deal_score.score_level in {DealScoreLevel.low, DealScoreLevel.very_low}
        and action_trace.action_type not in _LOW_SCORE_ALLOWED_P0_TYPES
    ):
        issues.append(
            NodeValidationIssue(
                location=f"action_traces.{action.action_id}.action_type",
                error_type="business_rule",
                message=(
                    "Low deal scores require P0 actions focused on clarification, "
                    "qualification, stakeholder alignment, or technical validation."
                ),
                input_summary=action_trace.action_type.value,
            )
        )
    return issues


def validate_action_quality(action: NextBestAction) -> list[NodeValidationIssue]:
    issues: list[NodeValidationIssue] = []
    if not action.required_participants:
        issues.append(
            NodeValidationIssue(
                location=f"next_best_actions.{action.action_id}.required_participants",
                error_type="business_rule",
                message="Next best actions must include required participants.",
            )
        )
    if not action.success_criteria:
        issues.append(
            NodeValidationIssue(
                location=f"next_best_actions.{action.action_id}.success_criteria",
                error_type="business_rule",
                message="Next best actions must include success criteria.",
            )
        )
    if not action.suggested_timeframe:
        issues.append(
            NodeValidationIssue(
                location=f"next_best_actions.{action.action_id}.suggested_timeframe",
                error_type="business_rule",
                message="Next best actions must include a suggested timeframe.",
            )
        )
    if len(action.action) < 8:
        issues.append(
            NodeValidationIssue(
                location=f"next_best_actions.{action.action_id}.action",
                error_type="business_rule",
                message="Next best action text must be specific and at least 8 characters.",
            )
        )
    if action.action.casefold() in _VAGUE_ACTIONS:
        issues.append(
            NodeValidationIssue(
                location=f"next_best_actions.{action.action_id}.action",
                error_type="business_rule",
                message="Next best action must not be a generic follow-up.",
                input_summary=action.action,
            )
        )
    return issues
