from __future__ import annotations

import json
from pathlib import Path

from evaluation.retrieval import RetrievalMethodComparisonEntry
from evaluation.retrieval.comparison_v2 import select_retrieval_method_v2
from evaluation.retrieval.runner_v2 import (
    RetrievalFormalCaseResultV2,
    recompute_summary_metrics_from_formal_results_v2,
)
from evaluation.retrieval.storage_v2 import compute_file_sha256


BASE_DIR = Path("data/evaluation/retrieval")
BENCHMARK_CONFIG_V2_PATH = BASE_DIR / "retrieval_benchmark_config.v2.json"
RETRIEVAL_CASES_V2_PATH = BASE_DIR / "retrieval_cases.v2.jsonl"
LEXICAL_RESULTS_PATH = BASE_DIR / "lexical_baseline_results.v2.jsonl"
LEXICAL_SUMMARY_PATH = BASE_DIR / "lexical_baseline_summary.v2.json"
VECTOR_RESULTS_PATH = BASE_DIR / "vector_baseline_results.v2.jsonl"
VECTOR_SUMMARY_PATH = BASE_DIR / "vector_baseline_summary.v2.json"
HYBRID_RESULTS_PATH = BASE_DIR / "hybrid_baseline_results.v2.jsonl"
HYBRID_SUMMARY_PATH = BASE_DIR / "hybrid_baseline_summary.v2.json"
COMPARISON_PATH = BASE_DIR / "retrieval_method_comparison.v2.json"

