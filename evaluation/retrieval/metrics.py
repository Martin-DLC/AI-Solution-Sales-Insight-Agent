from __future__ import annotations

from statistics import mean

from evaluation.retrieval.models import (
    RetrievalCaseScore,
    RetrievalEvaluationCase,
    RetrievalEvaluationSummary,
    RetrievalMethod,
    RetrievalRunResult,
)


def recall_at_k(
    *,
    relevant_ids: set[str],
    retrieved_ids: list[str],
    k: int,
) -> float:
    if not relevant_ids:
        return 0.0
    hits = len(relevant_ids & set(retrieved_ids[:k]))
    return hits / len(relevant_ids)


def precision_at_k(
    *,
    relevant_ids: set[str],
    retrieved_ids: list[str],
    k: int,
) -> float:
    window = retrieved_ids[:k]
    if not window:
        return 0.0
    hits = len(relevant_ids & set(window))
    return hits / len(window)


def mean_reciprocal_rank(
    *,
    relevant_ids: set[str],
    retrieved_ids: list[str],
) -> float:
    for index, item_id in enumerate(retrieved_ids, start=1):
        if item_id in relevant_ids:
            return 1.0 / index
    return 0.0


def forbidden_hit_rate(
    *,
    forbidden_ids: set[str],
    retrieved_document_ids: list[str],
) -> float:
    if not forbidden_ids:
        return 0.0
    return 1.0 if any(document_id in forbidden_ids for document_id in retrieved_document_ids) else 0.0


def solution_boundary_violation_rate(
    *,
    required_solution_ids: set[str],
    forbidden_solution_ids: set[str],
    candidate_solution_ids: list[list[str]],
) -> float:
    if not candidate_solution_ids:
        return 0.0

    violations = 0
    for solution_ids in candidate_solution_ids:
        solution_set = set(solution_ids)
        violates_required = bool(required_solution_ids) and not solution_set.issubset(required_solution_ids)
        violates_forbidden = bool(solution_set & forbidden_solution_ids)
        if violates_required or violates_forbidden:
            violations += 1
    return violations / len(candidate_solution_ids)


def evaluate_retrieval_case(
    *,
    case: RetrievalEvaluationCase,
    result: RetrievalRunResult,
) -> RetrievalCaseScore:
    relevant_ids = set(case.expected_relevant_document_ids) | set(case.expected_relevant_chunk_ids)
    retrieved_document_ids = [candidate.document_id for candidate in result.retrieved_candidates]
    retrieved_ids = [
        _candidate_relevance_id(
            document_id=candidate.document_id,
            chunk_id=candidate.chunk_id,
            expected_document_ids=set(case.expected_relevant_document_ids),
            expected_chunk_ids=set(case.expected_relevant_chunk_ids),
        )
        for candidate in result.retrieved_candidates
    ]
    candidate_solution_ids = [candidate.solution_ids for candidate in result.retrieved_candidates]

    request_error = result.error_type is not None
    forbidden_rate = forbidden_hit_rate(
        forbidden_ids=set(case.forbidden_document_ids),
        retrieved_document_ids=retrieved_document_ids,
    )
    boundary_rate = solution_boundary_violation_rate(
        required_solution_ids=set(case.required_solution_ids),
        forbidden_solution_ids=set(case.forbidden_solution_ids),
        candidate_solution_ids=candidate_solution_ids,
    )

    reasons: list[str] = []
    if request_error:
        reasons.append("request_error")
    if recall_at_k(relevant_ids=relevant_ids, retrieved_ids=retrieved_ids, k=5) < 1.0:
        reasons.append("recall_at_5_below_pilot_gate")
    if forbidden_rate > 0:
        reasons.append("forbidden_hit_detected")
    if boundary_rate > 0:
        reasons.append("solution_boundary_violation")

    return RetrievalCaseScore(
        retrieval_case_id=case.retrieval_case_id,
        retrieval_method=result.retrieval_method,
        recall_at_1=recall_at_k(relevant_ids=relevant_ids, retrieved_ids=retrieved_ids, k=1),
        recall_at_3=recall_at_k(relevant_ids=relevant_ids, retrieved_ids=retrieved_ids, k=3),
        recall_at_5=recall_at_k(relevant_ids=relevant_ids, retrieved_ids=retrieved_ids, k=5),
        precision_at_3=precision_at_k(relevant_ids=relevant_ids, retrieved_ids=retrieved_ids, k=3),
        precision_at_5=precision_at_k(relevant_ids=relevant_ids, retrieved_ids=retrieved_ids, k=5),
        reciprocal_rank=mean_reciprocal_rank(relevant_ids=relevant_ids, retrieved_ids=retrieved_ids),
        forbidden_hit=forbidden_rate > 0,
        solution_boundary_violation=boundary_rate > 0,
        request_error=request_error,
        latency_ms=result.latency_ms,
        eligible_for_rag=not reasons,
        disqualification_reasons=reasons,
    )


def summarize_retrieval_results(
    results: list[RetrievalCaseScore],
) -> RetrievalEvaluationSummary:
    if not results:
        raise ValueError("Retrieval summary requires at least one case result.")

    methods = {result.retrieval_method for result in results}
    if len(methods) != 1:
        raise ValueError("Retrieval summary requires a single retrieval_method; mixed methods are not supported.")

    request_error_count = sum(1 for result in results if result.request_error)
    disqualification_reasons: list[str] = []
    for result in results:
        for reason in result.disqualification_reasons:
            if reason not in disqualification_reasons:
                disqualification_reasons.append(reason)

    summary = RetrievalEvaluationSummary(
        retrieval_method=next(iter(methods)),
        case_count=len(results),
        recall_at_1=mean(result.recall_at_1 for result in results),
        recall_at_3=mean(result.recall_at_3 for result in results),
        recall_at_5=mean(result.recall_at_5 for result in results),
        precision_at_3=mean(result.precision_at_3 for result in results),
        precision_at_5=mean(result.precision_at_5 for result in results),
        mean_reciprocal_rank=mean(result.reciprocal_rank for result in results),
        forbidden_hit_rate=mean(1.0 if result.forbidden_hit else 0.0 for result in results),
        solution_boundary_violation_rate=mean(
            1.0 if result.solution_boundary_violation else 0.0 for result in results
        ),
        average_latency_ms=mean(result.latency_ms for result in results),
        request_error_count=request_error_count,
        eligible_for_rag=False,
        disqualification_reasons=disqualification_reasons,
    )
    summary.eligible_for_rag = _passes_pilot_gate(summary)
    return summary


def _passes_pilot_gate(summary: RetrievalEvaluationSummary) -> bool:
    return (
        summary.recall_at_5 == 1.0
        and summary.forbidden_hit_rate == 0
        and summary.solution_boundary_violation_rate == 0
        and summary.request_error_count == 0
    )


def _candidate_relevance_id(
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
