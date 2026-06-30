from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from pydantic import Field

from evaluation.retrieval.failure_taxonomy import classify_retrieval_failures_v2
from evaluation.retrieval.metrics import (
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
    summarize_retrieval_results,
)
from evaluation.retrieval.models import (
    RetrievalCandidate,
    RetrievalCaseScore,
    RetrievalEvaluationSummary,
    RetrievalMethod,
    RetrievalRunResult,
)
from evaluation.retrieval.contracts_v2 import (
    RetrievalEvaluationCaseV2,
    RetrievalRuntimeContextV2,
    evaluate_candidate_boundary_v2,
)
from knowledge_base import KnowledgeChunkV2, KnowledgeDocumentV2
from knowledge_base.models import KnowledgeChunk, KnowledgeDocument
from schemas.common_models import StrictBaseModel


@dataclass(frozen=True)
class RetrievalRuntimeInputV2:
    query: str
    operational_filters: Mapping[str, object]
    operational_solution_scope: tuple[str, ...]
    allowed_document_types: tuple[str, ...]
    industries: tuple[str, ...]
    tags: tuple[str, ...]
    effective_on: date
    top_k: int


class RetrievalRunnerV2CaseResult(StrictBaseModel):
    retrieval_case_id: str
    source_case_id: str
    retrieval_method: RetrievalMethod
    top_k: int
    runtime_input: dict[str, Any]
    retrieved_candidates: list[dict[str, Any]] = Field(default_factory=list)
    case_metrics: dict[str, Any]
    passed_blocking_gate: bool
    failure_reasons: list[str] = Field(default_factory=list)
    failure_taxonomy: list[str] = Field(default_factory=list)
    runtime_gold_leak_detected: bool = False
    candidate_boundary_reasons: list[list[str]] = Field(default_factory=list)


class RetrievalRunnerV2Report(StrictBaseModel):
    case_results: list[RetrievalRunnerV2CaseResult] = Field(default_factory=list)
    run_results: list[RetrievalRunResult] = Field(default_factory=list)
    case_scores: list[RetrievalCaseScore] = Field(default_factory=list)
    summary: RetrievalEvaluationSummary


def make_runtime_input_v2(
    *,
    case: RetrievalEvaluationCaseV2,
    top_k: int,
) -> RetrievalRuntimeInputV2:
    return RetrievalRuntimeInputV2(
        query=case.query,
        operational_filters=dict(case.runtime_context.operational_filters),
        operational_solution_scope=tuple(case.runtime_context.operational_solution_scope),
        allowed_document_types=tuple(case.runtime_context.allowed_document_types),
        industries=tuple(case.runtime_context.industries),
        tags=tuple(case.runtime_context.tags),
        effective_on=case.runtime_context.effective_on or date.today(),
        top_k=top_k,
    )


def runtime_input_to_retriever_filters(runtime_input: RetrievalRuntimeInputV2) -> dict[str, object]:
    filters = dict(runtime_input.operational_filters)
    filters["solution_ids"] = list(runtime_input.operational_solution_scope)
    if runtime_input.allowed_document_types:
        filters["document_types"] = list(runtime_input.allowed_document_types)
    if runtime_input.industries:
        filters["industries"] = list(runtime_input.industries)
    if runtime_input.tags:
        filters["tags"] = list(runtime_input.tags)
    filters["effective_on"] = runtime_input.effective_on.isoformat()
    return filters


def runtime_input_has_gold_leak(runtime_input: RetrievalRuntimeInputV2) -> bool:
    forbidden = {
        "expected_relevant_document_ids",
        "expected_relevant_chunk_ids",
        "forbidden_document_ids",
        "forbidden_solution_ids",
        "minimum_relevant_hits",
    }
    return bool(forbidden & set(runtime_input.operational_filters))


