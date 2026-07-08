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


COMPARISON_PROVIDER_STATUSES = (
    "available",
    "completed",
    "completed_with_case_errors",
    "skipped_missing_api_key",
    "failed",
)


class SolutionInsightComparisonProviderStatus(StrictBaseModel):
    provider_name: str
    model_name: str | None = None
    provider_status: Literal[
        "available",
        "completed",
        "completed_with_case_errors",
        "skipped_missing_api_key",
        "failed",
    ]
    reason: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    cases_attempted: int = 0
    cases_scored: int = 0


class SolutionInsightComparisonCaseError(StrictBaseModel):
    case_id: str
    error_type: str
    error_message: str


class SolutionInsightComparisonLatencySummary(StrictBaseModel):
    average_latency_ms: float | None = None
    max_latency_ms: int | None = None
    min_latency_ms: int | None = None
    total_latency_ms: int = 0
    measured_case_count: int = 0


class SolutionInsightComparisonCostSummary(StrictBaseModel):
    prompt_tokens_total: int = 0
    completion_tokens_total: int = 0
    total_tokens_total: int = 0
    estimated_cost: float | None = None


class SolutionInsightModelComparisonPlan(StrictBaseModel):
    mode: Literal["provider_plan"]
    comparison_version: str
    evaluation_case_count: int
    providers_requested: list[str]
    provider_statuses: dict[str, SolutionInsightComparisonProviderStatus]
    comparison_output_path: str
    note: str


class SolutionInsightModelComparisonReport(StrictBaseModel):
    comparison_version: str
    evaluation_case_count: int
    providers_requested: list[str]
    providers_run: list[str] = Field(default_factory=list)
    providers_skipped: list[str] = Field(default_factory=list)
    provider_statuses: dict[str, SolutionInsightComparisonProviderStatus] = Field(default_factory=dict)
    aggregate_scores_by_provider: dict[str, SolutionInsightEvalAggregateScores | None] = Field(default_factory=dict)
    per_case_scores_by_provider: dict[str, list[SolutionInsightEvalCaseResult]] = Field(default_factory=dict)
    latency_summary: dict[str, SolutionInsightComparisonLatencySummary] = Field(default_factory=dict)
    cost_estimate_optional: dict[str, SolutionInsightComparisonCostSummary] = Field(default_factory=dict)
    hallucination_risk_cases_by_provider: dict[str, list[str]] = Field(default_factory=dict)
    fallback_mismatch_cases_by_provider: dict[str, list[str]] = Field(default_factory=dict)
    schema_invalid_cases_by_provider: dict[str, list[str]] = Field(default_factory=dict)
    case_errors_by_provider: dict[str, list[SolutionInsightComparisonCaseError]] = Field(default_factory=dict)
    best_provider_by_dimension: dict[str, str | None] = Field(default_factory=dict)
    recommended_provider_for_demo: str | None = None
    recommended_provider_for_production_poc: str | None = None
    limitations: list[str] = Field(default_factory=list)
    generated_at: str
