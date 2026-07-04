from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from schemas.common_models import StrictBaseModel


class SolutionInsightRequest(StrictBaseModel):
    user_query: str
    industry: str | None = None
    company_size: str | None = None
    current_systems: list[str] = Field(default_factory=list)
    target_goal: str | None = None
    constraints: list[str] = Field(default_factory=list)
    enable_shadow_retrieval: bool = False

    @field_validator("current_systems", "constraints")
    @classmethod
    def deduplicate_lists(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            normalized = value.strip()
            if not normalized:
                continue
            if normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result


class SolutionInsightEvidenceItem(StrictBaseModel):
    title: str
    candidate_type: str
    document_id: str
    chunk_id: str | None = None
    citation_label: str
    content_excerpt: str
    runtime_eligible: bool
    rejection_reasons: list[str] = Field(default_factory=list)


class SolutionInsightRetrievalDebug(StrictBaseModel):
    retrieval_method: str
    formal_candidate_count: int
    evidence_count: int
    top_k: int
    query_hash: str
    blocked_retrieval_status: str
    selected_method: str | None = None
    selection_status: str | None = None


class SolutionInsightShadowDebug(StrictBaseModel):
    hierarchical_mode: str
    candidate_count: int
    document_candidate_count: int
    chunk_candidate_count: int
    runtime_eligible_count: int
    runtime_rejected_count: int
    rejection_reason_counts: dict[str, int] = Field(default_factory=dict)
    evidence_complete: bool
    fallback_recommended: bool
    fallback_reasons: list[str] = Field(default_factory=list)
    shadow_error: str | None = None


class SolutionInsightResponse(StrictBaseModel):
    request_id: str
    requirement_summary: str
    pain_points: list[str] = Field(default_factory=list)
    ai_opportunity_points: list[str] = Field(default_factory=list)
    proposed_solution: str
    evidence_items: list[SolutionInsightEvidenceItem] = Field(default_factory=list)
    evidence_completeness: str
    fallback_recommended: bool
    fallback_reasons: list[str] = Field(default_factory=list)
    human_confirmation_required: bool
    llm_mode: str
    retrieval_debug: SolutionInsightRetrievalDebug
    shadow_retrieval_debug: SolutionInsightShadowDebug | None = None
    response_note: str
    log_record: dict[str, Any] = Field(default_factory=dict)