def project_v2_documents_to_legacy_runtime_inputs(
    documents: list[KnowledgeDocumentV2],
) -> list[KnowledgeDocument]:
    return [
        KnowledgeDocument.model_validate(
            {
                "document_id": document.document_id,
                "title": document.title,
                "document_type": document.document_type,
                "status": document.status,
                "version": document.version,
                "effective_from": document.effective_from,
                "effective_until": document.effective_until,
                "owner": document.owner,
                "summary": document.summary,
                "content": document.content,
                "tags": list(document.tags),
                "industries": list(document.industries),
                "solution_ids": list(document.applicable_solution_ids),
                "source_uri": document.source_uri,
                "confidentiality": document.confidentiality,
                "created_at": document.created_at,
                "updated_at": document.updated_at,
            }
        )
        for document in documents
    ]


def project_v2_chunks_to_legacy_runtime_inputs(
    chunks: list[KnowledgeChunkV2],
) -> list[KnowledgeChunk]:
    return [
        KnowledgeChunk.model_validate(
            {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "document_type": chunk.document_type,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "token_estimate": chunk.token_estimate,
                "tags": list(chunk.tags),
                "industries": list(chunk.industries),
                "solution_ids": list(chunk.applicable_solution_ids),
                "metadata": dict(chunk.metadata),
                "citation_label": chunk.citation_label,
            }
        )
        for chunk in chunks
    ]


def run_retrieval_evaluation_v2(
    *,
    cases: list[RetrievalEvaluationCaseV2],
    retriever: Any,
    method_id: str,
    top_k: int,
    documents: list[KnowledgeDocumentV2],
    chunks: list[KnowledgeChunkV2],
) -> RetrievalRunnerV2Report:
    retrieval_method = RetrievalMethod(method_id)
    documents_by_id = {document.document_id: document for document in documents}
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    run_results: list[RetrievalRunResult] = []
    case_scores: list[RetrievalCaseScore] = []
    case_results: list[RetrievalRunnerV2CaseResult] = []

    for case in cases:
        runtime_input = make_runtime_input_v2(case=case, top_k=top_k)
        runtime_filters = runtime_input_to_retriever_filters(runtime_input)
        try:
            candidates = retriever.retrieve(
                query=runtime_input.query,
                filters=runtime_filters,
                top_k=runtime_input.top_k,
            )
            debug = _build_debug_payload(
                retrieval_method=method_id,
                query=runtime_input.query,
                candidates=candidates,
                retriever_debug=getattr(retriever, "last_retrieval_debug", {}),
                retriever=retriever,
            )
            run_result = RetrievalRunResult(
                retrieval_case_id=case.retrieval_case_id,
                retrieval_method=retrieval_method,
                retrieved_candidates=candidates,
                latency_ms=int(debug.get("elapsed_ms", 0)),
            )
        except Exception as exc:
            debug = _build_debug_payload(
                retrieval_method=method_id,
                query=runtime_input.query,
                candidates=[],
                retriever_debug={},
                retriever=retriever,
            )
            run_result = RetrievalRunResult(
                retrieval_case_id=case.retrieval_case_id,
                retrieval_method=retrieval_method,
                retrieved_candidates=[],
                latency_ms=0,
                error_type="retrieval_error",
                error_message=_safe_error_message(exc),
            )

        case_score, candidate_boundary_reasons = evaluate_retrieval_case_v2(
            case=case,
            result=run_result,
            documents_by_id=documents_by_id,
            chunks_by_id=chunks_by_id,
        )
        failure_taxonomy = classify_retrieval_failures_v2(
            query=runtime_input.query,
            retrieval_method=method_id,
            result=run_result,
            metrics={
                "recall_at_5": case_score.recall_at_5,
                "relevant_hit_count": _count_relevant_hits_v2(case=case, result=run_result),
                "forbidden_hit": case_score.forbidden_hit,
                "solution_boundary_violation": case_score.solution_boundary_violation,
            },
            debug=debug,
            minimum_relevant_hits=case.evaluation_gold.minimum_relevant_hits,
        )
        passed_blocking_gate = not failure_taxonomy
        case_score.eligible_for_rag = passed_blocking_gate
        case_score.disqualification_reasons = list(failure_taxonomy)

        run_results.append(run_result)
        case_scores.append(case_score)
        case_results.append(
            RetrievalRunnerV2CaseResult(
                retrieval_case_id=case.retrieval_case_id,
                source_case_id=case.source_case_id,
                retrieval_method=retrieval_method,
                top_k=runtime_input.top_k,
                runtime_input={
                    "query": runtime_input.query,
                    "operational_filters": dict(runtime_input.operational_filters),
                    "operational_solution_scope": list(runtime_input.operational_solution_scope),
                    "allowed_document_types": list(runtime_input.allowed_document_types),
                    "industries": list(runtime_input.industries),
                    "tags": list(runtime_input.tags),
                    "effective_on": runtime_input.effective_on.isoformat(),
                    "top_k": runtime_input.top_k,
                },
                retrieved_candidates=[candidate.model_dump(mode="json") for candidate in run_result.retrieved_candidates],
                case_metrics=case_score.model_dump(mode="json"),
                passed_blocking_gate=passed_blocking_gate,
                failure_reasons=list(case_score.disqualification_reasons),
                failure_taxonomy=list(failure_taxonomy),
                runtime_gold_leak_detected=runtime_input_has_gold_leak(runtime_input),
                candidate_boundary_reasons=candidate_boundary_reasons,
            )
        )

    summary = summarize_retrieval_results(case_scores)
    summary.eligible_for_rag = _passes_blocking_gate_v2(summary=summary, case_results=case_results)
    summary.disqualification_reasons = _summarize_failure_reasons(case_results)
    return RetrievalRunnerV2Report(
        case_results=case_results,
        run_results=run_results,
        case_scores=case_scores,
        summary=summary,
    )


