from __future__ import annotations

import json
from typing import Any

from agent.workflow_c.contracts import NodeContract, NodeFailurePolicy
from agent.workflow_c.failures import NodeBusinessRuleError, NodeJSONParseError
from agent.workflow_c.node_outputs import ExplicitNeedNodeOutput
from agent.workflow_c.prompt_loader import render_explicit_need_messages
from agent.workflow_c.state import (
    FactExtractionResult,
    NodeValidationIssue,
    SourceIndexItem,
    SourceIndexResult,
    WorkflowNodeName,
)
from schemas.common_models import EvidenceReference, EvidenceSourceType
from schemas.insight_models import ExplicitNeed


class ExplicitNeedNode:
    contract = NodeContract(
        name=WorkflowNodeName.explicit_need,
        required_state_fields=("source_index", "fact_extraction"),
        produced_state_fields=("explicit_needs",),
        output_model=ExplicitNeedNodeOutput,
        failure_policy=NodeFailurePolicy.require_human_review,
        prompt_version="explicit_need_v1",
    )

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        source_index: SourceIndexResult = state["source_index"]
        fact_extraction: FactExtractionResult = state["fact_extraction"]
        messages = render_explicit_need_messages(source_index, fact_extraction)
        result = services.llm.complete_json_for_node(WorkflowNodeName.explicit_need, messages)
        parsed = result.parsed_json
        if parsed is None:
            try:
                parsed = json.loads(result.content)
            except json.JSONDecodeError as exc:
                raise NodeJSONParseError(
                    message="Explicit need extraction returned invalid JSON.",
                    content_length=len(result.content),
                    position=exc.pos,
                ) from exc

        output = ExplicitNeedNodeOutput.model_validate(parsed)
        _validate_explicit_need_evidence(output.explicit_needs, source_index)
        return {"explicit_needs": output.explicit_needs}


def _validate_explicit_need_evidence(
    explicit_needs: list[ExplicitNeed],
    source_index: SourceIndexResult,
) -> None:
    sources = {item.source_id: item for item in source_index.items}
    issues: list[NodeValidationIssue] = []

    for need_index, need in enumerate(explicit_needs):
        evidence_items = _resolve_evidence(
            evidence=need.evidence,
            sources=sources,
            base_location=f"explicit_needs.{need_index}.evidence",
            issues=issues,
        )
        if any(item.source_type is EvidenceSourceType.solution_library for item in evidence_items):
            issues.append(
                NodeValidationIssue(
                    location=f"explicit_needs.{need_index}.evidence",
                    error_type="business_rule",
                    message="Solution library entries cannot support explicit customer needs.",
                )
            )
        has_customer_verified_source = any(
            item.verified
            and item.source_type
            in {
                EvidenceSourceType.customer_profile,
                EvidenceSourceType.meeting_transcript,
            }
            for item in evidence_items
        )
        if not has_customer_verified_source:
            issues.append(
                NodeValidationIssue(
                    location=f"explicit_needs.{need_index}.evidence",
                    error_type="business_rule",
                    message=(
                        "An explicit need must include at least one verified customer "
                        "profile or meeting transcript evidence reference."
                    ),
                )
            )

    if issues:
        raise NodeBusinessRuleError(
            node_name=WorkflowNodeName.explicit_need,
            message="Explicit need evidence failed business validation.",
            issues=issues,
        )


def _resolve_evidence(
    *,
    evidence: list[EvidenceReference],
    sources: dict[str, SourceIndexItem],
    base_location: str,
    issues: list[NodeValidationIssue],
) -> list[SourceIndexItem]:
    resolved: list[SourceIndexItem] = []
    for evidence_index, reference in enumerate(evidence):
        item = sources.get(reference.source_id)
        location = f"{base_location}.{evidence_index}"
        if item is None:
            issues.append(
                NodeValidationIssue(
                    location=f"{location}.source_id",
                    error_type="business_rule",
                    message="Evidence source_id must exist in the Source Index.",
                )
            )
            continue
        if item.source_type is not reference.source_type:
            issues.append(
                NodeValidationIssue(
                    location=f"{location}.source_type",
                    error_type="business_rule",
                    message="Evidence source_type must match the Source Index source type.",
                )
            )
            continue
        resolved.append(item)
    return resolved
