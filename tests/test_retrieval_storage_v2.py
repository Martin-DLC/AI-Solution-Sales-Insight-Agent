from __future__ import annotations

from evaluation.retrieval.storage_v2 import (
    NON_DETERMINISTIC_RESULT_FIELDS_V2,
    compare_payloads_ignoring_runtime_fields,
    formal_v2_output_paths,
    formal_v2_results_exist,
)


def test_formal_v2_output_paths_are_declared_but_not_present() -> None:
    paths = formal_v2_output_paths()

    assert sorted(paths) == [
        "comparison",
        "hybrid_results",
        "hybrid_summary",
        "lexical_results",
        "lexical_summary",
        "vector_results",
        "vector_summary",
    ]
    assert formal_v2_results_exist() is False


def test_compare_payloads_ignores_only_runtime_fields() -> None:
    left = {"generated_at": "a", "average_latency_ms": 12, "stable": 1}
    right = {"generated_at": "b", "average_latency_ms": 99, "stable": 1}
    drift = {"generated_at": "b", "average_latency_ms": 99, "stable": 2}

    assert compare_payloads_ignoring_runtime_fields(left, right) == []
    assert compare_payloads_ignoring_runtime_fields(left, drift) == ["stable"]
    assert "generated_at" in NON_DETERMINISTIC_RESULT_FIELDS_V2
