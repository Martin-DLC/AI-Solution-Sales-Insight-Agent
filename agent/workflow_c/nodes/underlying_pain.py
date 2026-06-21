from __future__ import annotations

import json
from typing import Any

from agent.workflow_c.contracts import NodeContract, NodeFailurePolicy
from agent.workflow_c.evidence_validation import validate_evidence_references
from agent.workflow_c.failures import NodeBusinessRuleError, NodeJSONParseError
from agent.workflow_c.node_outputs import UnderlyingPainNodeOutput
from agent.workflow_c.prompt_loader import render_underlying_pain_messages
from agent.workflow_c.state import (
    FactExtractionResult,
    SourceIndexResult,
    WorkflowNodeName,
)
from schemas.common_models import EvidenceSourceType
from schemas.insight_models import ExplicitNeed, UnderlyingPain


_ALLOWED_VERIFIED_SUPPORT = {
    EvidenceSourceType.customer_profile,
    EvidenceSourceType.meeting_transcript,
    EvidenceSourceType.known_constraint,
}

_FORBIDDEN_SOURCES = {
    EvidenceSourceType.solution_library,
    EvidenceSourceType.reference_case,
}


class UnderlyingPainNode:
    contract = NodeContract(
        name=WorkflowNodeName.underlying_pain,
        required_state_fields=("source_index", "fact_extraction", "explicit_needs"),
        produced_state_fields=("underlying_pains",),
        output_model=UnderlyingPainNodeOutput,
        failure_policy=NodeFailurePolicy.require_human_review,
        prompt_version="underlying_pain_v1",
    )

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        source_index: SourceIndexResult = state["source_index"]
        fact_extraction: FactExtractionResult = state["fact_extraction"]
        explicit_needs: list[ExplicitNeed] = state["explicit_needs"]
        messages = render_underlying_pain_messages(
            source_index,
            fact_extraction,
            explicit_needs,
        )
        result = services.llm.complete_json_for_node(WorkflowNodeName.underlying_pain, messages)
        parsed = result.parsed_json
        if parsed is None:
            try:
                parsed = json.loads(result.content)
            except json.JSONDecodeError as exc:
                raise NodeJSONParseError(
                    message="Underlying pain extraction returned invalid JSON.",
                    content_length=len(result.content),
                    position=exc.pos,
                ) from exc

        output = UnderlyingPainNodeOutput.model_validate(parsed)
        _validate_underlying_pain_evidence(output.underlying_pains, source_index)
        return {"underlying_pains": output.underlying_pains}


def _validate_underlying_pain_evidence(
    underlying_pains: list[UnderlyingPain],
    source_index: SourceIndexResult,
) -> None:
    issues = []
    for index, pain in enumerate(underlying_pains):
        issues.extend(
            validate_evidence_references(
                node_name=WorkflowNodeName.underlying_pain,
                field_prefix=f"underlying_pains.{index}.evidence",
                evidence=pain.evidence,
                source_index=source_index,
                forbidden_source_types=_FORBIDDEN_SOURCES,
                require_verified_support=True,
                allowed_verified_source_types=_ALLOWED_VERIFIED_SUPPORT,
            )
        )
    if issues:
        raise NodeBusinessRuleError(
            node_name=WorkflowNodeName.underlying_pain,
            message="Underlying pain evidence failed business validation.",
            issues=issues,
        )
