from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from evaluation.retrieval.models import RetrievalQueryType
from knowledge_base.contracts_v2 import (
    KnowledgeChunkV2,
    KnowledgeDocumentV2,
    SolutionScopeType,
)
from schemas.common_models import StrictBaseModel


class RetrievalRuntimeContextV2(StrictBaseModel):
    operational_filters: dict[str, Any] = Field(default_factory=dict)
    operational_solution_scope: list[str] = Field(default_factory=list)
    allowed_document_types: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    effective_on: date | None = None

    @field_validator("operational_solution_scope", "allowed_document_types", "industries", "tags")
    @classmethod
    def deduplicate_lists(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if not value:
                raise ValueError("Runtime context lists cannot contain empty values.")
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result


class RetrievalEvaluationGoldV2(StrictBaseModel):
    expected_relevant_document_ids: list[str] = Field(default_factory=list)
    expected_relevant_chunk_ids: list[str] = Field(default_factory=list)
    forbidden_document_ids: list[str] = Field(default_factory=list)
    forbidden_solution_ids: list[str] = Field(default_factory=list)
    minimum_relevant_hits: int

    @field_validator(
        "expected_relevant_document_ids",
        "expected_relevant_chunk_ids",
        "forbidden_document_ids",
        "forbidden_solution_ids",
    )
    @classmethod
    def deduplicate_lists(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if not value:
                raise ValueError("Evaluation gold lists cannot contain empty values.")
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result

    @field_validator("minimum_relevant_hits")
    @classmethod
    def minimum_relevant_hits_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("minimum_relevant_hits must be greater than 0.")
        return value

    @model_validator(mode="after")
    def validate_gold(self) -> Self:
        if not (self.expected_relevant_document_ids or self.expected_relevant_chunk_ids):
            raise ValueError("Evaluation gold must define at least one expected document or chunk.")
        if len(set(self.forbidden_document_ids) & set(self.expected_relevant_document_ids)) > 0:
            raise ValueError("Expected relevant documents must not also appear in forbidden_document_ids.")
        return self


class RetrievalEvaluationCaseV2(StrictBaseModel):
    retrieval_case_id: str
    source_case_id: str
    query_type: RetrievalQueryType
    query: str
    runtime_context: RetrievalRuntimeContextV2
    evaluation_gold: RetrievalEvaluationGoldV2
    tags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("tags", "notes")
    @classmethod
    def deduplicate_lists(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if not value:
                raise ValueError("Retrieval case v2 lists cannot contain empty values.")
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result

    @model_validator(mode="after")
    def validate_case(self) -> Self:
        lowered = self.query.casefold()
        if "hidden reference" in lowered or "reference pack" in lowered:
            raise ValueError("Retrieval Benchmark v2 queries must not mention hidden reference material.")
        return self


class CandidateBoundaryDecisionV2(StrictBaseModel):
    candidate_allowed: bool
    reasons: list[str] = Field(default_factory=list)

    @field_validator("reasons")
    @classmethod
    def deduplicate_reasons(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result


class FeasibilityResult(StrictBaseModel):
    feasible: bool
    reasons: list[str] = Field(default_factory=list)
    safe_expected_item_count: int
    filtered_expected_item_count: int
    boundary_safe_expected_item_count: int

    @field_validator("safe_expected_item_count", "filtered_expected_item_count", "boundary_safe_expected_item_count")
    @classmethod
    def counts_must_be_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Feasibility counts must be zero or greater.")
        return value


def evaluate_candidate_boundary_v2(
    *,
    case: RetrievalEvaluationCaseV2,
    document: KnowledgeDocumentV2,
    chunk: KnowledgeChunkV2 | None = None,
) -> CandidateBoundaryDecisionV2:
    candidate = chunk or document
    applicable = set(candidate.applicable_solution_ids)
    excluded = set(candidate.excluded_solution_ids)
    operational_scope = set(case.runtime_context.operational_solution_scope)
    forbidden_scope = set(case.evaluation_gold.forbidden_solution_ids)
    reasons: list[str] = []

    if document.document_id in case.evaluation_gold.forbidden_document_ids:
        reasons.append("forbidden_document_id")

    if operational_scope and excluded & operational_scope:
        reasons.append("candidate_excludes_operational_scope")

    if candidate.scope_type is not SolutionScopeType.global_policy:
        if operational_scope and applicable.isdisjoint(operational_scope):
            reasons.append("candidate_outside_operational_scope")
        if forbidden_scope and applicable & forbidden_scope:
            reasons.append("candidate_overlaps_forbidden_solution_scope")

    return CandidateBoundaryDecisionV2(
        candidate_allowed=not reasons,
        reasons=reasons,
    )


def validate_retrieval_case_feasibility_v2(
    *,
    case: RetrievalEvaluationCaseV2,
    documents: list[KnowledgeDocumentV2],
    chunks: list[KnowledgeChunkV2],
    evaluation_date: date,
) -> FeasibilityResult:
    documents_by_id = {document.document_id: document for document in documents}
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    reasons: list[str] = []
    filtered_expected_item_count = 0
    boundary_safe_expected_item_count = 0
    conflicting_expected_item_count = 0

    expected_documents: list[KnowledgeDocumentV2] = []
    expected_chunk_pairs: list[tuple[KnowledgeDocumentV2, KnowledgeChunkV2]] = []

    for document_id in case.evaluation_gold.expected_relevant_document_ids:
        document = documents_by_id.get(document_id)
        if document is None:
            reasons.append("missing_expected_document")
            continue
        expected_documents.append(document)

    for chunk_id in case.evaluation_gold.expected_relevant_chunk_ids:
        chunk = chunks_by_id.get(chunk_id)
        if chunk is None:
            reasons.append("missing_expected_chunk")
            continue
        document = documents_by_id.get(chunk.document_id)
        if document is None:
            reasons.append("missing_chunk_parent_document")
            continue
        expected_chunk_pairs.append((document, chunk))

    for document in expected_documents:
        if _document_passes_runtime_filters(case=case, document=document, evaluation_date=evaluation_date):
            filtered_expected_item_count += 1
            decision = evaluate_candidate_boundary_v2(case=case, document=document)
            if decision.candidate_allowed:
                boundary_safe_expected_item_count += 1
            else:
                conflicting_expected_item_count += 1

    for document, chunk in expected_chunk_pairs:
        if _document_passes_runtime_filters(case=case, document=document, evaluation_date=evaluation_date):
            filtered_expected_item_count += 1
            decision = evaluate_candidate_boundary_v2(case=case, document=document, chunk=chunk)
            if decision.candidate_allowed:
                boundary_safe_expected_item_count += 1
            else:
                conflicting_expected_item_count += 1

    if filtered_expected_item_count == 0:
        reasons.append("operational_filters_exclude_all_expected_items")
    if conflicting_expected_item_count > 0:
        reasons.append("expected_relevant_items_conflict_with_boundary")
    if boundary_safe_expected_item_count < case.evaluation_gold.minimum_relevant_hits:
        reasons.append("minimum_relevant_hits_exceeds_safe_expected_items")

    return FeasibilityResult(
        feasible=not reasons,
        reasons=_deduplicate(reasons),
        safe_expected_item_count=boundary_safe_expected_item_count,
        filtered_expected_item_count=filtered_expected_item_count,
        boundary_safe_expected_item_count=boundary_safe_expected_item_count,
    )


def _document_passes_runtime_filters(
    *,
    case: RetrievalEvaluationCaseV2,
    document: KnowledgeDocumentV2,
    evaluation_date: date,
) -> bool:
    if not document.is_active(as_of=evaluation_date):
        return False
    if case.runtime_context.allowed_document_types:
        allowed = {item for item in case.runtime_context.allowed_document_types}
        if document.document_type.value not in allowed:
            return False
    if case.runtime_context.industries:
        if set(document.industries).isdisjoint(set(case.runtime_context.industries)):
            return False
    if case.runtime_context.tags:
        if set(document.tags).isdisjoint(set(case.runtime_context.tags)):
            return False
    return True


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
