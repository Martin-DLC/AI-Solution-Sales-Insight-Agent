from __future__ import annotations

from collections import Counter

from pydantic import Field

from evaluation.multi_maas.models import MULTI_MAAS_BOUNDARY_NOTE, MultiMaaSEvaluationResult
from schemas.common_models import StrictBaseModel


RECOVERY_BOUNDARY_NOTE = (
    "Recovery summary is evaluation-only; it does not execute retry, fallback, compensation, or production routing. "
    "skipped_missing_api_key may count as fallback recommended, but it is not a model quality failure."
)


class ProviderRecoverySummary(StrictBaseModel):
    provider_name: str
    total_results: int
    retry_recommended_count: int = 0
    fallback_recommended_count: int = 0
    human_review_recommended_count: int = 0
    stop_recommended_count: int = 0
    provider_unavailable_count: int = 0
    timeout_count: int = 0
    schema_invalid_count: int = 0
    unknown_error_count: int = 0


class RecoveryRecommendationSummary(StrictBaseModel):
    run_id: str
    total_results: int
    retry_recommended_count: int = 0
    fallback_recommended_count: int = 0
    human_review_recommended_count: int = 0
    stop_recommended_count: int = 0
    provider_unavailable_count: int = 0
    timeout_count: int = 0
    schema_invalid_count: int = 0
    unknown_error_count: int = 0
    per_provider_recovery_summary: list[ProviderRecoverySummary] = Field(default_factory=list)
    boundary_note: str = RECOVERY_BOUNDARY_NOTE


def build_recovery_recommendation_summary(
    results: list[MultiMaaSEvaluationResult],
) -> RecoveryRecommendationSummary:
    run_id = results[0].run_id if results else "unknown"
    action_counts = Counter(classify_recovery_action(result) for result in results)
    return RecoveryRecommendationSummary(
        run_id=run_id,
        total_results=len(results),
        retry_recommended_count=action_counts["retry"],
        fallback_recommended_count=action_counts["fallback"],
        human_review_recommended_count=action_counts["human_review"],
        stop_recommended_count=action_counts["stop"],
        provider_unavailable_count=sum(1 for result in results if result.status == "provider_unavailable"),
        timeout_count=sum(1 for result in results if result.status == "timeout"),
        schema_invalid_count=sum(1 for result in results if result.status == "schema_invalid"),
        unknown_error_count=sum(1 for result in results if result.error_type == "unknown_error"),
        per_provider_recovery_summary=summarize_recovery_by_provider(results),
        boundary_note=RECOVERY_BOUNDARY_NOTE,
    )


def summarize_recovery_by_provider(results: list[MultiMaaSEvaluationResult]) -> list[ProviderRecoverySummary]:
    grouped: dict[str, list[MultiMaaSEvaluationResult]] = {}
    for result in results:
        grouped.setdefault(result.provider_name, []).append(result)
    summaries = []
    for provider_name, provider_results in grouped.items():
        action_counts = Counter(classify_recovery_action(result) for result in provider_results)
        summaries.append(
            ProviderRecoverySummary(
                provider_name=provider_name,
                total_results=len(provider_results),
                retry_recommended_count=action_counts["retry"],
                fallback_recommended_count=action_counts["fallback"],
                human_review_recommended_count=action_counts["human_review"],
                stop_recommended_count=action_counts["stop"],
                provider_unavailable_count=sum(1 for result in provider_results if result.status == "provider_unavailable"),
                timeout_count=sum(1 for result in provider_results if result.status == "timeout"),
                schema_invalid_count=sum(1 for result in provider_results if result.status == "schema_invalid"),
                unknown_error_count=sum(1 for result in provider_results if result.error_type == "unknown_error"),
            )
        )
    return summaries


def classify_recovery_action(result: MultiMaaSEvaluationResult) -> str:
    if result.recommended_recovery_action:
        return result.recommended_recovery_action
    if result.human_review_triggered:
        return "human_review"
    if result.status in {"skipped_missing_api_key", "provider_unavailable", "schema_invalid"}:
        return "fallback"
    if result.status == "timeout":
        return "retry"
    return "none"
