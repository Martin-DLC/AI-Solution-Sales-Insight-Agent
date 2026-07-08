from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent import SolutionInsightRequest, SolutionInsightResponse, SolutionInsightService
from agent.prompts.solution_insight_prompt import build_solution_insight_messages
from dataio.jsonl_loader import load_jsonl_models
from evaluation.llm.comparison import (
    build_aggregate_scores,
    build_best_provider_by_dimension,
    build_cost_summary,
    build_latency_summary,
    recommend_provider_for_demo,
    recommend_provider_for_production_poc,
)
from evaluation.llm.evaluator import evaluate_solution_insight_response
from evaluation.llm.models import (
    SUPPORTED_PROVIDER_IDS,
    SolutionInsightComparisonCaseError,
    SolutionInsightComparisonProviderStatus,
    SolutionInsightEvalAggregateScores,
    SolutionInsightEvalCase,
    SolutionInsightEvalPlan,
    SolutionInsightEvalReport,
    SolutionInsightModelComparisonPlan,
    SolutionInsightModelComparisonReport,
)
from evaluation.llm.providers import create_provider_client, get_provider_spec, provider_is_available
from llm.errors import LLMJSONDecodeError, LLMRequestError, LLMResponseError


EVALUATION_VERSION = "solution_insight_llm_eval_v0.2"
COMPARISON_VERSION = "solution_insight_llm_model_comparison_v1"
DEFAULT_PROVIDER = "deterministic"
DATASET_PATH = Path("data/evaluation/llm/solution_insight_eval_cases.jsonl")
BASELINE_OUTPUT_PATH = Path("data/evaluation/llm/solution_insight_deterministic_baseline.v1.json")
COMPARISON_OUTPUT_PATH = Path("data/evaluation/llm/solution_insight_model_comparison.v1.json")
LOCAL_PROVIDER_NAME = "local_template"


def build_plan_payload(
    *,
    provider: str = DEFAULT_PROVIDER,
    dataset_path: Path | None = None,
    output_path: Path | None = None,
) -> SolutionInsightEvalPlan:
    dataset_path = dataset_path or DATASET_PATH
    output_path = output_path or BASELINE_OUTPUT_PATH
    cases = load_eval_cases(dataset_path)
    ensure_provider_is_supported(provider)
    return SolutionInsightEvalPlan(
        mode="plan",
        evaluation_version=EVALUATION_VERSION,
        enabled_provider=provider,
        disabled_providers=[item for item in SUPPORTED_PROVIDER_IDS if item != provider],
        case_count=len(cases),
        output_path=str(output_path),
        note="Only deterministic provider is enabled in v0.2. No external model API calls are made.",
    )


def build_comparison_plan_payload(
    *,
    providers: list[str],
    dataset_path: Path | None = None,
    output_path: Path | None = None,
) -> SolutionInsightModelComparisonPlan:
    dataset_path = dataset_path or DATASET_PATH
    output_path = output_path or COMPARISON_OUTPUT_PATH
    cases = load_eval_cases(dataset_path)
    normalized = normalize_providers(providers)
    provider_statuses: dict[str, SolutionInsightComparisonProviderStatus] = {}
    for provider_name in normalized:
        ensure_provider_name_is_supported(provider_name)
        spec = get_provider_spec(provider_name)
        if provider_name == DEFAULT_PROVIDER:
            provider_statuses[provider_name] = SolutionInsightComparisonProviderStatus(
                provider_name=provider_name,
                model_name=spec.configured_model(),
                provider_status="available",
                reason="Local deterministic provider is always available.",
            )
            continue
        if provider_is_available(provider_name):
            provider_statuses[provider_name] = SolutionInsightComparisonProviderStatus(
                provider_name=provider_name,
                model_name=spec.configured_model(),
                provider_status="available",
                reason="Provider API key is configured.",
            )
        else:
            provider_statuses[provider_name] = SolutionInsightComparisonProviderStatus(
                provider_name=provider_name,
                model_name=spec.configured_model(),
                provider_status="skipped_missing_api_key",
                reason=f"Environment variable {spec.api_key_env} is not configured.",
            )
    return SolutionInsightModelComparisonPlan(
        mode="provider_plan",
        comparison_version=COMPARISON_VERSION,
        evaluation_case_count=len(cases),
        providers_requested=normalized,
        provider_statuses=provider_statuses,
        comparison_output_path=str(output_path),
        note=(
            "This plan does not write artifacts. Deterministic remains the CI baseline, "
            "and external providers are optional live comparisons."
        ),
    )


