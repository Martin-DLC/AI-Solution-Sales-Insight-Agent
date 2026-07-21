from __future__ import annotations

from typing import Literal

from pydantic import Field

from schemas.common_models import StrictBaseModel


class ObservationInputSummary(StrictBaseModel):
    user_query_preview: str
    llm_mode: str
    company_id_present: bool
    shadow_requested: bool
    enterprise_context_present: bool


class ObservationFormalPath(StrictBaseModel):
    formal_candidate_count: int
    evidence_count: int
    evidence_titles: list[str] = Field(default_factory=list)
    retrieval_debug_summary: dict[str, object] = Field(default_factory=dict)


class ObservationShadowPath(StrictBaseModel):
    shadow_enabled: bool
    shadow_candidate_count: int = 0
    document_candidate_count: int = 0
    chunk_candidate_count: int = 0
    runtime_eligible_count: int = 0
    runtime_rejected_count: int = 0
    shadow_error: str | None = None


class ObservationSkills(StrictBaseModel):
    executed_skills: list[str] = Field(default_factory=list)
    skill_count: int = 0
    failed_skill_count: int = 0
    total_elapsed_ms: int = 0
    warnings: list[str] = Field(default_factory=list)


class ObservationProviders(StrictBaseModel):
    provider_success_count: int = 0
    provider_failed_count: int = 0
    provider_skipped_count: int = 0
    provider_warnings: list[str] = Field(default_factory=list)
    provider_names: list[str] = Field(default_factory=list)
    mock_data: bool = True
    context_source: str | None = None


class ObservationFallback(StrictBaseModel):
    fallback_recommended: bool
    fallback_reasons: list[str] = Field(default_factory=list)
    human_confirmation_required: bool
    evidence_completeness: str


class ObservationOutputSummary(StrictBaseModel):
    requirement_summary: str
    pain_point_count: int = 0
    opportunity_count: int = 0
    proposed_solution_preview: str


class ObservationSafetyNotes(StrictBaseModel):
    boundary_status: str
    shadow_does_not_affect_formal_answer: bool = True
    deterministic_or_llm_mode: str


class ObservationGovernance(StrictBaseModel):
    run_id: str | None = None
    trace_id: str | None = None
    event_count: int = 0
    final_runtime_status: str | None = None
    stopped_by_policy: bool = False
    stop_reason: str | None = None
    human_review_required: bool = False
    fallback_triggered: bool = False


class ObservationSnapshot(StrictBaseModel):
    request_id: str
    generated_at: str
    input_summary: ObservationInputSummary
    formal_path: ObservationFormalPath
    shadow_path: ObservationShadowPath
    skills: ObservationSkills
    providers: ObservationProviders
    fallback: ObservationFallback
    output_summary: ObservationOutputSummary
    safety_notes: ObservationSafetyNotes
    governance: ObservationGovernance = Field(default_factory=ObservationGovernance)


ObservationMode = Literal["deterministic", "llm", "auto"]
