from __future__ import annotations

from evaluation.llm.models import (
    SolutionInsightComparisonCaseError,
    SolutionInsightComparisonCostSummary,
    SolutionInsightComparisonLatencySummary,
    SolutionInsightComparisonProviderStatus,
    SolutionInsightEvalAggregateScores,
    SolutionInsightEvalCaseResult,
    SolutionInsightModelComparisonReport,
)


def build_aggregate_scores(per_case_results: list[SolutionInsightEvalCaseResult]) -> SolutionInsightEvalAggregateScores:
    return SolutionInsightEvalAggregateScores(
        schema_validity=_average_score(per_case_results, "schema_validity"),
        section_completeness=_average_score(per_case_results, "section_completeness"),
        evidence_grounding=_average_score(per_case_results, "evidence_grounding"),
        hallucination_risk=_average_score(per_case_results, "hallucination_risk"),
        fallback_alignment=_average_score(per_case_results, "fallback_alignment"),
        chinese_business_clarity=_average_score(per_case_results, "chinese_business_clarity"),
        overall_score=_average_score(per_case_results, "overall_score"),
    )


def build_latency_summary(latency_values: list[int]) -> SolutionInsightComparisonLatencySummary:
    if not latency_values:
        return SolutionInsightComparisonLatencySummary()
    return SolutionInsightComparisonLatencySummary(
        average_latency_ms=round(sum(latency_values) / len(latency_values), 4),
        max_latency_ms=max(latency_values),
        min_latency_ms=min(latency_values),
        total_latency_ms=sum(latency_values),
        measured_case_count=len(latency_values),
    )


def build_cost_summary(usages: list[dict[str, int | None]]) -> SolutionInsightComparisonCostSummary:
    prompt_tokens_total = sum(int(item.get("prompt_tokens") or 0) for item in usages)
    completion_tokens_total = sum(int(item.get("completion_tokens") or 0) for item in usages)
    total_tokens_total = sum(int(item.get("total_tokens") or 0) for item in usages)
    return SolutionInsightComparisonCostSummary(
        prompt_tokens_total=prompt_tokens_total,
        completion_tokens_total=completion_tokens_total,
        total_tokens_total=total_tokens_total,
        estimated_cost=None,
    )


def build_best_provider_by_dimension(
    aggregate_scores_by_provider: dict[str, SolutionInsightEvalAggregateScores | None],
) -> dict[str, str | None]:
    dimensions = (
        "schema_validity",
        "section_completeness",
        "evidence_grounding",
        "hallucination_risk",
        "fallback_alignment",
        "chinese_business_clarity",
        "overall_score",
    )
    result: dict[str, str | None] = {}
    for dimension in dimensions:
        best_provider: str | None = None
        best_score = float("-inf")
        for provider_name, scores in aggregate_scores_by_provider.items():
            if scores is None:
                continue
            value = float(getattr(scores, dimension))
            if value > best_score:
                best_score = value
                best_provider = provider_name
        result[dimension] = best_provider
    return result


def recommend_provider_for_demo(report: SolutionInsightModelComparisonReport) -> str | None:
    if "deterministic" in report.providers_run:
        return "deterministic"
    for provider_name in report.providers_requested:
        status = report.provider_statuses.get(provider_name)
        if status and status.provider_status in {"completed", "completed_with_case_errors"}:
            return provider_name
    return None


def recommend_provider_for_production_poc(report: SolutionInsightModelComparisonReport) -> str | None:
    external_candidates: list[tuple[float, str]] = []
    for provider_name, aggregate in report.aggregate_scores_by_provider.items():
        if provider_name == "deterministic" or aggregate is None:
            continue
        status = report.provider_statuses.get(provider_name)
        if status is None or status.provider_status not in {"completed", "completed_with_case_errors"}:
            continue
        external_candidates.append((aggregate.overall_score, provider_name))
    if not external_candidates:
        return None
    external_candidates.sort(reverse=True)
    return external_candidates[0][1]


def summarize_case_errors(
    case_errors_by_provider: dict[str, list[SolutionInsightComparisonCaseError]],
) -> dict[str, SolutionInsightComparisonProviderStatus]:
    statuses: dict[str, SolutionInsightComparisonProviderStatus] = {}
    for provider_name, case_errors in case_errors_by_provider.items():
        if not case_errors:
            continue
        first_error = case_errors[0]
        statuses[provider_name] = SolutionInsightComparisonProviderStatus(
            provider_name=provider_name,
            provider_status="completed_with_case_errors",
            error_type=first_error.error_type,
            error_message=first_error.error_message,
            reason=f"{len(case_errors)} case(s) failed during provider evaluation.",
        )
    return statuses


def _average_score(per_case_results: list[SolutionInsightEvalCaseResult], field_name: str) -> float:
    if not per_case_results:
        return 0.0
    total = sum(getattr(item.scores, field_name) for item in per_case_results)
    return round(total / len(per_case_results), 4)
