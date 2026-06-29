from __future__ import annotations

from typing import Any

from pydantic import Field

from evaluation.retrieval.metrics import evaluate_retrieval_case, summarize_retrieval_results
from evaluation.retrieval.models import (
    RetrievalCaseScore,
    RetrievalEvaluationCase,
    RetrievalFormalCaseResult,
    RetrievalFormalSummary,
    RetrievalEvaluationSummary,
    RetrievalMethod,
    RetrievalRunResult,
    RetrievalDependencyVersions,
    summarize_case_mix,
)
from knowledge_base.models import KnowledgeBaseManifest
from knowledge_base.dataset import DemoSolutionScope
from knowledge_base.retrieval.lexical import LexicalBaselineConfig, WeightedBM25Retriever
from knowledge_base.retrieval.vector import VectorBaselineConfig
from knowledge_base.retrieval.hybrid import HybridBaselineConfig
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
    retriever: Any,
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


def build_formal_case_results(report: LexicalRetrievalEvaluationReport) -> list[RetrievalFormalCaseResult]:
    case_scores_by_id = {score.retrieval_case_id: score for score in report.case_scores}
    run_results_by_id = {result.retrieval_case_id: result for result in report.run_results}
    results: list[RetrievalFormalCaseResult] = []
    for case_result in report.case_results:
        case_score = case_scores_by_id[case_result.retrieval_case_id]
        run_result = run_results_by_id[case_result.retrieval_case_id]
        results.append(
            RetrievalFormalCaseResult(
                retrieval_case_id=case_result.retrieval_case_id,
                query_type=case_result.query_type,
                retrieval_method=case_result.retrieval_method,
                top_k=case_result.top_k,
                retrieved_candidates=case_result.retrieved_candidates,
                recall_at_1=case_score.recall_at_1,
                recall_at_3=case_score.recall_at_3,
                recall_at_5=case_score.recall_at_5,
                precision_at_3=case_score.precision_at_3,
                precision_at_5=case_score.precision_at_5,
                reciprocal_rank=case_score.reciprocal_rank,
                forbidden_hit=case_score.forbidden_hit,
                solution_boundary_violation=case_score.solution_boundary_violation,
                passed_blocking_gate=case_result.passed_blocking_gate,
                failure_reasons=list(case_result.failure_reasons),
                latency_ms=run_result.latency_ms,
                error_type=run_result.error_type,
                error_message=run_result.error_message,
            )
        )
    return results


def build_formal_summary_payload(
    *,
    cases: list[RetrievalEvaluationCase],
    config: VectorBaselineConfig | HybridBaselineConfig,
    config_file: str,
    manifest: KnowledgeBaseManifest,
    demo_scope: DemoSolutionScope,
    report: LexicalRetrievalEvaluationReport,
    model_name: str,
    resolved_model_revision: str,
    embedding_dimension: int,
    dependency_versions: dict[str, str | None],
    corpus_embedding_count: int,
    cache_hit_count: int,
    cache_miss_count: int,
    corpus_embedding_build_ms: int,
    limitations: list[str],
) -> RetrievalFormalSummary:
    failed_case_ids = [
        result.retrieval_case_id for result in report.case_results if not result.passed_blocking_gate
    ]
    return RetrievalFormalSummary(
        baseline_version=config.baseline_version,
        retrieval_method=RetrievalMethod("vector_v1" if config.baseline_version == "vector_v1" else "hybrid_v1"),
        config_file=config_file,
        knowledge_base_version=manifest.knowledge_base_version,
        demo_solution_scope_version=demo_scope.scope_version,
        model_name=model_name,
        resolved_model_revision=resolved_model_revision,
        embedding_dimension=embedding_dimension,
        dependency_versions=RetrievalDependencyVersions.model_validate(dependency_versions),
        case_count=report.summary.case_count,
        query_type_counts=summarize_case_mix(cases),
        recall_at_1=report.summary.recall_at_1,
        recall_at_3=report.summary.recall_at_3,
        recall_at_5=report.summary.recall_at_5,
        precision_at_3=report.summary.precision_at_3,
        precision_at_5=report.summary.precision_at_5,
        mean_reciprocal_rank=report.summary.mean_reciprocal_rank,
        forbidden_hit_rate=report.summary.forbidden_hit_rate,
        solution_boundary_violation_rate=report.summary.solution_boundary_violation_rate,
        average_latency_ms=report.summary.average_latency_ms,
        corpus_embedding_count=corpus_embedding_count,
        cache_hit_count=cache_hit_count,
        cache_miss_count=cache_miss_count,
        corpus_embedding_build_ms=corpus_embedding_build_ms,
        eligible_for_rag=report.summary.eligible_for_rag,
        disqualification_reasons=list(report.summary.disqualification_reasons),
        failed_case_ids=failed_case_ids,
        generated_from_synthetic_data=True,
        limitations=limitations,
    )


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
