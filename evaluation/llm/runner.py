from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent import SolutionInsightRequest, SolutionInsightService
from dataio.jsonl_loader import load_jsonl_models
from evaluation.llm.evaluator import evaluate_solution_insight_response
from evaluation.llm.models import (
    SUPPORTED_PROVIDER_IDS,
    SolutionInsightEvalAggregateScores,
    SolutionInsightEvalCase,
    SolutionInsightEvalPlan,
    SolutionInsightEvalReport,
)


EVALUATION_VERSION = "solution_insight_llm_eval_v0.2"
DEFAULT_PROVIDER = "deterministic"
DATASET_PATH = Path("data/evaluation/llm/solution_insight_eval_cases.jsonl")
BASELINE_OUTPUT_PATH = Path("data/evaluation/llm/solution_insight_deterministic_baseline.v1.json")
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


def _average_score(per_case_results: list[Any], field_name: str) -> float:
    if not per_case_results:
        return 0.0
    total = sum(getattr(item.scores, field_name) for item in per_case_results)
    return round(total / len(per_case_results), 4)


def _normalize_report_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(payload))
    normalized["generated_at"] = "<ignored>"
    return normalized
