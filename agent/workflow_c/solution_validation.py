from __future__ import annotations

from agent.workflow_c.state import NodeValidationIssue, SourceIndexItem, SourceIndexResult
from schemas.common_models import EvidenceSourceType, OpportunitySuitability
from schemas.input_models import EvaluationCaseInput
from schemas.solution_models import AIOpportunity, SolutionRecommendation


_RECOMMENDABLE_SUITABILITY = {
    OpportunitySuitability.suitable_now,
    OpportunitySuitability.suitable_for_poc,
    OpportunitySuitability.suitable_after_prerequisites,
}


def normalize_identifier(value: str) -> str:
    return value.strip().casefold()


def validate_related_ids(
    *,
    field_prefix: str,
    referenced_ids: list[str],
    allowed_ids: set[str],
) -> list[NodeValidationIssue]:
    normalized_allowed = {normalize_identifier(value) for value in allowed_ids}
    issues: list[NodeValidationIssue] = []
    for index, value in enumerate(referenced_ids):
        if normalize_identifier(value) not in normalized_allowed:
            issues.append(
                NodeValidationIssue(
                    location=f"{field_prefix}.{index}",
                    error_type="business_rule",
                    message="Referenced ID must exist in the current workflow state.",
                    input_summary=value,
                )
            )
    return issues


def build_solution_catalog(
    case: EvaluationCaseInput,
    source_index: SourceIndexResult,
) -> dict[str, SourceIndexItem]:
    solution_items = [
        item
        for item in source_index.items
        if item.source_type is EvidenceSourceType.solution_library
    ]
    catalog = {item.content: item for item in solution_items}

    if set(catalog) != set(case.available_solution_library):
        return catalog
    return {
        solution: catalog[solution]
        for solution in case.available_solution_library
        if solution in catalog
    }


def validate_solution_catalog(
    case: EvaluationCaseInput,
    catalog: dict[str, SourceIndexItem],
) -> list[NodeValidationIssue]:
    issues: list[NodeValidationIssue] = []
    expected = list(case.available_solution_library)
    actual = list(catalog)
    if actual != expected:
        issues.append(
            NodeValidationIssue(
                location="solution_catalog",
                error_type="business_rule",
                message=(
                    "Solution catalog must match available_solution_library exactly "
                    "and preserve order."
                ),
                input_summary=f"expected={len(expected)}; actual={len(actual)}",
            )
        )
    return issues


def validate_solution_recommendation(
    *,
    recommendation: SolutionRecommendation,
    recommendation_index: int,
    solution_catalog: dict[str, SourceIndexItem],
    ai_opportunities: list[AIOpportunity],
) -> list[NodeValidationIssue]:
    issues: list[NodeValidationIssue] = []
    location = f"solution_recommendations.{recommendation_index}"
    opportunities_by_id = {
        opportunity.opportunity_id: opportunity
        for opportunity in ai_opportunities
    }
    opportunity_ids = set(opportunities_by_id)
    issues.extend(
        validate_related_ids(
            field_prefix=f"{location}.related_opportunity_ids",
            referenced_ids=recommendation.related_opportunity_ids,
            allowed_ids=opportunity_ids,
        )
    )

    catalog_item = solution_catalog.get(recommendation.solution_id)
    if catalog_item is None:
        issues.append(
            NodeValidationIssue(
                location=f"{location}.solution_id",
                error_type="business_rule",
                message="Solution recommendation must use a solution_id from available_solution_library.",
                input_summary="unmatched_solution_id",
            )
        )

    if not recommendation.knowledge_references:
        issues.append(
            NodeValidationIssue(
                location=f"{location}.knowledge_references",
                error_type="business_rule",
                message="Solution recommendation must include solution library knowledge references.",
            )
        )
    else:
        has_matching_solution_reference = False
        for reference_index, reference in enumerate(recommendation.knowledge_references):
            reference_location = f"{location}.knowledge_references.{reference_index}"
            if reference.source_type is not EvidenceSourceType.solution_library:
                issues.append(
                    NodeValidationIssue(
                        location=f"{reference_location}.source_type",
                        error_type="business_rule",
                        message="Knowledge references must use source_type=solution_library.",
                        input_summary=reference.source_type.value,
                    )
                )
                continue
            if catalog_item is None:
                continue
            if reference.source_id != catalog_item.source_id:
                issues.append(
                    NodeValidationIssue(
                        location=f"{reference_location}.source_id",
                        error_type="business_rule",
                        message="Knowledge reference source_id must match the recommended solution.",
                        input_summary=reference.source_id,
                    )
                )
                continue
            has_matching_solution_reference = True

        if catalog_item is not None and not has_matching_solution_reference:
            issues.append(
                NodeValidationIssue(
                    location=f"{location}.knowledge_references",
                    error_type="business_rule",
                    message="At least one knowledge reference must point to the recommended solution.",
                    input_summary=catalog_item.source_id,
                )
            )

    referenced_opportunities = [
        opportunities_by_id[opportunity_id]
        for opportunity_id in recommendation.related_opportunity_ids
        if opportunity_id in opportunities_by_id
    ]
    if referenced_opportunities and not any(
        opportunity.suitability in _RECOMMENDABLE_SUITABILITY
        for opportunity in referenced_opportunities
    ):
        issues.append(
            NodeValidationIssue(
                location=f"{location}.related_opportunity_ids",
                error_type="business_rule",
                message=(
                    "Solution recommendations must reference at least one AI opportunity "
                    "that is eligible for recommendation."
                ),
            )
        )
    return issues


def opportunity_allows_recommendation(opportunity: AIOpportunity) -> bool:
    return opportunity.suitability in _RECOMMENDABLE_SUITABILITY
