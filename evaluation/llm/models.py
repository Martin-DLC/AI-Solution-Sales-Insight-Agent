from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator

from schemas.common_models import StrictBaseModel


SUPPORTED_PROVIDER_IDS = (
    "deterministic",
    "deepseek",
    "qwen",
    "glm",
    "doubao",
    "openai",
    "claude",
)

REQUIRED_RESPONSE_SECTIONS = (
    "requirement_summary",
    "pain_points",
    "ai_opportunity_points",
    "proposed_solution",
    "evidence_items",
    "evidence_completeness",
    "fallback_recommended",
    "fallback_reasons",
    "human_confirmation_required",
    "retrieval_debug",
)


class SolutionInsightEvalCase(StrictBaseModel):
    case_id: str
    user_query: str
    industry: str | None = None
    company_size: str | None = None
    current_systems: list[str] = Field(default_factory=list)
    target_goal: str | None = None
    constraints: list[str] = Field(default_factory=list)
    expected_focus_areas: list[str] = Field(default_factory=list)
    required_output_sections: list[str] = Field(default_factory=lambda: list(REQUIRED_RESPONSE_SECTIONS))
    expected_fallback_behavior: bool
    forbidden_claims: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator(
        "current_systems",
        "constraints",
        "expected_focus_areas",
        "required_output_sections",
        "forbidden_claims",
    )
    @classmethod
    def deduplicate_list_values(cls, values: list[str]) -> list[str]:
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


class SolutionInsightEvalScores(StrictBaseModel):
    schema_validity: int = Field(ge=0, le=20)
    section_completeness: int = Field(ge=0, le=15)
    evidence_grounding: int = Field(ge=0, le=20)
    hallucination_risk: int = Field(ge=0, le=20)
    fallback_alignment: int = Field(ge=0, le=15)
    chinese_business_clarity: int = Field(ge=0, le=10)
    overall_score: int = Field(ge=0, le=100)


class SolutionInsightEvalCaseResult(StrictBaseModel):
    case_id: str
    provider: str
    model_mode: str
    scores: SolutionInsightEvalScores
    score_reasons: dict[str, list[str]] = Field(default_factory=dict)
    schema_is_valid: bool
    hallucination_risk_detected: bool
    fallback_alignment_ok: bool
    response_snapshot: dict[str, Any] = Field(default_factory=dict)


class SolutionInsightEvalAggregateScores(StrictBaseModel):
    schema_validity: float
    section_completeness: float
    evidence_grounding: float
    hallucination_risk: float
    fallback_alignment: float
    chinese_business_clarity: float
    overall_score: float


class SolutionInsightEvalReport(StrictBaseModel):
    evaluation_version: str
    model_mode: Literal["deterministic"]
    provider: Literal["local_template"]
    case_count: int
    aggregate_scores: SolutionInsightEvalAggregateScores
    per_case_results: list[SolutionInsightEvalCaseResult]
    failed_cases: list[str] = Field(default_factory=list)
    hallucination_risk_cases: list[str] = Field(default_factory=list)
    fallback_mismatch_cases: list[str] = Field(default_factory=list)
    schema_invalid_cases: list[str] = Field(default_factory=list)
    average_overall_score: float
    limitations: list[str] = Field(default_factory=list)
    generated_at: str


class SolutionInsightEvalPlan(StrictBaseModel):
    mode: Literal["plan"]
    evaluation_version: str
    enabled_provider: str
    disabled_providers: list[str]
    case_count: int
    output_path: str
    note: str

