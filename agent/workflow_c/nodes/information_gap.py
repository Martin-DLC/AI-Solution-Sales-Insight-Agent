from __future__ import annotations

import json
from typing import Any

from agent.workflow_c.contracts import NodeContract, NodeFailurePolicy
from agent.workflow_c.failures import NodeBusinessRuleError, NodeJSONParseError
from agent.workflow_c.node_outputs import InformationGapNodeOutput
from agent.workflow_c.prompt_loader import render_information_gap_messages
from agent.workflow_c.state import (
    AnalysisMode,
    ContextSufficiencyResult,
    FactExtractionResult,
    NodeValidationIssue,
    SourceIndexResult,
    WorkflowNodeName,
)
from schemas.common_models import InformationGapCategory, SalesRole, SeverityLevel
from schemas.insight_models import (
    BusinessImpact,
    BuyingIntent,
    ExplicitNeed,
    InformationGap,
    Stakeholder,
    UnderlyingPain,
)


CONTEXT_CATEGORY_TO_GAP_CATEGORIES: dict[str, set[InformationGapCategory]] = {
    "business_goal": {InformationGapCategory.business_goal},
    "current_process": {InformationGapCategory.delivery_readiness},
    "pain_or_problem": {InformationGapCategory.current_metrics},
    "stakeholders": {
        InformationGapCategory.authority,
        InformationGapCategory.decision_process,
    },
    "budget": {InformationGapCategory.budget},
    "timeline": {InformationGapCategory.timeline},
    "data": {InformationGapCategory.data},
    "systems": {InformationGapCategory.integration},
    "security": {InformationGapCategory.security},
    "success_metrics": {InformationGapCategory.success_metrics},
}

_VAGUE_QUESTIONS = {
    "进一步了解",
    "持续沟通",
    "后续确认",
    "请补充信息",
    "follow up",
    "clarify",
}

_AUTHORITY_ROLES = {
    SalesRole.decision_maker,
    SalesRole.budget_owner,
    SalesRole.business_owner,
    SalesRole.champion_candidate,
}

_AUTHORITY_GAP_CATEGORIES = {
    InformationGapCategory.authority,
    InformationGapCategory.decision_process,
}


class InformationGapNode:
    contract = NodeContract(
        name=WorkflowNodeName.information_gap,
        required_state_fields=(
            "source_index",
            "context_sufficiency",
            "fact_extraction",
        ),
        produced_state_fields=("information_gaps",),
        output_model=InformationGapNodeOutput,
        failure_policy=NodeFailurePolicy.require_human_review,
        prompt_version="information_gap_v1",
    )

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        source_index: SourceIndexResult = state["source_index"]
        context_sufficiency: ContextSufficiencyResult = state["context_sufficiency"]
        fact_extraction: FactExtractionResult = state["fact_extraction"]
        messages = render_information_gap_messages(
            source_index,
            context_sufficiency,
            fact_extraction,
            explicit_needs=state.get("explicit_needs"),
            underlying_pains=state.get("underlying_pains"),
            business_impacts=state.get("business_impacts"),
            buying_intent=state.get("buying_intent"),
            stakeholder_map=state.get("stakeholder_map"),
        )
        result = services.llm.complete_json_for_node(
            WorkflowNodeName.information_gap,
            messages,
        )
        parsed = result.parsed_json
        if parsed is None:
            try:
                parsed = json.loads(result.content)
            except json.JSONDecodeError as exc:
                raise NodeJSONParseError(
                    message="Information gap analysis returned invalid JSON.",
                    content_length=len(result.content),
                    position=exc.pos,
                ) from exc

        output = InformationGapNodeOutput.model_validate(parsed)
        _validate_information_gap_rules(
            output.information_gaps,
            context_sufficiency,
            buying_intent=state.get("buying_intent"),
            stakeholder_map=state.get("stakeholder_map"),
        )
        return {"information_gaps": output.information_gaps}


def _validate_information_gap_rules(
    information_gaps: list[InformationGap],
    context_sufficiency: ContextSufficiencyResult,
    *,
    buying_intent: BuyingIntent | None = None,
    stakeholder_map: list[Stakeholder] | None = None,
) -> None:
    issues: list[NodeValidationIssue] = []
    gap_categories = {gap.category for gap in information_gaps}

    if context_sufficiency.analysis_mode is AnalysisMode.clarification_only:
        expected_categories = _expected_categories_for_blocking_gaps(
            context_sufficiency.blocking_gaps
        )
        if expected_categories and gap_categories.isdisjoint(expected_categories):
            issues.append(
                NodeValidationIssue(
                    location="information_gaps.category",
                    error_type="business_rule",
                    message=(
                        "Clarification-only analysis must include a gap category "
                        "that covers context blocking_gaps."
                    ),
                    input_summary=",".join(sorted(context_sufficiency.blocking_gaps)),
                )
            )

    if _has_unconfirmed_authority_role(stakeholder_map or []):
        if gap_categories.isdisjoint(_AUTHORITY_GAP_CATEGORIES):
            issues.append(
                NodeValidationIssue(
                    location="information_gaps.category",
                    error_type="business_rule",
                    message=(
                        "Unconfirmed decision, budget, business owner, or champion candidate "
                        "requires an authority or decision_process information gap."
                    ),
                )
            )

    if buying_intent is not None and buying_intent.unknown_factors and not information_gaps:
        issues.append(
            NodeValidationIssue(
                location="information_gaps",
                error_type="business_rule",
                message="Buying intent unknown factors require at least one information gap.",
            )
        )

    for index, gap in enumerate(information_gaps):
        question = _normalize_question(gap.question_to_ask)
        if len(question) < 8:
            issues.append(
                NodeValidationIssue(
                    location=f"information_gaps.{index}.question_to_ask",
                    error_type="business_rule",
                    message="Information gap question_to_ask must contain at least 8 characters.",
                )
            )
        if question in _VAGUE_QUESTIONS:
            issues.append(
                NodeValidationIssue(
                    location=f"information_gaps.{index}.question_to_ask",
                    error_type="business_rule",
                    message="Information gap question_to_ask must be specific and actionable.",
                    input_summary=gap.question_to_ask,
                )
            )
        if gap.priority in {SeverityLevel.critical, SeverityLevel.high}:
            if len("".join(gap.business_impact.split())) < 10:
                issues.append(
                    NodeValidationIssue(
                        location=f"information_gaps.{index}.business_impact",
                        error_type="business_rule",
                        message=(
                            "Critical or high priority information gaps must explain "
                            "deal or solution impact in at least 10 characters."
                        ),
                    )
                )

    if issues:
        raise NodeBusinessRuleError(
            node_name=WorkflowNodeName.information_gap,
            message="Information gap analysis failed business validation.",
            issues=issues,
        )


def _expected_categories_for_blocking_gaps(
    blocking_gaps: list[str],
) -> set[InformationGapCategory]:
    expected: set[InformationGapCategory] = set()
    for category in blocking_gaps:
        expected.update(CONTEXT_CATEGORY_TO_GAP_CATEGORIES.get(category, set()))
    return expected


def _has_unconfirmed_authority_role(stakeholder_map: list[Stakeholder]) -> bool:
    return any(
        not stakeholder.confirmed and stakeholder.sales_role in _AUTHORITY_ROLES
        for stakeholder in stakeholder_map
    )


def _normalize_question(value: str) -> str:
    stripped = "".join(value.split()).casefold()
    return stripped.rstrip("?？。.")
