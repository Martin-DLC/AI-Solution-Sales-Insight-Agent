from __future__ import annotations

import json
from pathlib import Path

from evaluation.retrieval.storage_v2 import compute_file_sha256


BASE_DIR = Path("data/evaluation/retrieval")
METHODS = ("lexical", "vector", "hybrid")
METRICS = (
    "recall_at_1",
    "recall_at_3",
    "recall_at_5",
    "precision_at_3",
    "precision_at_5",
    "mean_reciprocal_rank",
    "forbidden_hit_rate",
    "solution_boundary_violation_rate",
)

EXPECTED_DELTAS = {
    "lexical": {
        "recall_at_1": 0.005208333333333315,
        "recall_at_3": -0.02083333333333337,
        "recall_at_5": -0.03645833333333337,
        "precision_at_3": -0.04166666666666663,
        "precision_at_5": -0.025000000000000022,
        "mean_reciprocal_rank": 0.0,
        "forbidden_hit_rate": 0.0,
        "solution_boundary_violation_rate": -0.25,
    },
    "vector": {
        "recall_at_1": 0.005208333333333343,
        "recall_at_3": -0.02083333333333337,
        "recall_at_5": -0.03645833333333337,
        "precision_at_3": -0.04166666666666674,
        "precision_at_5": -0.025000000000000022,
        "mean_reciprocal_rank": 0.0,
        "forbidden_hit_rate": -0.0625,
        "solution_boundary_violation_rate": -0.4375,
    },
    "hybrid": {
        "recall_at_1": 0.005208333333333315,
        "recall_at_3": -0.00520833333333337,
        "recall_at_5": -0.02083333333333337,
        "precision_at_3": -0.02083333333333337,
        "precision_at_5": -0.012500000000000067,
        "mean_reciprocal_rank": 0.0,
        "forbidden_hit_rate": 0.0,
        "solution_boundary_violation_rate": -0.375,
    },
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _v1_summary(method: str) -> dict:
    return _load_json(BASE_DIR / f"{method}_baseline_summary.v1.json")


def _v2_summary(method: str) -> dict:
    return _load_json(BASE_DIR / f"{method}_baseline_summary.v2.json")


def _v1_config(method: str) -> dict:
    return _load_json(BASE_DIR / f"{method}_baseline_config.v1.json")


def _v2_config(method: str) -> dict:
    return _load_json(BASE_DIR / f"{method}_baseline_config.v2.json")


def test_v1_and_v2_keep_the_same_retriever_algorithm_parameters() -> None:
    for method in METHODS:
        assert _v2_config(method)["algorithm_config"] == _v1_config(method)


def test_v2_comparison_references_frozen_v2_method_config_hashes() -> None:
    comparison = _load_json(BASE_DIR / "retrieval_method_comparison.v2.json")
    for method in METHODS:
        method_key = method
        assert comparison["method_config_hashes"][method_key] == compute_file_sha256(
            BASE_DIR / f"{method}_baseline_config.v2.json"
        )


def test_v2_configs_preserve_frozen_v1_source_config_hashes() -> None:
    for method in METHODS:
        v2_config = _v2_config(method)
        assert v2_config["source_v1_config_hash"] == compute_file_sha256(BASE_DIR / f"{method}_baseline_config.v1.json")


def test_v1_to_v2_metric_deltas_match_the_frozen_formal_results() -> None:
    for method in METHODS:
        v1_summary = _v1_summary(method)
        v2_summary = _v2_summary(method)
        for metric in METRICS:
            delta = v2_summary[metric] - v1_summary[metric]
            assert delta == EXPECTED_DELTAS[method][metric]


def test_failed_case_counts_and_eligibility_changes_match_frozen_summaries() -> None:
    expected_failed_case_counts = {
        "lexical": (7, 3),
        "vector": (16, 3),
        "hybrid": (16, 2),
    }
    for method in METHODS:
        v1_summary = _v1_summary(method)
        v2_summary = _v2_summary(method)
        assert (len(v1_summary["failed_case_ids"]), len(v2_summary["failed_case_ids"])) == expected_failed_case_counts[method]
        assert v1_summary["eligible_for_rag"] is False
        assert v2_summary["eligible_for_rag"] is False


def test_v2_boundary_violation_rate_is_lower_than_v1_for_all_three_methods() -> None:
    for method in METHODS:
        assert _v2_summary(method)["solution_boundary_violation_rate"] < _v1_summary(method)["solution_boundary_violation_rate"]


def test_v2_recall_at_5_is_still_below_the_frozen_gate_for_all_three_methods() -> None:
    for method in METHODS:
        assert _v2_summary(method)["recall_at_5"] < 1.0


def test_v1_empty_query_tokens_misclassification_is_absent_from_v2_formal_taxonomy() -> None:
    vector_v1_results = _load_jsonl(BASE_DIR / "vector_baseline_results.v1.jsonl")
    hybrid_v1_results = _load_jsonl(BASE_DIR / "hybrid_baseline_results.v1.jsonl")
    vector_v2_summary = _v2_summary("vector")
    hybrid_v2_summary = _v2_summary("hybrid")

    assert any("empty_query_tokens" in row["failure_reasons"] for row in vector_v1_results)
    assert any("empty_query_tokens" in row["failure_reasons"] for row in hybrid_v1_results)
    assert "empty_query_tokens" not in vector_v2_summary["failure_taxonomy"]
    assert "empty_query_tokens" not in hybrid_v2_summary["failure_taxonomy"]


def test_v2_failure_taxonomy_only_counts_solution_boundary_violations_in_frozen_results() -> None:
    assert _v2_summary("lexical")["failure_taxonomy"] == {"solution_boundary_violation": 3}
    assert _v2_summary("vector")["failure_taxonomy"] == {"solution_boundary_violation": 3}
    assert _v2_summary("hybrid")["failure_taxonomy"] == {"solution_boundary_violation": 2}


def test_v2_comparison_keeps_no_eligible_method_decision() -> None:
    comparison = _load_json(BASE_DIR / "retrieval_method_comparison.v2.json")
    assert comparison["selected_method"] is None
    assert comparison["selection_status"] == "no_eligible_method"
    assert comparison["selection_reasons"] == ["No retrieval method passed the frozen blocking gate."]


def test_failed_case_reduction_cannot_be_claimed_as_algorithm_tuning_gain() -> None:
    for method in METHODS:
        assert _v2_config(method)["algorithm_config"] == _v1_config(method)
    assert _v2_summary("lexical")["failed_case_ids"] != _v1_summary("lexical")["failed_case_ids"]
    assert _v2_summary("vector")["failed_case_ids"] != _v1_summary("vector")["failed_case_ids"]
    assert _v2_summary("hybrid")["failed_case_ids"] != _v1_summary("hybrid")["failed_case_ids"]


def test_interpretation_of_v1_to_v2_change_must_be_governance_not_parameter_change() -> None:
    for method in METHODS:
        assert _v2_config(method)["algorithm_config"] == _v1_config(method)
    assert _v2_summary("vector")["failure_taxonomy"] == {"solution_boundary_violation": 3}
    assert _v2_summary("hybrid")["failure_taxonomy"] == {"solution_boundary_violation": 2}


def test_next_stage_must_address_recall_and_boundary_together() -> None:
    for method in METHODS:
        summary = _v2_summary(method)
        assert summary["recall_at_5"] < 1.0
        assert summary["solution_boundary_violation_rate"] > 0.0


def test_architecture_c_must_remain_blocked_because_selected_method_is_null() -> None:
    comparison = _load_json(BASE_DIR / "retrieval_method_comparison.v2.json")
    assert comparison["selected_method"] is None
    assert comparison["selection_status"] == "no_eligible_method"
