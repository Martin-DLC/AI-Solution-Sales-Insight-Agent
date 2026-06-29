from __future__ import annotations

from evaluation.retrieval.comparison import RetrievalMethodComparisonEntry, select_retrieval_method


def _entry(method: str, **overrides) -> RetrievalMethodComparisonEntry:
    payload = {
        "retrieval_method": method,
        "case_count": 16,
        "recall_at_1": 0.5,
        "recall_at_3": 0.7,
        "recall_at_5": 1.0,
        "precision_at_3": 0.8,
        "precision_at_5": 0.7,
        "mean_reciprocal_rank": 0.9,
        "forbidden_hit_rate": 0.0,
        "solution_boundary_violation_rate": 0.0,
        "average_latency_ms": 12.0,
        "eligible_for_rag": True,
        "disqualification_reasons": [],
        "failed_case_ids": [],
    }
    payload.update(overrides)
    return RetrievalMethodComparisonEntry.model_validate(payload)


def test_comparison_prefers_eligible_method() -> None:
    comparison = select_retrieval_method(
        [
            _entry("lexical_v1", eligible_for_rag=False, disqualification_reasons=["boundary"]),
            _entry("vector_v1", eligible_for_rag=True),
        ]
    )

    assert comparison.selected_method.value == "vector_v1"


def test_comparison_does_not_select_ineligible_method_even_if_metrics_higher() -> None:
    comparison = select_retrieval_method(
        [
            _entry("lexical_v1", recall_at_5=1.0, eligible_for_rag=False),
            _entry("vector_v1", recall_at_5=0.9, eligible_for_rag=True),
        ]
    )

    assert comparison.selected_method.value == "vector_v1"


def test_comparison_returns_null_when_no_method_is_eligible() -> None:
    comparison = select_retrieval_method(
        [
            _entry("lexical_v1", eligible_for_rag=False),
            _entry("vector_v1", eligible_for_rag=False),
            _entry("hybrid_v1", eligible_for_rag=False),
        ]
    )

    assert comparison.selected_method is None
    assert comparison.selection_status == "no_eligible_method"


def test_comparison_does_not_default_to_hybrid() -> None:
    comparison = select_retrieval_method(
        [
            _entry("lexical_v1", recall_at_5=1.0, average_latency_ms=5.0),
            _entry("hybrid_v1", recall_at_5=1.0, average_latency_ms=25.0),
        ]
    )

    assert comparison.selected_method.value == "lexical_v1"