def evaluate_retrieval_case_v2(
    *,
    case: RetrievalEvaluationCaseV2,
    result: RetrievalRunResult,
    documents_by_id: dict[str, KnowledgeDocumentV2],
    chunks_by_id: dict[str, KnowledgeChunkV2],
) -> tuple[RetrievalCaseScore, list[list[str]]]:
    relevant_ids = set(case.evaluation_gold.expected_relevant_document_ids) | set(case.evaluation_gold.expected_relevant_chunk_ids)
    retrieved_document_ids = [candidate.document_id for candidate in result.retrieved_candidates]
    retrieved_ids = [
        _candidate_relevance_id_v2(
            document_id=candidate.document_id,
            chunk_id=candidate.chunk_id,
            expected_document_ids=set(case.evaluation_gold.expected_relevant_document_ids),
            expected_chunk_ids=set(case.evaluation_gold.expected_relevant_chunk_ids),
        )
        for candidate in result.retrieved_candidates
    ]
    boundary_reasons: list[list[str]] = []
    forbidden_hit = any(document_id in set(case.evaluation_gold.forbidden_document_ids) for document_id in retrieved_document_ids)
    solution_boundary_violation = False
    for candidate in result.retrieved_candidates:
        document = documents_by_id[candidate.document_id]
        chunk = chunks_by_id.get(candidate.chunk_id) if candidate.chunk_id else None
        decision = evaluate_candidate_boundary_v2(case=case, document=document, chunk=chunk)
        boundary_reasons.append(list(decision.reasons))
        if not decision.candidate_allowed:
            solution_boundary_violation = True

    reasons: list[str] = []
    request_error = result.error_type is not None
    recall5 = recall_at_k(relevant_ids=relevant_ids, retrieved_ids=retrieved_ids, k=5)
    relevant_hit_count = _count_relevant_hits_v2(case=case, result=result)
    if request_error:
        reasons.append("retrieval_error")
    if recall5 < 1.0:
        reasons.append("recall_at_5_below_pilot_gate")
    if forbidden_hit:
        reasons.append("forbidden_hit_detected")
    if solution_boundary_violation:
        reasons.append("solution_boundary_violation")
    if relevant_hit_count < case.evaluation_gold.minimum_relevant_hits:
        reasons.append("minimum_relevant_hits_not_met")

    return (
        RetrievalCaseScore(
            retrieval_case_id=case.retrieval_case_id,
            retrieval_method=result.retrieval_method,
            recall_at_1=recall_at_k(relevant_ids=relevant_ids, retrieved_ids=retrieved_ids, k=1),
            recall_at_3=recall_at_k(relevant_ids=relevant_ids, retrieved_ids=retrieved_ids, k=3),
            recall_at_5=recall5,
            precision_at_3=precision_at_k(relevant_ids=relevant_ids, retrieved_ids=retrieved_ids, k=3),
            precision_at_5=precision_at_k(relevant_ids=relevant_ids, retrieved_ids=retrieved_ids, k=5),
            reciprocal_rank=mean_reciprocal_rank(relevant_ids=relevant_ids, retrieved_ids=retrieved_ids),
            forbidden_hit=forbidden_hit,
            solution_boundary_violation=solution_boundary_violation,
            request_error=request_error,
            latency_ms=result.latency_ms,
            eligible_for_rag=not reasons,
            disqualification_reasons=reasons,
        ),
        boundary_reasons,
    )


