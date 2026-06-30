from __future__ import annotations

from evaluation.retrieval import RetrievalMethodComparisonEntry
from evaluation.retrieval.comparison_v2 import select_retrieval_method_v2


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


def test_v2_comparison_selects_best_eligible_method_with_metadata() -> None:
    comparison = select_retrieval_method_v2(
        entries=[_entry("lexical_v1"), _entry("hybrid_v1", average_latency_ms=20.0)],
        benchmark_config_hash="bench",
        method_config_hashes={"lexical": "a", "hybrid": "b"},
        retrieval_contract_version="v2_method_aware",
        failure_taxonomy_version="v2_method_aware",
        boundary_contract_version="v2",
    )

    assert comparison.selected_method == "lexical_v1"
    assert comparison.benchmark_config_hash == "bench"
    assert comparison.method_summaries[0].retrieval_method == "lexical_v1"


def test_v2_comparison_returns_no_eligible_method_when_all_fail_gate() -> None:
    comparison = select_retrieval_method_v2(
        entries=[_entry("lexical_v1", eligible_for_rag=False), _entry("vector_v1", eligible_for_rag=False)],
        benchmark_config_hash="bench",
        method_config_hashes={"lexical": "a", "vector": "b"},
        retrieval_contract_version="v2_method_aware",
        failure_taxonomy_version="v2_method_aware",
        boundary_contract_version="v2",
    )

    assert comparison.selected_method is None
    assert comparison.selection_status == "no_eligible_method"