def load_eval_cases(dataset_path: Path | None = None) -> list[SolutionInsightEvalCase]:
    dataset_path = dataset_path or DATASET_PATH
    return load_jsonl_models(dataset_path, SolutionInsightEvalCase)


def run_evaluation(
    *,
    provider: str = DEFAULT_PROVIDER,
    dataset_path: Path | None = None,
) -> SolutionInsightEvalReport:
    dataset_path = dataset_path or DATASET_PATH
    ensure_provider_is_supported(provider)
    cases = load_eval_cases(dataset_path)
    service = build_service_for_provider(provider)
    per_case_results = []
    for case in cases:
        request = SolutionInsightRequest(
            user_query=case.user_query,
            industry=case.industry,
            company_size=case.company_size,
            current_systems=list(case.current_systems),
            target_goal=case.target_goal,
            constraints=list(case.constraints),
            enable_shadow_retrieval=True,
            llm_mode="deterministic",
        )
        response = service.generate_insight(request)
        per_case_results.append(
            evaluate_solution_insight_response(
                case,
                response,
                provider=LOCAL_PROVIDER_NAME,
                model_mode="deterministic",
            )
        )

    aggregate_scores = SolutionInsightEvalAggregateScores(
        schema_validity=_average_score(per_case_results, "schema_validity"),
        section_completeness=_average_score(per_case_results, "section_completeness"),
        evidence_grounding=_average_score(per_case_results, "evidence_grounding"),
        hallucination_risk=_average_score(per_case_results, "hallucination_risk"),
        fallback_alignment=_average_score(per_case_results, "fallback_alignment"),
        chinese_business_clarity=_average_score(per_case_results, "chinese_business_clarity"),
        overall_score=_average_score(per_case_results, "overall_score"),
    )
    failed_cases = [item.case_id for item in per_case_results if item.scores.overall_score < 70]
    hallucination_risk_cases = [item.case_id for item in per_case_results if item.hallucination_risk_detected]
    fallback_mismatch_cases = [item.case_id for item in per_case_results if not item.fallback_alignment_ok]
    schema_invalid_cases = [item.case_id for item in per_case_results if not item.schema_is_valid]

    return SolutionInsightEvalReport(
        evaluation_version=EVALUATION_VERSION,
        model_mode="deterministic",
        provider=LOCAL_PROVIDER_NAME,
        case_count=len(per_case_results),
        aggregate_scores=aggregate_scores,
        per_case_results=per_case_results,
        failed_cases=failed_cases,
        hallucination_risk_cases=hallucination_risk_cases,
        fallback_mismatch_cases=fallback_mismatch_cases,
        schema_invalid_cases=schema_invalid_cases,
        average_overall_score=aggregate_scores.overall_score,
        limitations=[
            "Only deterministic mode is evaluated in v0.2.",
            "Scores are rule-based and do not replace human judgment.",
            "No external provider API is called in this evaluation harness.",
            "Current formal retriever remains blocked by the frozen Retrieval Benchmark v2 gate.",
        ],
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def run_provider_comparison(
    *,
    providers: list[str],
    dataset_path: Path | None = None,
) -> SolutionInsightModelComparisonReport:
    dataset_path = dataset_path or DATASET_PATH
    cases = load_eval_cases(dataset_path)
    normalized_providers = normalize_providers(providers)
    deterministic_service = SolutionInsightService.from_defaults(enable_shadow_retrieval=True, llm_mode="deterministic")

    provider_statuses: dict[str, SolutionInsightComparisonProviderStatus] = {}
    aggregate_scores_by_provider: dict[str, SolutionInsightEvalAggregateScores | None] = {}
    per_case_scores_by_provider: dict[str, list[Any]] = {}
    latency_summary: dict[str, Any] = {}
    cost_estimate_optional: dict[str, Any] = {}
    hallucination_risk_cases_by_provider: dict[str, list[str]] = {}
    fallback_mismatch_cases_by_provider: dict[str, list[str]] = {}
    schema_invalid_cases_by_provider: dict[str, list[str]] = {}
    case_errors_by_provider: dict[str, list[SolutionInsightComparisonCaseError]] = {}

    providers_run: list[str] = []
    providers_skipped: list[str] = []

    for provider_name in normalized_providers:
        ensure_provider_name_is_supported(provider_name)
        spec = get_provider_spec(provider_name)

        if provider_name == DEFAULT_PROVIDER:
            results, latencies, usages = _run_deterministic_provider(cases, deterministic_service)
            provider_statuses[provider_name] = SolutionInsightComparisonProviderStatus(
                provider_name=provider_name,
                model_name=spec.configured_model(),
                provider_status="completed",
                cases_attempted=len(cases),
                cases_scored=len(results),
                reason="Local deterministic baseline completed successfully.",
            )
            _populate_provider_outputs(
                provider_name=provider_name,
                results=results,
                latencies=latencies,
                usages=usages,
                case_errors=[],
                aggregate_scores_by_provider=aggregate_scores_by_provider,
                per_case_scores_by_provider=per_case_scores_by_provider,
                latency_summary=latency_summary,
                cost_estimate_optional=cost_estimate_optional,
                hallucination_risk_cases_by_provider=hallucination_risk_cases_by_provider,
                fallback_mismatch_cases_by_provider=fallback_mismatch_cases_by_provider,
                schema_invalid_cases_by_provider=schema_invalid_cases_by_provider,
                case_errors_by_provider=case_errors_by_provider,
            )
            providers_run.append(provider_name)
            continue

        if not provider_is_available(provider_name):
            provider_statuses[provider_name] = SolutionInsightComparisonProviderStatus(
                provider_name=provider_name,
                model_name=spec.configured_model(),
                provider_status="skipped_missing_api_key",
                reason=f"Environment variable {spec.api_key_env} is not configured.",
            )
            providers_skipped.append(provider_name)
            continue

        try:
            client = create_provider_client(provider_name)
        except Exception as exc:
            provider_statuses[provider_name] = SolutionInsightComparisonProviderStatus(
                provider_name=provider_name,
                model_name=spec.configured_model(),
                provider_status="failed",
                error_type=exc.__class__.__name__,
                error_message=_safe_error_message(exc),
                reason="Provider client could not be created.",
            )
            continue

        results, latencies, usages, case_errors = _run_live_provider(
            cases=cases,
            service=deterministic_service,
            provider_name=provider_name,
            client=client,
        )
        cases_scored = len(results)
        if cases_scored == 0:
            first_error = case_errors[0] if case_errors else None
            provider_statuses[provider_name] = SolutionInsightComparisonProviderStatus(
                provider_name=provider_name,
                model_name=spec.configured_model(),
                provider_status="failed",
                error_type=first_error.error_type if first_error else None,
                error_message=first_error.error_message if first_error else None,
                cases_attempted=len(cases),
                cases_scored=0,
                reason="Provider returned no scoreable outputs.",
            )
            case_errors_by_provider[provider_name] = case_errors
            continue

        provider_statuses[provider_name] = SolutionInsightComparisonProviderStatus(
            provider_name=provider_name,
            model_name=spec.configured_model(),
            provider_status="completed" if not case_errors else "completed_with_case_errors",
            error_type=case_errors[0].error_type if case_errors else None,
            error_message=case_errors[0].error_message if case_errors else None,
            cases_attempted=len(cases),
            cases_scored=cases_scored,
            reason="Provider comparison completed." if not case_errors else "Provider completed with per-case errors.",
        )
        _populate_provider_outputs(
            provider_name=provider_name,
            results=results,
            latencies=latencies,
            usages=usages,
            case_errors=case_errors,
            aggregate_scores_by_provider=aggregate_scores_by_provider,
            per_case_scores_by_provider=per_case_scores_by_provider,
            latency_summary=latency_summary,
            cost_estimate_optional=cost_estimate_optional,
            hallucination_risk_cases_by_provider=hallucination_risk_cases_by_provider,
            fallback_mismatch_cases_by_provider=fallback_mismatch_cases_by_provider,
            schema_invalid_cases_by_provider=schema_invalid_cases_by_provider,
            case_errors_by_provider=case_errors_by_provider,
        )
        providers_run.append(provider_name)

    report = SolutionInsightModelComparisonReport(
        comparison_version=COMPARISON_VERSION,
        evaluation_case_count=len(cases),
        providers_requested=normalized_providers,
        providers_run=providers_run,
        providers_skipped=providers_skipped,
        provider_statuses=provider_statuses,
        aggregate_scores_by_provider=aggregate_scores_by_provider,
        per_case_scores_by_provider=per_case_scores_by_provider,
        latency_summary=latency_summary,
        cost_estimate_optional=cost_estimate_optional,
        hallucination_risk_cases_by_provider=hallucination_risk_cases_by_provider,
        fallback_mismatch_cases_by_provider=fallback_mismatch_cases_by_provider,
        schema_invalid_cases_by_provider=schema_invalid_cases_by_provider,
        case_errors_by_provider=case_errors_by_provider,
        best_provider_by_dimension=build_best_provider_by_dimension(aggregate_scores_by_provider),
        recommended_provider_for_demo=None,
        recommended_provider_for_production_poc=None,
        limitations=_build_comparison_limitations(provider_statuses),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    report.recommended_provider_for_demo = recommend_provider_for_demo(report)
    report.recommended_provider_for_production_poc = recommend_provider_for_production_poc(report)
    return report


def write_baseline(
    *,
    provider: str = DEFAULT_PROVIDER,
    dataset_path: Path | None = None,
    output_path: Path | None = None,
) -> SolutionInsightEvalReport:
    dataset_path = dataset_path or DATASET_PATH
    output_path = output_path or BASELINE_OUTPUT_PATH
    report = run_evaluation(provider=provider, dataset_path=dataset_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temp_output_path = output_path.with_name(f"{output_path.name}.tmp")
    temp_output_path.write_text(payload, encoding="utf-8")
    temp_output_path.replace(output_path)
    return report


def write_provider_comparison(
    *,
    providers: list[str],
    dataset_path: Path | None = None,
    output_path: Path | None = None,
) -> SolutionInsightModelComparisonReport:
    dataset_path = dataset_path or DATASET_PATH
    output_path = output_path or COMPARISON_OUTPUT_PATH
    report = run_provider_comparison(providers=providers, dataset_path=dataset_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output_path.write_text(payload, encoding="utf-8")
    return report


def check_baseline(
    *,
    provider: str = DEFAULT_PROVIDER,
    dataset_path: Path | None = None,
    output_path: Path | None = None,
) -> tuple[bool, dict[str, Any]]:
    dataset_path = dataset_path or DATASET_PATH
    output_path = output_path or BASELINE_OUTPUT_PATH
    report = run_evaluation(provider=provider, dataset_path=dataset_path)
    if not output_path.exists():
        return False, {"reason": "baseline_missing", "output_path": str(output_path)}
    frozen_payload = json.loads(output_path.read_text(encoding="utf-8"))
    current_payload = report.model_dump(mode="json")
    matches = _normalize_report_payload(frozen_payload) == _normalize_report_payload(current_payload)
    return matches, {
        "reason": "outputs_match" if matches else "outputs_mismatch",
        "output_path": str(output_path),
        "case_count": current_payload["case_count"],
    }


def check_provider_comparison(
    *,
    output_path: Path | None = None,
) -> tuple[bool, dict[str, Any]]:
    output_path = output_path or COMPARISON_OUTPUT_PATH
    if not output_path.exists():
        return False, {"reason": "comparison_missing", "output_path": str(output_path)}
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        SolutionInsightModelComparisonReport.model_validate(payload)
    except Exception as exc:
        return False, {
            "reason": "comparison_invalid",
            "output_path": str(output_path),
            "error_type": exc.__class__.__name__,
            "error_message": _safe_error_message(exc),
        }
    return True, {"reason": "comparison_outputs_parseable", "output_path": str(output_path)}


def build_service_for_provider(provider: str) -> SolutionInsightService:
    if provider != DEFAULT_PROVIDER:
        raise NotImplementedError(
            f"Provider {provider!r} is reserved for future live evaluation and is disabled in v0.2."
        )
    return SolutionInsightService.from_defaults(enable_shadow_retrieval=True, llm_mode="deterministic")


def ensure_provider_is_supported(provider: str) -> None:
    if provider not in SUPPORTED_PROVIDER_IDS:
        raise ValueError(f"Unknown provider {provider!r}. Supported values: {', '.join(SUPPORTED_PROVIDER_IDS)}.")
    if provider != DEFAULT_PROVIDER:
        raise NotImplementedError(
            f"Provider {provider!r} is not enabled in v0.2. Only deterministic runs are allowed without network access."
        )


def ensure_provider_name_is_supported(provider: str) -> None:
    if provider not in SUPPORTED_PROVIDER_IDS:
        raise ValueError(f"Unknown provider {provider!r}. Supported values: {', '.join(SUPPORTED_PROVIDER_IDS)}.")


def normalize_providers(providers: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for provider in providers:
        normalized = provider.strip().casefold()
        if not normalized:
            continue
        ensure_provider_name_is_supported(normalized)
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    if not result:
        return [DEFAULT_PROVIDER]
    return result


def _average_score(per_case_results: list[Any], field_name: str) -> float:
    if not per_case_results:
        return 0.0
    total = sum(getattr(item.scores, field_name) for item in per_case_results)
    return round(total / len(per_case_results), 4)


def _normalize_report_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(payload))
    normalized["generated_at"] = "<ignored>"
    return normalized


def _run_deterministic_provider(
    cases: list[SolutionInsightEvalCase],
    service: SolutionInsightService,
) -> tuple[list[Any], list[int], list[dict[str, int | None]]]:
    results = []
    latencies: list[int] = []
    usages: list[dict[str, int | None]] = []
    for case in cases:
        request = _build_request(case, llm_mode="deterministic")
        response = service.generate_insight(request)
        results.append(
            evaluate_solution_insight_response(
                case,
                response,
                provider=LOCAL_PROVIDER_NAME,
                model_mode="deterministic",
            )
        )
        latencies.append(0)
        usages.append({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    return results, latencies, usages


def _run_live_provider(
    *,
    cases: list[SolutionInsightEvalCase],
    service: SolutionInsightService,
    provider_name: str,
    client: Any,
) -> tuple[list[Any], list[int], list[dict[str, int | None]], list[SolutionInsightComparisonCaseError]]:
    results = []
    latencies: list[int] = []
    usages: list[dict[str, int | None]] = []
    case_errors: list[SolutionInsightComparisonCaseError] = []

    for case in cases:
        request = _build_request(case, llm_mode="auto")
        scaffold = service.generate_insight(_build_request(case, llm_mode="deterministic"))
        messages = build_solution_insight_messages(
            request=request,
            formal_evidence_payload=[
                {
                    "title": item.title,
                    "candidate_type": item.candidate_type,
                    "document_id": item.document_id,
                    "chunk_id": item.chunk_id,
                    "citation_label": item.citation_label,
                    "content_excerpt": item.content_excerpt,
                }
                for item in scaffold.evidence_items
            ],
        )
        try:
            response = client.complete_json(messages)
            normalized_response = _merge_provider_output_onto_scaffold(
                scaffold=scaffold,
                provider_payload=response.parsed_json or {},
                provider_name=provider_name,
            )
            results.append(
                evaluate_solution_insight_response(
                    case,
                    normalized_response,
                    provider=provider_name,
                    model_mode="llm",
                )
            )
            latencies.append(response.latency_ms)
            usages.append(response.usage.model_dump(mode="json"))
        except LLMJSONDecodeError as exc:
            invalid_payload = _build_invalid_provider_payload(scaffold)
            results.append(
                evaluate_solution_insight_response(
                    case,
                    invalid_payload,
                    provider=provider_name,
                    model_mode="llm",
                )
            )
            latencies.append(0)
            usages.append({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
            case_errors.append(
                SolutionInsightComparisonCaseError(
                    case_id=case.case_id,
                    error_type=exc.__class__.__name__,
                    error_message=_safe_error_message(exc),
                )
            )
        except (LLMRequestError, LLMResponseError, Exception) as exc:
            case_errors.append(
                SolutionInsightComparisonCaseError(
                    case_id=case.case_id,
                    error_type=exc.__class__.__name__,
                    error_message=_safe_error_message(exc),
                )
            )
    return results, latencies, usages, case_errors


def _populate_provider_outputs(
    *,
    provider_name: str,
    results: list[Any],
    latencies: list[int],
    usages: list[dict[str, int | None]],
    case_errors: list[SolutionInsightComparisonCaseError],
    aggregate_scores_by_provider: dict[str, SolutionInsightEvalAggregateScores | None],
    per_case_scores_by_provider: dict[str, list[Any]],
    latency_summary: dict[str, Any],
    cost_estimate_optional: dict[str, Any],
    hallucination_risk_cases_by_provider: dict[str, list[str]],
    fallback_mismatch_cases_by_provider: dict[str, list[str]],
    schema_invalid_cases_by_provider: dict[str, list[str]],
    case_errors_by_provider: dict[str, list[SolutionInsightComparisonCaseError]],
) -> None:
    aggregate_scores_by_provider[provider_name] = build_aggregate_scores(results) if results else None
    per_case_scores_by_provider[provider_name] = results
    latency_summary[provider_name] = build_latency_summary(latencies)
    cost_estimate_optional[provider_name] = build_cost_summary(usages)
    hallucination_risk_cases_by_provider[provider_name] = [item.case_id for item in results if item.hallucination_risk_detected]
    fallback_mismatch_cases_by_provider[provider_name] = [item.case_id for item in results if not item.fallback_alignment_ok]
    schema_invalid_cases_by_provider[provider_name] = [item.case_id for item in results if not item.schema_is_valid]
    case_errors_by_provider[provider_name] = case_errors


def _build_request(case: SolutionInsightEvalCase, *, llm_mode: str) -> SolutionInsightRequest:
    return SolutionInsightRequest(
        user_query=case.user_query,
        industry=case.industry,
        company_size=case.company_size,
        current_systems=list(case.current_systems),
        target_goal=case.target_goal,
        constraints=list(case.constraints),
        enable_shadow_retrieval=True,
        llm_mode=llm_mode,
    )


def _merge_provider_output_onto_scaffold(
    *,
    scaffold: SolutionInsightResponse,
    provider_payload: dict[str, Any],
    provider_name: str,
) -> SolutionInsightResponse:
    payload = scaffold.model_dump(mode="json")
    payload.update(
        {
            "requirement_summary": str(
                provider_payload.get("requirement_summary") or scaffold.requirement_summary
            ),
            "pain_points": _ensure_string_list(provider_payload.get("pain_points")) or list(scaffold.pain_points),
            "ai_opportunity_points": _ensure_string_list(provider_payload.get("ai_opportunity_points"))
            or list(scaffold.ai_opportunity_points),
            "proposed_solution": str(provider_payload.get("proposed_solution") or scaffold.proposed_solution),
            "response_note": str(provider_payload.get("response_note") or scaffold.response_note),
            "llm_mode": "llm",
        }
    )
    payload["log_record"] = dict(scaffold.log_record) | {"llm_provider": provider_name, "llm_mode": "llm"}
    return SolutionInsightResponse.model_validate(payload)


def _build_invalid_provider_payload(scaffold: SolutionInsightResponse) -> dict[str, Any]:
    payload = scaffold.model_dump(mode="json")
    for field_name in ("requirement_summary", "pain_points", "ai_opportunity_points", "proposed_solution"):
        payload.pop(field_name, None)
    payload["llm_mode"] = "llm"
    payload["response_note"] = "Provider response could not be normalized into the required JSON structure."
    return payload


def _build_comparison_limitations(
    provider_statuses: dict[str, SolutionInsightComparisonProviderStatus],
) -> list[str]:
    limitations = [
        "Deterministic baseline remains the only frozen CI contract.",
        "Comparison artifact is parse-checked only and is not byte-for-byte reproducible.",
        "Scores are rule-based and do not replace human review.",
        "Current formal retriever remains blocked by the frozen Retrieval Benchmark v2 gate.",
    ]
    if not any(
        status.provider_status in {"completed", "completed_with_case_errors"} and status.provider_name != "deterministic"
        for status in provider_statuses.values()
    ):
        limitations.append("no_external_provider_results")
    return limitations


def _ensure_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _safe_error_message(error: Exception) -> str:
    message = str(error).strip() or error.__class__.__name__
    return message.splitlines()[0][:240]
