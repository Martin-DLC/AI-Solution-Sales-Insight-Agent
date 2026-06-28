from __future__ import annotations

import pytest

from evaluation.retrieval.metrics import (
    evaluate_retrieval_case,
    forbidden_hit_rate,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
    solution_boundary_violation_rate,
    summarize_retrieval_results,
)
from evaluation.retrieval.models import (
    RetrievalCandidate,
    RetrievalCaseScore,
    RetrievalEvaluationCase,
    RetrievalMethod,
    RetrievalQueryType,
    RetrievalRunResult,
)


def sample_case(**overrides):
    payload = {
        "retrieval_case_id": "RET-001",
        "source_case_id": "DEV-01",
        "query_type": RetrievalQueryType.solution_discovery,
        "query": "客户希望改善续约风险识别与服务运营可视化。",
        "filters": {"industries": ["field_services"], "document_types": ["solution"]},
        "expected_relevant_document_ids": ["KB-SOL-001"],
        "expected_relevant_chunk_ids": [],
        "forbidden_document_ids": ["KB-SOL-999"],
        "required_solution_ids": ["service-risk-dashboard"],
        "forbidden_solution_ids": ["finance-copilot"],
        "minimum_relevant_hits": 1,
        "tags": ["dev", "service"],
        "notes": ["synthetic-case"],
    }
    payload.update(overrides)
    return RetrievalEvaluationCase.model_validate(payload)


def sample_candidate(**overrides):
    payload = {
        "rank": 1,
        "document_id": "KB-SOL-001",
        "chunk_id": "KB-SOL-001#chunk-001",
        "score": 0.92,
        "retrieval_method": RetrievalMethod.lexical_v1,
        "matched_terms": ["续约风险", "服务运营"],
        "metadata": {"document_type": "solution"},
        "citation_label": "KB-SOL-001 §overview",
        "solution_ids": ["service-risk-dashboard"],
    }
    payload.update(overrides)
    return RetrievalCandidate.model_validate(payload)


def test_recall_at_k() -> None:
    score = recall_at_k(
        relevant_ids={"A", "B"},
        retrieved_ids=["A", "Z", "B"],
        k=3,
    )

    assert score == 1.0


def test_precision_at_k() -> None:
    score = precision_at_k(
        relevant_ids={"A", "B"},
        retrieved_ids=["A", "Z", "B"],
        k=3,
    )

    assert score == pytest.approx(2 / 3)


def test_mrr() -> None:
    score = mean_reciprocal_rank(
        relevant_ids={"B"},
        retrieved_ids=["Z", "B", "C"],
    )

    assert score == 0.5


def test_forbidden_hit_rate() -> None:
    score = forbidden_hit_rate(
        forbidden_ids={"KB-BAD-001"},
        retrieved_document_ids=["KB-OK-001", "KB-BAD-001"],
    )

    assert score == 1.0


def test_solution_boundary_violation_rate() -> None:
    score = solution_boundary_violation_rate(
        required_solution_ids={"service-risk-dashboard"},
        forbidden_solution_ids={"finance-copilot"},
        candidate_solution_ids=[
            ["service-risk-dashboard"],
            ["finance-copilot"],
        ],
    )

    assert score == 0.5


def test_evaluate_retrieval_case_success_path() -> None:
    case = sample_case()
    result = RetrievalRunResult(
        retrieval_case_id=case.retrieval_case_id,
        retrieval_method=RetrievalMethod.lexical_v1,
        retrieved_candidates=[sample_candidate()],
        latency_ms=23,
    )

    score = evaluate_retrieval_case(case=case, result=result)

    assert score.recall_at_1 == 1.0
    assert score.recall_at_3 == 1.0
    assert score.recall_at_5 == 1.0
    assert score.precision_at_3 == 1.0
    assert score.reciprocal_rank == 1.0
    assert score.forbidden_hit is False
    assert score.solution_boundary_violation is False
    assert score.eligible_for_rag is True


def test_request_error_disqualifies_case() -> None:
    case = sample_case()
    result = RetrievalRunResult(
        retrieval_case_id=case.retrieval_case_id,
        retrieval_method=RetrievalMethod.lexical_v1,
        retrieved_candidates=[],
        latency_ms=5,
        error_type="request_error",
        error_message="provider timeout",
    )

    score = evaluate_retrieval_case(case=case, result=result)

    assert score.request_error is True
    assert score.eligible_for_rag is False
    assert "request_error" in score.disqualification_reasons


