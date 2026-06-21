from __future__ import annotations

from agent.workflow_c.state import (
    NodeValidationIssue,
    SourceIndexItem,
    SourceIndexResult,
    WorkflowNodeName,
)
from schemas.common_models import EvidenceReference, EvidenceSourceType


def build_source_index_map(
    source_index: SourceIndexResult,
) -> dict[str, SourceIndexItem]:
    return {item.source_id: item for item in source_index.items}


def validate_evidence_references(
    *,
    node_name: WorkflowNodeName,
    field_prefix: str,
    evidence: list[EvidenceReference],
    source_index: SourceIndexResult,
    forbidden_source_types: set[EvidenceSourceType] | None = None,
    require_verified_support: bool = True,
    allowed_verified_source_types: set[EvidenceSourceType] | None = None,
) -> list[NodeValidationIssue]:
    del node_name
    sources = build_source_index_map(source_index)
    forbidden = forbidden_source_types or set()
    issues: list[NodeValidationIssue] = []
    resolved: list[SourceIndexItem] = []

    for index, reference in enumerate(evidence):
        location = f"{field_prefix}.{index}"
        item = sources.get(reference.source_id)
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
                    input_summary=reference.source_type.value,
                )
            )
            continue
        if item.source_type in forbidden:
            issues.append(
                NodeValidationIssue(
                    location=f"{location}.source_type",
                    error_type="business_rule",
                    message=f"Evidence source_type {item.source_type.value} is not allowed here.",
                    input_summary=item.source_id,
                )
            )
            continue
        resolved.append(item)

    if require_verified_support:
        verified_items = [item for item in resolved if item.verified]
        if allowed_verified_source_types is not None:
            verified_items = [
                item
                for item in verified_items
                if item.source_type in allowed_verified_source_types
            ]
        if not verified_items:
            issues.append(
                NodeValidationIssue(
                    location=field_prefix,
                    error_type="business_rule",
                    message=(
                        "Evidence must include at least one verified source; "
                        "unverified salesperson notes can only be supporting context."
                    ),
                )
            )
    return issues
