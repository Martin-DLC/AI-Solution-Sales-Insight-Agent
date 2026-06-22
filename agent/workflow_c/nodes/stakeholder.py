from __future__ import annotations

import json
from typing import Any

from agent.workflow_c.contracts import NodeContract, NodeFailurePolicy
from agent.workflow_c.evidence_validation import has_verified_support, validate_evidence_references
from agent.workflow_c.failures import NodeBusinessRuleError, NodeJSONParseError
from agent.workflow_c.node_outputs import StakeholderNodeOutput
from agent.workflow_c.prompt_loader import render_stakeholder_messages
from agent.workflow_c.state import (
    FactExtractionResult,
    NodeValidationIssue,
    SourceIndexResult,
    WorkflowNodeName,
)
from schemas import EvaluationCaseInput
from schemas.common_models import EvidenceSourceType, SalesRole
from schemas.insight_models import BuyingIntent, Stakeholder


_CUSTOMER_VERIFIED_SOURCES = {
    EvidenceSourceType.customer_profile,
    EvidenceSourceType.meeting_transcript,
}

_FORBIDDEN_SOURCES = {
    EvidenceSourceType.solution_library,
    EvidenceSourceType.reference_case,
}

_CONFIRMED_ROLE_REQUIRING_CUSTOMER_EVIDENCE = {
    SalesRole.champion,
    SalesRole.decision_maker,
    SalesRole.budget_owner,
    SalesRole.business_owner,
}


class StakeholderNode:
    contract = NodeContract(
        name=WorkflowNodeName.stakeholder,
        required_state_fields=(
            "validated_case",
            "source_index",
            "fact_extraction",
            "buying_intent",
        ),
        produced_state_fields=("stakeholder_map",),
        output_model=StakeholderNodeOutput,
        failure_policy=NodeFailurePolicy.require_human_review,
        prompt_version="stakeholder_v1",
    )

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        case: EvaluationCaseInput = state["validated_case"]
        source_index: SourceIndexResult = state["source_index"]
        fact_extraction: FactExtractionResult = state["fact_extraction"]
        buying_intent: BuyingIntent = state["buying_intent"]
        messages = render_stakeholder_messages(
            source_index,
            fact_extraction,
            buying_intent,
            case.meeting.participants,
        )
        result = services.llm.complete_json_for_node(WorkflowNodeName.stakeholder, messages)
        parsed = result.parsed_json
        if parsed is None:
            try:
                parsed = json.loads(result.content)
            except json.JSONDecodeError as exc:
                raise NodeJSONParseError(
                    message="Stakeholder analysis returned invalid JSON.",
                    content_length=len(result.content),
                    position=exc.pos,
                ) from exc

        output = StakeholderNodeOutput.model_validate(parsed)
        _validate_stakeholder_rules(output.stakeholder_map, source_index)
        return {"stakeholder_map": output.stakeholder_map}


def _validate_stakeholder_rules(
    stakeholder_map: list[Stakeholder],
    source_index: SourceIndexResult,
) -> None:
    issues: list[NodeValidationIssue] = []
    for index, stakeholder in enumerate(stakeholder_map):
        if not stakeholder.confirmed:
            if stakeholder.next_validation is None or len(stakeholder.next_validation.strip()) < 8:
                issues.append(
                    NodeValidationIssue(
                        location=f"stakeholder_map.{index}.next_validation",
                        error_type="business_rule",
                        message="Unconfirmed stakeholders must include a next_validation of at least 8 characters.",
                    )
                )
            continue

        issues.extend(
            validate_evidence_references(
                node_name=WorkflowNodeName.stakeholder,
                field_prefix=f"stakeholder_map.{index}.evidence",
                evidence=stakeholder.evidence,
                source_index=source_index,
                forbidden_source_types=_FORBIDDEN_SOURCES,
                require_verified_support=True,
                allowed_verified_source_types=_CUSTOMER_VERIFIED_SOURCES,
            )
        )
        if stakeholder.sales_role in _CONFIRMED_ROLE_REQUIRING_CUSTOMER_EVIDENCE:
            if not has_verified_support(
                stakeholder.evidence,
                source_index,
                allowed_source_types=_CUSTOMER_VERIFIED_SOURCES,
            ):
                issues.append(
                    NodeValidationIssue(
                        location=f"stakeholder_map.{index}.evidence",
                        error_type="business_rule",
                        message=(
                            "Confirmed champion, decision maker, budget owner, or business owner "
                            "must have verified customer profile or meeting evidence."
                        ),
                    )
                )
    if issues:
        raise NodeBusinessRuleError(
            node_name=WorkflowNodeName.stakeholder,
            message="Stakeholder evidence failed business validation.",
            issues=issues,
        )