FROZEN_HASHES = {
    LEXICAL_RESULTS_PATH: "41bfa53dda9a65e78f82eeab064e0a9436b47bb423b3c52d995e3b661e552bad",
    LEXICAL_SUMMARY_PATH: "c5a48e917a897bd3ab76b2f815fdc07796e69ff0c9117534e50d0b13058f67e0",
    VECTOR_RESULTS_PATH: "9db04530b0240d00175dd5f386b7cc4cea030266ba90bb3180063a5c320244c4",
    VECTOR_SUMMARY_PATH: "766801ae928598de3e9ed23097f497764eeeac84e09da56ad6ee60b61cc8d585",
    HYBRID_RESULTS_PATH: "c5a3ace3ce08914fc7af7426e2c20143863d123b9e5ea3cfff314c0cd8dc5c46",
    HYBRID_SUMMARY_PATH: "d9543f66c64ff065ba5be0e6cc80a1a97dcafc1caa3fcb4622b6704052679d74",
    COMPARISON_PATH: "92c405e623246dacc154d935f31069f4e31b96e55c8886eea9ec9d314aea618d",
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _expected_case_order() -> list[str]:
    return [f"RET2-{index:03d}" for index in range(1, 17)]


def _expected_source_case_ids() -> dict[str, str]:
    return {
        row["retrieval_case_id"]: row["source_case_id"]
        for row in _load_jsonl(RETRIEVAL_CASES_V2_PATH)
    }


def _summary_and_results() -> dict[str, tuple[dict, list[dict]]]:
    return {
        "lexical_v1": (_load_json(LEXICAL_SUMMARY_PATH), _load_jsonl(LEXICAL_RESULTS_PATH)),
        "vector_v1": (_load_json(VECTOR_SUMMARY_PATH), _load_jsonl(VECTOR_RESULTS_PATH)),
        "hybrid_v1": (_load_json(HYBRID_SUMMARY_PATH), _load_jsonl(HYBRID_RESULTS_PATH)),
    }


def _frozen_blocking_gate() -> dict:
    return _load_json(BENCHMARK_CONFIG_V2_PATH)["blocking_gate"]


def test_formal_v2_files_exist_and_match_frozen_hashes() -> None:
    for path, expected_hash in FROZEN_HASHES.items():
        assert path.exists(), f"Expected frozen artifact to exist: {path}"
        assert compute_file_sha256(path) == expected_hash


def test_each_method_has_sixteen_results_in_stable_order_with_expected_source_case_ids() -> None:
    expected_order = _expected_case_order()
    expected_source_case_ids = _expected_source_case_ids()

    for _method, (_summary, results) in _summary_and_results().items():
        assert len(results) == 16
        assert [row["retrieval_case_id"] for row in results] == expected_order
        assert {row["retrieval_case_id"]: row["source_case_id"] for row in results} == expected_source_case_ids


def test_summaries_recompute_from_formal_results_with_runner_v2_single_source_of_truth() -> None:
    for _method, (summary, results) in _summary_and_results().items():
        formal_results = [RetrievalFormalCaseResultV2.model_validate(row) for row in results]
        recomputed = recompute_summary_metrics_from_formal_results_v2(formal_results)

        for field in (
            "case_count",
            "recall_at_1",
            "recall_at_3",
            "recall_at_5",
            "precision_at_3",
            "precision_at_5",
            "mean_reciprocal_rank",
            "forbidden_hit_rate",
            "solution_boundary_violation_rate",
            "request_error_count",
            "failed_case_ids",
            "failure_taxonomy",
            "eligible_for_rag",
            "average_latency_ms",
            "disqualification_reasons",
        ):
            assert summary[field] == recomputed[field]


def test_comparison_matches_three_formal_summaries_and_frozen_selection_rule() -> None:
    comparison = _load_json(COMPARISON_PATH)
    methods = _summary_and_results()
    summary_map = {summary["retrieval_method"]: summary for summary, _results in methods.values()}

    assert [entry["retrieval_method"] for entry in comparison["entries"]] == ["lexical_v1", "vector_v1", "hybrid_v1"]
    assert comparison["method_summaries"] == comparison["entries"]

    for entry in comparison["entries"]:
        summary = summary_map[entry["retrieval_method"]]
        for field in (
            "case_count",
            "recall_at_1",
            "recall_at_3",
            "recall_at_5",
            "precision_at_3",
            "precision_at_5",
            "mean_reciprocal_rank",
            "forbidden_hit_rate",
            "solution_boundary_violation_rate",
            "average_latency_ms",
            "eligible_for_rag",
            "disqualification_reasons",
            "failed_case_ids",
        ):
            assert entry[field] == summary[field]

    regenerated = select_retrieval_method_v2(
        benchmark_version=comparison["benchmark_version"],
        entries=[RetrievalMethodComparisonEntry.model_validate(entry) for entry in comparison["entries"]],
        benchmark_config_hash=comparison["benchmark_config_hash"],
        method_config_hashes=comparison["method_config_hashes"],
        retrieval_contract_version=comparison["retrieval_contract_version"],
        failure_taxonomy_version=comparison["failure_taxonomy_version"],
        boundary_contract_version=comparison["boundary_contract_version"],
    ).model_dump(mode="json")

    assert regenerated["selected_method"] == comparison["selected_method"]
    assert regenerated["selection_status"] == comparison["selection_status"]
    assert regenerated["selection_reasons"] == comparison["selection_reasons"]
    assert regenerated["rejected_methods"] == comparison["rejected_methods"]
    assert regenerated["comparison_limitations"] == comparison["comparison_limitations"]
    assert all(entry["eligible_for_rag"] is False for entry in comparison["entries"])
    assert comparison["selected_method"] is None
    assert comparison["selection_status"] == "no_eligible_method"


def test_formal_results_do_not_expose_gold_query_body_embedding_vectors_or_absolute_paths() -> None:
    for path in (
        LEXICAL_RESULTS_PATH,
        LEXICAL_SUMMARY_PATH,
        VECTOR_RESULTS_PATH,
        VECTOR_SUMMARY_PATH,
        HYBRID_RESULTS_PATH,
        HYBRID_SUMMARY_PATH,
        COMPARISON_PATH,
    ):
        serialized = path.read_text(encoding="utf-8").casefold()
        assert '"query":' not in serialized
        assert '"content":' not in serialized
        assert "expected_relevant_document_ids" not in serialized
        assert "expected_relevant_chunk_ids" not in serialized
        assert "forbidden_solution_ids" not in serialized
        assert "forbidden_document_ids" not in serialized
        assert '"embedding": [' not in serialized
        assert "/users/baba/" not in serialized
        assert "api_key" not in serialized
        assert "secret" not in serialized


def test_vector_and_hybrid_model_metadata_match_frozen_revision_and_dimension() -> None:
    vector_summary = _load_json(VECTOR_SUMMARY_PATH)
    hybrid_summary = _load_json(HYBRID_SUMMARY_PATH)

    for summary in (vector_summary, hybrid_summary):
        assert summary["model_name"] == "intfloat/multilingual-e5-small"
        assert summary["resolved_model_revision"] == "614241f622f53c4eeff9890bdc4f31cfecc418b3"
        assert summary["embedding_dimension"] == 384
        assert summary["corpus_embedding_count"] == 40


def test_complete_summary_gate_shows_recall_and_boundary_both_fail_for_all_three_methods() -> None:
    gate = _frozen_blocking_gate()

    for _method, (summary, _results) in _summary_and_results().items():
        recall_gate_passed = summary["recall_at_5"] == gate["summary_recall_at_5_equals"]
        forbidden_gate_passed = summary["forbidden_hit_rate"] == gate["summary_forbidden_hit_rate_equals"]
        boundary_gate_passed = (
            summary["solution_boundary_violation_rate"] == gate["summary_solution_boundary_violation_rate_equals"]
        )
        request_error_gate_passed = (
            summary["request_error_count"] == gate["summary_request_error_count_equals"]
        )

        assert summary["recall_at_5"] < 1.0
        assert summary["solution_boundary_violation_rate"] > 0.0
        assert summary["forbidden_hit_rate"] == 0.0
        assert summary["request_error_count"] == 0
        assert summary["eligible_for_rag"] is False

        assert recall_gate_passed is False
        assert forbidden_gate_passed is True
        assert boundary_gate_passed is False
        assert request_error_gate_passed is True


def test_disqualification_reasons_are_case_level_only_not_a_complete_summary_gate_explanation() -> None:
    gate = _frozen_blocking_gate()

    for _method, (summary, _results) in _summary_and_results().items():
        assert summary["disqualification_reasons"] == ["solution_boundary_violation"]
        assert summary["recall_at_5"] < gate["summary_recall_at_5_equals"]
        assert "recall" not in " ".join(summary["disqualification_reasons"]).casefold()
