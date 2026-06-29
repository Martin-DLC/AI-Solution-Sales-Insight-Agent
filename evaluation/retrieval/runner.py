from __future__ import annotations

import json
from statistics import mean
from typing import Any

from pydantic import Field

from evaluation.retrieval.metrics import evaluate_retrieval_case, summarize_retrieval_results
from evaluation.retrieval.models import (
    RetrievalCaseScore,
    RetrievalEvaluationCase,
    RetrievalEvaluationSummary,
    RetrievalMethod,
    RetrievalRunResult,
    summarize_case_mix,
)
from knowledge_base.models import KnowledgeBaseManifest
from knowledge_base.dataset import DemoSolutionScope
from knowledge_base.retrieval.lexical import LexicalBaselineConfig, WeightedBM25Retriever
from schemas.common_models import StrictBaseModel


class LexicalRetrievalCaseResult(StrictBaseModel):
    retrieval_case_id: str
    query_type: str
    retrieval_method: RetrievalMethod
    top_k: int
    retrieved_candidates: list[dict[str, Any]] = Field(default_factory=list)
    case_metrics: dict[str, Any]
    passed_blocking_gate: bool
    failure_reasons: list[str] = Field(default_factory=list)


class LexicalRetrievalEvaluationReport(StrictBaseModel):
    case_results: list[LexicalRetrievalCaseResult] = Field(default_factory=list)
    run_results: list[RetrievalRunResult] = Field(default_factory=list)
    case_scores: list[RetrievalCaseScore] = Field(default_factory=list)
    summary: RetrievalEvaluationSummary


def run_retrieval_evaluation(
    *,
    cases: list[RetrievalEvaluationCase],
    retriever: WeightedBM25Retriever,
    method_id: str,
    top_k: int,
) -> LexicalRetrievalEvaluationReport:
    retrieval_method = RetrievalMethod(method_id)
    run_results: list[RetrievalRunResult] = []
    case_scores: list[RetrievalCaseScore] = []
    case_results: list[LexicalRetrievalCaseResult] = []

    for case in cases:
        try:
            candidates = retriever.retrieve(
                query=case.query,
                filters=case.filters,
                top_k=top_k,
            )
            debug = retriever.last_retrieval_debug
            run_result = RetrievalRunResult(
                retrieval_case_id=case.retrieval_case_id,
                retrieval_method=retrieval_method,
                retrieved_candidates=candidates,
                latency_ms=int(debug.get("elapsed_ms", 0)),
            )
        except Exception as exc:
            debug = {
                "query_tokens": [],
                "filtered_candidate_count": 0,
                "elapsed_ms": 0,
            }
            run_result = RetrievalRunResult(
                retrieval_case_id=case.retrieval_case_id,
                retrieval_method=retrieval_method,
                retrieved_candidates=[],
                latency_ms=0,
                error_type="retrieval_error",
                error_message=_safe_error_message(exc),
            )

        case_score = evaluate_retrieval_case(case=case, result=run_result)
        failure_reasons = _classify_failure_reasons(
            case=case,
            run_result=run_result,
            case_score=case_score,
            retrieval_debug=debug,
        )
        passed_blocking_gate = not failure_reasons
        case_score.eligible_for_rag = passed_blocking_gate
        case_score.disqualification_reasons = list(failure_reasons)

        run_results.append(run_result)
        case_scores.append(case_score)
        case_results.append(
            LexicalRetrievalCaseResult(
                retrieval_case_id=case.retrieval_case_id,
                query_type=case.query_type.value,
                retrieval_method=retrieval_method,
                top_k=top_k,
                retrieved_candidates=[
                    candidate.model_dump(mode="json") for candidate in run_result.retrieved_candidates
                ],
                case_metrics=case_score.model_dump(mode="json"),
                passed_blocking_gate=passed_blocking_gate,
                failure_reasons=failure_reasons,
            )
        )

    summary = summarize_retrieval_results(case_scores)
    summary.eligible_for_rag = _passes_pilot_gate(summary=summary, case_results=case_results)
    summary.disqualification_reasons = _summarize_failure_reasons(case_results)
    return LexicalRetrievalEvaluationReport(
        case_results=case_results,
        run_results=run_results,
        case_scores=case_scores,
        summary=summary,
    )


