from __future__ import annotations

import json
from pathlib import Path


BASE_DIR = Path("data/evaluation/retrieval")
COMPARISON_PATH = BASE_DIR / "retrieval_method_comparison.v1.json"
LEXICAL_SUMMARY_PATH = BASE_DIR / "lexical_baseline_summary.v1.json"
VECTOR_SUMMARY_PATH = BASE_DIR / "vector_baseline_summary.v1.json"
HYBRID_SUMMARY_PATH = BASE_DIR / "hybrid_baseline_summary.v1.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_comparison_file_exists() -> None:
    assert COMPARISON_PATH.exists()


def test_comparison_entries_match_frozen_summaries() -> None:
    comparison = _load_json(COMPARISON_PATH)
    lexical = _load_json(LEXICAL_SUMMARY_PATH)
    vector = _load_json(VECTOR_SUMMARY_PATH)
    hybrid = _load_json(HYBRID_SUMMARY_PATH)
    summaries = {
        "lexical_v1": lexical,
        "vector_v1": vector,
        "hybrid_v1": hybrid,
    }

    assert [entry["retrieval_method"] for entry in comparison["entries"]] == ["lexical_v1", "vector_v1", "hybrid_v1"]
    for entry in comparison["entries"]:
        summary = summaries[entry["retrieval_method"]]
        assert entry["case_count"] == summary["case_count"]
        assert entry["recall_at_1"] == summary["recall_at_1"]
        assert entry["recall_at_3"] == summary["recall_at_3"]
        assert entry["recall_at_5"] == summary["recall_at_5"]
        assert entry["precision_at_3"] == summary["precision_at_3"]
        assert entry["precision_at_5"] == summary["precision_at_5"]
        assert entry["mean_reciprocal_rank"] == summary["mean_reciprocal_rank"]
        assert entry["forbidden_hit_rate"] == summary["forbidden_hit_rate"]
        assert entry["solution_boundary_violation_rate"] == summary["solution_boundary_violation_rate"]
        assert entry["average_latency_ms"] == summary["average_latency_ms"]
        assert entry["eligible_for_rag"] == summary["eligible_for_rag"]
        assert entry["failed_case_ids"] == summary["failed_case_ids"]
        assert entry["disqualification_reasons"] == summary["disqualification_reasons"]


def test_selected_method_follows_frozen_rule_when_no_method_is_eligible() -> None:
    comparison = _load_json(COMPARISON_PATH)

    assert all(entry["eligible_for_rag"] is False for entry in comparison["entries"])
    assert comparison["selected_method"] is None
    assert comparison["selection_status"] == "no_eligible_method"
    assert comparison["selection_reasons"] == ["No retrieval method passed the frozen blocking gate."]


def test_no_ineligible_method_can_be_selected() -> None:
    comparison = _load_json(COMPARISON_PATH)
    if comparison["selected_method"] is None:
        assert comparison["selection_status"] == "no_eligible_method"
        return

    selected = next(entry for entry in comparison["entries"] if entry["retrieval_method"] == comparison["selected_method"])
    assert selected["eligible_for_rag"] is True