def test_summary_rejects_mixed_methods() -> None:
    with pytest.raises(ValueError, match="mixed methods"):
        summarize_retrieval_results(
            [
                RetrievalCaseScore(
                    retrieval_case_id="RET-001",
                    retrieval_method=RetrievalMethod.lexical_v1,
                    recall_at_1=1.0,
                    recall_at_3=1.0,
                    recall_at_5=1.0,
                    precision_at_3=1.0,
                    precision_at_5=1.0,
                    reciprocal_rank=1.0,
                    forbidden_hit=False,
                    solution_boundary_violation=False,
                    request_error=False,
                    latency_ms=10,
                    eligible_for_rag=True,
                ),
                RetrievalCaseScore(
                    retrieval_case_id="RET-002",
                    retrieval_method=RetrievalMethod.vector_v1,
                    recall_at_1=1.0,
                    recall_at_3=1.0,
                    recall_at_5=1.0,
                    precision_at_3=1.0,
                    precision_at_5=1.0,
                    reciprocal_rank=1.0,
                    forbidden_hit=False,
                    solution_boundary_violation=False,
                    request_error=False,
                    latency_ms=10,
                    eligible_for_rag=True,
                ),
            ]
        )


def test_summary_marks_pilot_gate_success() -> None:
    case = sample_case()
    result = RetrievalRunResult(
        retrieval_case_id=case.retrieval_case_id,
        retrieval_method=RetrievalMethod.lexical_v1,
        retrieved_candidates=[sample_candidate()],
        latency_ms=30,
    )
    score = evaluate_retrieval_case(case=case, result=result)

    summary = summarize_retrieval_results([score])

    assert summary.recall_at_5 == 1.0
    assert summary.forbidden_hit_rate == 0.0
    assert summary.solution_boundary_violation_rate == 0.0
    assert summary.request_error_count == 0
    assert summary.eligible_for_rag is True


def test_summary_marks_pilot_gate_failure_when_request_error_exists() -> None:
    case = sample_case()
    result = RetrievalRunResult(
        retrieval_case_id=case.retrieval_case_id,
        retrieval_method=RetrievalMethod.lexical_v1,
        retrieved_candidates=[],
        latency_ms=8,
        error_type="request_error",
        error_message="timeout",
    )
    score = evaluate_retrieval_case(case=case, result=result)

    summary = summarize_retrieval_results([score])

    assert summary.request_error_count == 1
    assert summary.eligible_for_rag is False
    assert "request_error" in summary.disqualification_reasons


def test_summary_uses_stable_reason_order() -> None:
    first = RetrievalCaseScore(
        retrieval_case_id="RET-001",
        retrieval_method=RetrievalMethod.lexical_v1,
        recall_at_1=0.0,
        recall_at_3=0.0,
        recall_at_5=0.0,
        precision_at_3=0.0,
        precision_at_5=0.0,
        reciprocal_rank=0.0,
        forbidden_hit=True,
        solution_boundary_violation=False,
        request_error=False,
        latency_ms=10,
        eligible_for_rag=False,
        disqualification_reasons=["recall_at_5_below_pilot_gate", "forbidden_hit_detected"],
    )
    second = RetrievalCaseScore(
        retrieval_case_id="RET-002",
        retrieval_method=RetrievalMethod.lexical_v1,
        recall_at_1=0.0,
        recall_at_3=0.0,
        recall_at_5=0.0,
        precision_at_3=0.0,
        precision_at_5=0.0,
        reciprocal_rank=0.0,
        forbidden_hit=False,
        solution_boundary_violation=True,
        request_error=False,
        latency_ms=10,
        eligible_for_rag=False,
        disqualification_reasons=["recall_at_5_below_pilot_gate", "solution_boundary_violation"],
    )

    summary = summarize_retrieval_results([first, second])

    assert summary.disqualification_reasons == [
        "recall_at_5_below_pilot_gate",
        "forbidden_hit_detected",
        "solution_boundary_violation",
    ]
