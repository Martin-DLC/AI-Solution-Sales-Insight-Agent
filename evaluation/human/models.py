from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from schemas.common_models import StrictBaseModel


class SolutionInsightHumanEvalPacket(StrictBaseModel):
    case_id: str
    user_query_summary: str
    industry: str | None = None
    company_size: str | None = None
    target_goal: str | None = None
    constraints: list[str] = Field(default_factory=list)
    expected_focus_areas: list[str] = Field(default_factory=list)
    expected_fallback_behavior: bool
    response_summary: str
    pain_points: list[str] = Field(default_factory=list)
    ai_opportunity_points: list[str] = Field(default_factory=list)
    proposed_solution: str
    evidence_count: int
    evidence_titles: list[str] = Field(default_factory=list)
    fallback_recommended: bool
    fallback_reasons: list[str] = Field(default_factory=list)
    human_confirmation_required: bool
    skill_trace_summary: dict[str, object] = Field(default_factory=dict)
    provider_trace_summary: dict[str, object] = Field(default_factory=dict)
    observability_available: bool
    review_instructions: str


class SolutionInsightHumanAnnotation(StrictBaseModel):
    case_id: str
    reviewer_id: str | None = None
    reviewed_at: str | None = None
    business_relevance_score: int | None = Field(default=None, ge=1, le=5)
    evidence_grounding_score: int | None = Field(default=None, ge=1, le=5)
    risk_fallback_score: int | None = Field(default=None, ge=1, le=5)
    actionability_score: int | None = Field(default=None, ge=1, le=5)
    communication_quality_score: int | None = Field(default=None, ge=1, le=5)
    product_thinking_score: int | None = Field(default=None, ge=1, le=5)
    overall_human_score: float | None = None
    pass_fail: Literal["pass", "fail"] | None = None
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    suggested_improvements: list[str] = Field(default_factory=list)
    reviewer_notes: str | None = None

    @field_validator("strengths", "weaknesses", "suggested_improvements")
    @classmethod
    def clean_string_lists(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(normalized)
        return cleaned

    @model_validator(mode="after")
    def validate_annotation_consistency(self) -> "SolutionInsightHumanAnnotation":
        scores = [
            self.business_relevance_score,
            self.evidence_grounding_score,
            self.risk_fallback_score,
            self.actionability_score,
            self.communication_quality_score,
            self.product_thinking_score,
        ]
        completed_scores = [score for score in scores if score is not None]
        if completed_scores and len(completed_scores) != 6:
            raise ValueError("Either all six human scores must be provided, or all must remain null.")
        if self.reviewer_id is None and self.reviewed_at is not None:
            raise ValueError("reviewed_at cannot be set when reviewer_id is null.")
        if self.reviewer_id is not None and len(completed_scores) != 6:
            raise ValueError("Completed reviews must provide all six human scores.")
        if len(completed_scores) == 6:
            expected = round(sum(completed_scores) / 6 * 20, 2)
            if self.overall_human_score is None:
                object.__setattr__(self, "overall_human_score", expected)
            elif round(self.overall_human_score, 2) != expected:
                raise ValueError("overall_human_score does not match the six rubric scores.")
        else:
            if self.overall_human_score is not None:
                raise ValueError("overall_human_score must remain null until all scores are filled.")
            if self.pass_fail is not None:
                raise ValueError("pass_fail must remain null until review is completed.")
        return self


class SolutionInsightHumanEvalAggregateScores(StrictBaseModel):
    business_relevance_score: float
    evidence_grounding_score: float
    risk_fallback_score: float
    actionability_score: float
    communication_quality_score: float
    product_thinking_score: float
    overall_human_score: float


class SolutionInsightHumanEvalSummary(StrictBaseModel):
    evaluation_version: str
    human_review_status: Literal["not_started", "in_progress", "completed"]
    review_packet_case_count: int
    annotation_case_count: int
    completed_review_count: int
    aggregate_scores: SolutionInsightHumanEvalAggregateScores | None = None
    pass_rate: float | None = None
    strengths_summary: list[str] = Field(default_factory=list)
    weaknesses_summary: list[str] = Field(default_factory=list)
    suggested_improvements_summary: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
