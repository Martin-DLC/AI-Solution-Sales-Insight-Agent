from __future__ import annotations

from statistics import mean

from evaluation.retrieval.models import RetrievalCaseScore, RetrievalMethod
from evaluation.retrieval.runner_v2 import (
    RetrievalFormalCaseMetricsV2,
    RetrievalFormalCaseResultV2,
    aggregate_summary_metrics_v2,
    recompute_summary_metrics_from_formal_results_v2,
)


def _case_score(case_id: str, recall_at_5: float) -> RetrievalCaseScore:
    return RetrievalCaseScore(
        retrieval_case_id=case_id,
        retrieval_method=RetrievalMethod.lexical_v1,
        recall_at_1=0.0,
        recall_at_3=0.0,
        recall_at_5=recall_at_5,
        precision_at_3=0.0,
        precision_at_5=0.0,
        reciprocal_rank=0.0,
        forbidden_hit=False,
        solution_boundary_violation=False,
        request_error=False,
        latency_ms=1,
        eligible_for_rag=True,
        disqualification_reasons=[],
    )


def _formal_result(case_score: RetrievalCaseScore) -> RetrievalFormalCaseResultV2:
    return RetrievalFormalCaseResultV2(
        retrieval_case_id=case_score.retrieval_case_id,
        source_case_id="DEV-TEST",
        retrieval_method=case_score.retrieval_method,
        query_type="solution_discovery",
        candidate_count=0,
        candidates=[],
        case_metrics=RetrievalFormalCaseMetricsV2(
            recall_at_1=case_score.recall_at_1,
            recall_at_3=case_score.recall_at_3,
            recall_at_5=case_score.recall_at_5,
            precision_at_3=case_score.precision_at_3,
            precision_at_5=case_score.precision_at_5,
            reciprocal_rank=case_score.reciprocal_rank,
            forbidden_hit=case_score.forbidden_hit,
            solution_boundary_violation=case_score.solution_boundary_violation,
            request_error=case_score.request_error,
        ),
        failure_reasons=[],
        passed_blocking_gate=True,
        latency_ms=case_score.latency_ms,
        error_type=None,
        error_message=None,
    )


def test_attempt1_recall_regression_comes_from_two_float_aggregation_paths() -> None:
    recall_values = [
        1.0,
        1.0,
        1.0,
        1.0,
        2.0 / 3.0,
        3.0 / 4.0,
        1.0,
        1.0,
        1.0,
        3.0 / 4.0,
        3.0 / 4.0,
        1.0,
        1.0,
        3.0 / 4.0,
        3.0 / 4.0,
        3.0 / 4.0,
    ]
    case_scores = [_case_score(f"RET2-{index:03d}", value) for index, value in enumerate(recall_values, start=1)]

    old_summary_value = mean(score.recall_at_5 for score in case_scores)
    old_recomputed_value = sum(score.recall_at_5 for score in case_scores) / len(case_scores)

    assert old_summary_value != old_recomputed_value

    summary = aggregate_summary_metrics_v2(case_scores)
    recomputed = recompute_summary_metrics_from_formal_results_v2([_formal_result(score) for score in case_scores])

    assert summary.recall_at_5 == old_summary_value
    assert recomputed["recall_at_5"] == old_summary_value
    assert recomputed["recall_at_5"] == summary.recall_at_5


def test_recompute_summary_metrics_v2_uses_same_macro_average_as_summary() -> None:
    case_scores = [
        _case_score("RET2-001", 1.0),
        _case_score("RET2-002", 0.5),
        _case_score("RET2-003", 0.0),
    ]

    summary = aggregate_summary_metrics_v2(case_scores)
    recomputed = recompute_summary_metrics_from_formal_results_v2([_formal_result(score) for score in case_scores])

    assert summary.recall_at_5 == 0.5
    assert recomputed["recall_at_5"] == 0.5
    assert recomputed["case_count"] == 3
