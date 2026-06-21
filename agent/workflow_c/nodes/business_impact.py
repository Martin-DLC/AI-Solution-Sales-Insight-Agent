from __future__ import annotations

import json
from typing import Any

from agent.workflow_c.contracts import NodeContract, NodeFailurePolicy
from agent.workflow_c.evidence_validation import validate_evidence_references
from agent.workflow_c.failures import NodeBusinessRuleError, NodeJSONParseError
from agent.workflow_c.node_outputs import BusinessImpactNodeOutput
from agent.workflow_c.prompt_loader import render_business_impact_messages
from agent.workflow_c.state import (
    FactExtractionResult,
    NodeValidationIssue,
    SourceIndexResult,
    WorkflowNodeName,
)
from schemas.common_models import ClaimType, EvidenceSourceType
from schemas.insight_models import BusinessImpact, ExplicitNeed, UnderlyingPain


_ALLOWED_VERIFIED_SUPPORT = {
    EvidenceSourceType.customer_profile,
    EvidenceSourceType.meeting_transcript,
    EvidenceSourceType.known_constraint,
}

_FORBIDDEN_SOURCES = {
    EvidenceSourceType.solution_library,
    EvidenceSourceType.reference_case,
}


class BusinessImpactNode:
    contract = NodeContract(
        name=WorkflowNodeName.business_impact,
        required_state_fields=(
            "source_index",
            "fact_extraction",
            "explicit_needs",
            "underlying_pains",
        ),
        produced_state_fields=("business_impacts",),
        output_model=BusinessImpactNodeOutput,
        failure_policy=NodeFailurePolicy.require_human_review,
        prompt_version="business_impact_v1",
    )

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        source_index: SourceIndexResult = state["source_index"]
        fact_extraction: FactExtractionResult = state["fact_extraction"]
        explicit_needs: list[ExplicitNeed] = state["explicit_needs"]
        underlying_pains: list[UnderlyingPain] = state["underlying_pains"]
        messages = render_business_impact_messages(
            source_index,
            fact_extraction,
            explicit_needs,
            underlying_pains,
        )
        result = services.llm.complete_json_for_node(WorkflowNodeName.business_impact, messages)
        parsed = result.parsed_json
        if parsed is None:
            try:
                parsed = json.loads(result.content)
            except json.JSONDecodeError as exc:
                raise NodeJSONParseError(
                    message="Business impact analysis returned invalid JSON.",
                    content_length=len(result.content),
                    position=exc.pos,
                ) from exc

        output = BusinessImpactNodeOutput.model_validate(parsed)
        _validate_business_impact_rules(output.business_impacts, source_index)
        return {"business_impacts": output.business_impacts}


def _validate_business_impact_rules(
    business_impacts: list[BusinessImpact],
    source_index: SourceIndexResult,
) -> None:
    issues: list[NodeValidationIssue] = []
    for index, impact in enumerate(business_impacts):
        if impact.claim_type is ClaimType.unknown:
            issues.append(
                NodeValidationIssue(
                    location=f"business_impacts.{index}.claim_type",
                    error_type="business_rule",
                    message="Business impact claim_type must not be unknown.",
                )
            )
        issues.extend(
            validate_evidence_references(
                node_name=WorkflowNodeName.business_impact,
                field_prefix=f"business_impacts.{index}.evidence",
                evidence=impact.evidence,
                source_index=source_index,
                forbidden_source_types=_FORBIDDEN_SOURCES,
                require_verified_support=True,
                allowed_verified_source_types=_ALLOWED_VERIFIED_SUPPORT,
            )
        )
    if issues:
        raise NodeBusinessRuleError(
            node_name=WorkflowNodeName.business_impact,
            message="Business impact evidence failed business validation.",
            issues=issues,
        )
