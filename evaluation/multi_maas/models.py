from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from agent.model_providers.openai_compatible import MaaSProviderUsage
from schemas.common_models import StrictBaseModel


MULTI_MAAS_BOUNDARY_NOTE = (
    "Multi-MaaS evaluation results may be skipped or dry-run; heuristic scores are not human ratings, "
    "do not prove business impact, do not replace formal retrieval benchmarks, do not replace human evaluation, "
    "estimated cost is not real billing, and provider fallback recommendations are not production routing."
)

MultiMaaSStatus = Literal[
    "success",
    "skipped_missing_api_key",
    "skipped_dry_run",
    "failed",
    "schema_invalid",
    "provider_unavailable",
    "timeout",
]


class MultiMaaSEvaluationCase(StrictBaseModel):
    case_id: str
    case_name: str
    input_text: str
    expected_output_fields: list[str]
    risk_level: str
    requires_evidence: bool
    requires_structured_output: bool
    category: str

    @field_validator("expected_output_fields")
    @classmethod
    def expected_fields_must_not_be_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("expected_output_fields must not be empty.")
        return value


class ProviderModelTarget(StrictBaseModel):
    provider_name: str
    model_name: str
    adapter_type: str
    verification_status: str
    api_key_env: str
    dry_run: bool = True


class MultiMaaSEvaluationResult(StrictBaseModel):
    run_id: str
    case_id: str
    provider_name: str
    model_name: str
    adapter_type: str
    verification_status: str
    status: MultiMaaSStatus
    output_preview: str | None = None
    latency_ms: int = 0
    usage: MaaSProviderUsage = Field(default_factory=MaaSProviderUsage)
    usage_available: bool = False
    estimated_cost: str | None = None
    schema_valid: bool | None = None
    expected_fields_present: dict[str, bool] = Field(default_factory=dict)
    answer_quality_score: float | None = None
    evidence_grounding_score: float | None = None
    fallback_triggered: bool = False
    human_review_triggered: bool = False
    error_type: str | None = None
    error_message: str | None = None
    recommended_recovery_action: str | None = None
    boundary_note: str = MULTI_MAAS_BOUNDARY_NOTE
    created_at: str


class ProviderSummary(StrictBaseModel):
    provider_name: str
    model_name: str
    total_runs: int = 0
    success_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    schema_valid_rate: float | None = None
    usage_available_rate: float | None = None
    average_latency_ms: float | None = None
    provider_error_rate: float | None = None


class MultiMaaSEvaluationSummary(StrictBaseModel):
    run_id: str
    created_at: str
    total_cases: int
    total_targets: int
    total_runs: int
    success_count: int
    skipped_count: int
    failed_count: int
    schema_valid_rate: float | None = None
    usage_available_rate: float | None = None
    average_latency_ms: float | None = None
    average_estimated_cost: float | None = None
    provider_error_rate: float | None = None
    timeout_rate: float | None = None
    retry_recommended_count: int = 0
    fallback_recommended_count: int = 0
    human_review_trigger_count: int = 0
    boundary_note: str = MULTI_MAAS_BOUNDARY_NOTE
    provider_summaries: list[ProviderSummary] = Field(default_factory=list)


class MultiMaaSEvaluationReport(StrictBaseModel):
    run_id: str
    created_at: str
    dry_run: bool
    targets: list[ProviderModelTarget]
    cases: list[MultiMaaSEvaluationCase]
    summary: MultiMaaSEvaluationSummary
    results: list[MultiMaaSEvaluationResult]
    selection_recommendation: dict[str, object] | None = None
    recovery_summary: dict[str, object] | None = None
    boundary_notes: list[str] = Field(default_factory=lambda: [MULTI_MAAS_BOUNDARY_NOTE])
