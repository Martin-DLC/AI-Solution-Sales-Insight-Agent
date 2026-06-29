from __future__ import annotations

import json
from pathlib import Path
from statistics import mean


BASE_DIR = Path("data/evaluation/retrieval")
VECTOR_RESULTS_PATH = BASE_DIR / "vector_baseline_results.v1.jsonl"
VECTOR_SUMMARY_PATH = BASE_DIR / "vector_baseline_summary.v1.json"
HYBRID_RESULTS_PATH = BASE_DIR / "hybrid_baseline_results.v1.jsonl"
HYBRID_SUMMARY_PATH = BASE_DIR / "hybrid_baseline_summary.v1.json"
RETRIEVAL_CASES_PATH = BASE_DIR / "retrieval_cases.v1.jsonl"


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _expected_case_order() -> list[str]:
    return [row["retrieval_case_id"] for row in _load_jsonl(RETRIEVAL_CASES_PATH)]


def _assert_summary_matches_results(summary: dict, results: list[dict]) -> None:
    assert summary["case_count"] == len(results)
    assert summary["recall_at_1"] == mean(row["recall_at_1"] for row in results)
    assert summary["recall_at_3"] == mean(row["recall_at_3"] for row in results)
    assert summary["recall_at_5"] == mean(row["recall_at_5"] for row in results)
    assert summary["precision_at_3"] == mean(row["precision_at_3"] for row in results)
    assert summary["precision_at_5"] == mean(row["precision_at_5"] for row in results)
    assert summary["mean_reciprocal_rank"] == mean(row["reciprocal_rank"] for row in results)
    assert summary["forbidden_hit_rate"] == mean(1.0 if row["forbidden_hit"] else 0.0 for row in results)
    assert summary["solution_boundary_violation_rate"] == mean(
        1.0 if row["solution_boundary_violation"] else 0.0 for row in results
    )
    assert summary["average_latency_ms"] == mean(row["latency_ms"] for row in results)
    assert summary["failed_case_ids"] == [
        row["retrieval_case_id"] for row in results if not row["passed_blocking_gate"]
    ]


def test_formal_result_files_exist() -> None:
    for path in (
        VECTOR_RESULTS_PATH,
        VECTOR_SUMMARY_PATH,
        HYBRID_RESULTS_PATH,
        HYBRID_SUMMARY_PATH,
    ):
        assert path.exists(), f"Expected formal retrieval artifact to exist: {path}"


def test_vector_and_hybrid_results_cover_all_cases_in_order() -> None:
    expected_order = _expected_case_order()
    vector_results = _load_jsonl(VECTOR_RESULTS_PATH)
    hybrid_results = _load_jsonl(HYBRID_RESULTS_PATH)

    assert len(vector_results) == 16
    assert len(hybrid_results) == 16
    assert [row["retrieval_case_id"] for row in vector_results] == expected_order
    assert [row["retrieval_case_id"] for row in hybrid_results] == expected_order


def test_vector_and_hybrid_summaries_recompute_from_case_results() -> None:
    vector_results = _load_jsonl(VECTOR_RESULTS_PATH)
    hybrid_results = _load_jsonl(HYBRID_RESULTS_PATH)
    vector_summary = _load_json(VECTOR_SUMMARY_PATH)
    hybrid_summary = _load_json(HYBRID_SUMMARY_PATH)

    _assert_summary_matches_results(vector_summary, vector_results)
    _assert_summary_matches_results(hybrid_summary, hybrid_results)


def test_formal_result_files_do_not_expose_embeddings_gold_or_absolute_paths() -> None:
    for result_path in (VECTOR_RESULTS_PATH, HYBRID_RESULTS_PATH):
        serialized = result_path.read_text(encoding="utf-8")
        lowered = serialized.casefold()
        assert '"embedding"' not in lowered
        assert '"vector":' not in lowered
        assert '"gold"' not in lowered
        assert "/users/baba/" not in lowered


def test_hybrid_candidates_include_rrf_fields() -> None:
    hybrid_results = _load_jsonl(HYBRID_RESULTS_PATH)
    first_candidate = hybrid_results[0]["retrieved_candidates"][0]
    metadata = first_candidate["metadata"]

    assert "lexical_rank" in metadata
    assert "vector_rank" in metadata
    assert "lexical_score" in metadata
    assert "vector_score" in metadata
    assert "rrf_score" in metadata