def build_summary_payload(
    *,
    cases: list[RetrievalEvaluationCase],
    config: LexicalBaselineConfig,
    manifest: KnowledgeBaseManifest,
    demo_scope: DemoSolutionScope,
    report: LexicalRetrievalEvaluationReport,
) -> dict[str, Any]:
    failed_case_ids = [
        result.retrieval_case_id for result in report.case_results if not result.passed_blocking_gate
    ]
    return {
        "baseline_version": config.baseline_version,
        "config_file": "data/evaluation/retrieval/lexical_baseline_config.v1.json",
        "knowledge_base_version": manifest.knowledge_base_version,
        "demo_solution_scope_version": demo_scope.scope_version,
        "case_count": report.summary.case_count,
        "query_type_counts": summarize_case_mix(cases),
        "recall_at_1": report.summary.recall_at_1,
        "recall_at_3": report.summary.recall_at_3,
        "recall_at_5": report.summary.recall_at_5,
        "precision_at_3": report.summary.precision_at_3,
        "precision_at_5": report.summary.precision_at_5,
        "mean_reciprocal_rank": report.summary.mean_reciprocal_rank,
        "forbidden_hit_rate": report.summary.forbidden_hit_rate,
        "solution_boundary_violation_rate": report.summary.solution_boundary_violation_rate,
        "average_latency_ms": report.summary.average_latency_ms,
        "eligible_for_rag": report.summary.eligible_for_rag,
        "disqualification_reasons": report.summary.disqualification_reasons,
        "failed_case_ids": failed_case_ids,
        "generated_from_synthetic_data": True,
        "limitations": [
            "Lexical baseline uses deterministic token overlap and weighted BM25 only.",
            "This benchmark covers the 6-solution public demo scope, not a future enterprise master catalog.",
            "No embeddings, reranking, query rewriting, or hybrid retrieval are used in lexical_v1.",
        ],
    }


def _classify_failure_reasons(
    *,
    case: RetrievalEvaluationCase,
    run_result: RetrievalRunResult,
    case_score: RetrievalCaseScore,
    retrieval_debug: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    relevant_hits = _count_relevant_hits(case=case, run_result=run_result)

    if run_result.error_type:
        reasons.append("retrieval_error")
    if not retrieval_debug.get("query_tokens"):
        reasons.append("empty_query_tokens")
    elif retrieval_debug.get("filtered_candidate_count", 0) == 0:
        reasons.append("operational_filter_excluded_all")
    if relevant_hits == 0:
        reasons.append("no_relevant_hit_at_5")
    if relevant_hits < case.minimum_relevant_hits:
        reasons.append("insufficient_relevant_hits")
    if case_score.forbidden_hit:
        reasons.append("forbidden_document_hit")
    if case_score.solution_boundary_violation:
        reasons.append("solution_boundary_violation")
    return _deduplicate(reasons)


def _count_relevant_hits(
    *,
    case: RetrievalEvaluationCase,
    run_result: RetrievalRunResult,
) -> int:
    expected_document_ids = set(case.expected_relevant_document_ids)
    expected_chunk_ids = set(case.expected_relevant_chunk_ids)
    hits = 0
    for candidate in run_result.retrieved_candidates[:5]:
        if candidate.chunk_id and candidate.chunk_id in expected_chunk_ids:
            hits += 1
            continue
        if candidate.document_id in expected_document_ids:
            hits += 1
    return hits


def _passes_pilot_gate(
    *,
    summary: RetrievalEvaluationSummary,
    case_results: list[LexicalRetrievalCaseResult],
) -> bool:
    return (
        summary.recall_at_5 == 1.0
        and summary.forbidden_hit_rate == 0
        and summary.solution_boundary_violation_rate == 0
        and summary.request_error_count == 0
        and all(result.passed_blocking_gate for result in case_results)
    )


def _summarize_failure_reasons(case_results: list[LexicalRetrievalCaseResult]) -> list[str]:
    ordered: list[str] = []
    for case_result in case_results:
        for reason in case_result.failure_reasons:
            if reason not in ordered:
                ordered.append(reason)
    return ordered


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _safe_error_message(error: Exception) -> str:
    return str(error).replace("\n", " ").strip() or error.__class__.__name__
