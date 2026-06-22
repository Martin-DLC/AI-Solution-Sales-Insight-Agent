from __future__ import annotations

import json
from typing import Any

from agent.workflow_c.contracts import NodeContract, NodeFailurePolicy
from agent.workflow_c.evidence_validation import validate_evidence_references
from agent.workflow_c.failures import NodeBusinessRuleError, NodeJSONParseError
from agent.workflow_c.node_outputs import AIOpportunityNodeOutput
from agent.workflow_c.prompt_loader import render_ai_opportunity_messages
from agent.workflow_c.solution_validation import validate_related_ids
from agent.workflow_c.state import (
    ContextSufficiencyResult,
    NodeValidationIssue,
    SourceIndexResult,
    WorkflowNodeName,
)
from schemas.common_models import ContextQuality, EvidenceSourceType, OpportunitySuitability
from schemas.input_models import EvaluationCaseInput
from schemas.insight_models import BusinessImpact, ExplicitNeed, InformationGap, UnderlyingPain
from schemas.solution_models import AIOpportunity


_FORBIDDEN_EVIDENCE_SOURCES = {
    EvidenceSourceType.solution_library,
    EvidenceSourceType.reference_case,
}

_CUSTOMER_VERIFIED_SOURCES = {
    EvidenceSourceType.customer_profile,
    EvidenceSourceType.meeting_transcript,
    EvidenceSourceType.known_constraint,
}


class AIOpportunityNode:
    contract = NodeContract(
        name=WorkflowNodeName.ai_opportunity,
        required_state_fields=(
            "validated_case",
            "source_index",
            "context_sufficiency",
            "explicit_needs",
            "underlying_pains",
            "business_impacts",
            "information_gaps",
        ),
        produced_state_fields=("ai_opportunities",),
        output_model=AIOpportunityNodeOutput,
        failure_policy=NodeFailurePolicy.require_human_review,
        prompt_version="ai_opportunity_v1",
    )

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        case: EvaluationCaseInput = state["validated_case"]
        source_index: SourceIndexResult = state["source_index"]
        context_sufficiency: ContextSufficiencyResult = state["context_sufficiency"]
        explicit_needs: list[ExplicitNeed] = state["explicit_needs"]
        underlying_pains: list[UnderlyingPain] = state["underlying_pains"]
        business_impacts: list[BusinessImpact] = state["business_impacts"]
        information_gaps: list[InformationGap] = state["information_gaps"]
        messages = render_ai_opportunity_messages(
            source_index,
            context_sufficiency,
            explicit_needs,
            underlying_pains,
            business_impacts,
            information_gaps,
            case.known_constraints,
        )
        result = services.llm.complete_json_for_node(
            WorkflowNodeName.ai_opportunity,
            messages,
        )
        parsed = result.parsed_json
        if parsed is None:
            try:
                parsed = json.loads(result.content)
            except json.JSONDecodeError as exc:
                raise NodeJSONParseError(
                    message="AI opportunity analysis returned invalid JSON.",
                    content_length=len(result.content),
                    position=exc.pos,
                ) from exc

        output = AIOpportunityNodeOutput.model_validate(parsed)
        _validate_ai_opportunity_rules(
            output.ai_opportunities,
            source_index,
            context_sufficiency,
            underlying_pains,
        )
        return {"ai_opportunities": output.ai_opportunities}


def _validate_ai_opportunity_rules(
    ai_opportunities: list[AIOpportunity],
    source_index: SourceIndexResult,
    context_sufficiency: ContextSufficiencyResult,
    underlying_pains: list[UnderlyingPain],
) -> None:
    issues: list[NodeValidationIssue] = []
    pain_ids = {pain.pain_id for pain in underlying_pains}
    if context_sufficiency.context_quality is ContextQuality.insufficient:
        issues.append(
            NodeValidationIssue(
                location="context_sufficiency.context_quality",
                error_type="business_rule",
                message="AI opportunity analysis cannot run with insufficient context.",
                input_summary=ContextQuality.insufficient.value,
            )
        )

    for index, opportunity in enumerate(ai_opportunities):
        prefix = f"ai_opportunities.{index}"
        issues.extend(
            validate_related_ids(
                field_prefix=f"{prefix}.related_pain_ids",
                referenced_ids=opportunity.related_pain_ids,
                allowed_ids=pain_ids,
            )
        )
        issues.extend(
            validate_evidence_references(
                node_name=WorkflowNodeName.ai_opportunity,
                field_prefix=f"{prefix}.evidence",
                evidence=opportunity.evidence,
                source_index=source_index,
                forbidden_source_types=_FORBIDDEN_EVIDENCE_SOURCES,
                require_verified_support=True,
                allowed_verified_source_types=_CUSTOMER_VERIFIED_SOURCES,
            )
        )
        if (
            context_sufficiency.context_quality is ContextQuality.partially_sufficient
            and opportunity.suitability is OpportunitySuitability.suitable_now
        ):
            issues.append(
                NodeValidationIssue(
                    location=f"{prefix}.suitability",
                    error_type="business_rule",
                    message="Partially sufficient context cannot produce suitable_now AI opportunities.",
                    input_summary=opportunity.suitability.value,
                )
            )

    if issues:
        raise NodeBusinessRuleError(
            node_name=WorkflowNodeName.ai_opportunity,
            message="AI opportunity analysis failed business validation.",
            issues=issues,
        )