def _count_relevant_hits_v2(
    *,
    case: RetrievalEvaluationCaseV2,
    result: RetrievalRunResult,
) -> int:
    expected_document_ids = set(case.evaluation_gold.expected_relevant_document_ids)
    expected_chunk_ids = set(case.evaluation_gold.expected_relevant_chunk_ids)
    hits = 0
    for candidate in result.retrieved_candidates[:5]:
        if candidate.chunk_id and candidate.chunk_id in expected_chunk_ids:
            hits += 1
            continue
        if candidate.document_id in expected_document_ids:
            hits += 1
    return hits


def _candidate_relevance_id_v2(
    *,
    document_id: str,
    chunk_id: str | None,
    expected_document_ids: set[str],
    expected_chunk_ids: set[str],
) -> str:
    if chunk_id and chunk_id in expected_chunk_ids:
        return chunk_id
    if document_id in expected_document_ids:
        return document_id
    return chunk_id or document_id


def _passes_blocking_gate_v2(
    *,
    summary: RetrievalEvaluationSummary,
    case_results: list[RetrievalRunnerV2CaseResult],
) -> bool:
    return (
        summary.recall_at_5 == 1.0
        and summary.forbidden_hit_rate == 0
        and summary.solution_boundary_violation_rate == 0
        and summary.request_error_count == 0
        and all(result.passed_blocking_gate for result in case_results)
    )


def _summarize_failure_reasons(case_results: list[RetrievalRunnerV2CaseResult]) -> list[str]:
    ordered: list[str] = []
    for case_result in case_results:
        for reason in case_result.failure_taxonomy:
            if reason not in ordered:
                ordered.append(reason)
    return ordered


def _build_debug_payload(
    *,
    retrieval_method: str,
    query: str,
    candidates: list[RetrievalCandidate],
    retriever_debug: Mapping[str, Any],
    retriever: Any,
) -> dict[str, Any]:
    elapsed_ms = int(retriever_debug.get("elapsed_ms", 0) or 0)
    payload: dict[str, Any] = {
        "raw_query_present": bool(query),
        "normalized_query_present": bool("".join(query.split())),
        "candidate_count": len(candidates),
        "retrieval_method": retrieval_method,
        "elapsed_ms": elapsed_ms,
        "operational_filter_excluded_all": bool(query.strip()) and int(retriever_debug.get("filtered_candidate_count", 0) or 0) == 0,
    }
    if retrieval_method == "lexical_v1":
        payload["lexical_query_tokens"] = list(retriever_debug.get("query_tokens", []))
        payload["lexical_matched_terms"] = [term for candidate in candidates for term in candidate.matched_terms]
    elif retrieval_method == "vector_v1":
        payload["query_embedding_generated"] = bool(query.strip())
        payload["embedding_dimension"] = getattr(getattr(retriever, "_embedding_provider", None), "dimension", None)
    elif retrieval_method == "hybrid_v1":
        lexical_debug = getattr(getattr(retriever, "_lexical_retriever", None), "last_retrieval_debug", {})
        vector_debug = getattr(getattr(retriever, "_vector_retriever", None), "last_retrieval_debug", {})
        payload["lexical_candidate_count"] = int(lexical_debug.get("filtered_candidate_count", 0) or 0)
        payload["vector_candidate_count"] = int(vector_debug.get("filtered_candidate_count", 0) or 0)
        payload["fused_candidate_count"] = len(candidates)
    return payload


def _safe_error_message(error: Exception) -> str:
    return str(error).replace("\n", " ").strip() or error.__class__.__name__
