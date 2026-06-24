from __future__ import annotations

import json
from typing import Any

from agent.workflow_c.contracts import NodeContract, NodeFailurePolicy
from agent.workflow_c.failures import NodeBusinessRuleError, NodeJSONParseError
from agent.workflow_c.node_outputs import FactExtractionNodeOutput
from agent.workflow_c.prompt_loader import render_fact_extraction_messages
from agent.workflow_c.state import (
    FactExtractionResult,
    NodeValidationIssue,
    SourceIndexItem,
    SourceIndexResult,
    WorkflowNodeName,
)
from schemas.common_models import ClaimType, EvidenceReference, EvidenceSourceType


class FactExtractionNode:
    contract = NodeContract(
        name=WorkflowNodeName.fact_extraction,
        required_state_fields=("source_index",),
        produced_state_fields=("fact_extraction",),
        output_model=FactExtractionNodeOutput,
        failure_policy=NodeFailurePolicy.require_human_review,
        prompt_version="fact_extraction_v2",
    )

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        source_index: SourceIndexResult = state["source_index"]
        messages = render_fact_extraction_messages(source_index)
        result = services.llm.complete_json_for_node(WorkflowNodeName.fact_extraction, messages)
        parsed = result.parsed_json
        if parsed is None:
            try:
                parsed = json.loads(result.content)
            except json.JSONDecodeError as exc:
                raise NodeJSONParseError(
                    message="Fact extraction returned invalid JSON.",
                    content_length=len(result.content),
                    position=exc.pos,
                ) from exc

        output = FactExtractionNodeOutput.model_validate(parsed)
        _validate_fact_evidence(output.fact_extraction, source_index)
        return {"fact_extraction": output.fact_extraction}


def _validate_fact_evidence(
    fact_extraction: FactExtractionResult,
    source_index: SourceIndexResult,
) -> None:
    sources = {item.source_id: item for item in source_index.items}
    issues: list[NodeValidationIssue] = []

    for fact_index, fact in enumerate(fact_extraction.facts):
        evidence_items = _resolve_evidence(
            evidence=fact.evidence,
            sources=sources,
            base_location=f"fact_extraction.facts.{fact_index}.evidence",
            issues=issues,
        )
        if fact.claim_type is not ClaimType.fact:
            continue
        has_verified_fact_source = any(
            item.verified and item.source_type is not EvidenceSourceType.salesperson_note
            for item in evidence_items
        )
        if not has_verified_fact_source:
            issues.append(
                NodeValidationIssue(
                    location=f"fact_extraction.facts.{fact_index}.evidence",
                    error_type="business_rule",
                    message=(
                        "A confirmed fact must be supported by at least one verified "
                        "non-salesperson-note source."
                    ),
                )
            )

    if issues:
        raise NodeBusinessRuleError(
            node_name=WorkflowNodeName.fact_extraction,
            message="Fact extraction evidence failed business validation.",
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
