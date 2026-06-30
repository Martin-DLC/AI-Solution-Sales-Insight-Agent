from __future__ import annotations

import json
from pathlib import Path


CONFIG_PATH = Path("data/evaluation/retrieval/retrieval_benchmark_config.v2.json")


def test_retrieval_benchmark_config_v2_tracks_frozen_counts_and_gate() -> None:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    assert payload["benchmark_version"] == "retrieval_benchmark_v2"
    assert payload["knowledge_contract_version"] == "v2"
    assert payload["document_count"] == 20
    assert payload["chunk_count"] == 40
    assert payload["case_count"] == 16
    assert payload["demo_solution_count"] == 6
    assert payload["all_cases_feasible"] is True
    assert payload["blocking_gate"] == {
        "summary_recall_at_5_equals": 1.0,
        "summary_forbidden_hit_rate_equals": 0.0,
        "summary_solution_boundary_violation_rate_equals": 0.0,
        "summary_request_error_count_equals": 0,
        "all_cases_pass_blocking_gate": True,
    }


def test_retrieval_benchmark_config_v2_references_tracked_v2_artifacts() -> None:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    assert payload["document_file"] == "data/knowledge_base/documents.v2.jsonl"
    assert payload["chunk_file"] == "data/knowledge_base/chunks.v2.jsonl"
    assert payload["manifest_file"] == "data/knowledge_base/manifest.v2.json"
    assert payload["case_file"] == "data/evaluation/retrieval/retrieval_cases.v2.jsonl"
    assert payload["feasibility_file"] == "data/evaluation/retrieval/retrieval_case_feasibility.v2.json"
    assert sorted(payload["dataset_hashes"]) == [
        "chunks_v2",
        "documents_v2",
        "manifest_v2",
        "retrieval_case_feasibility_v2",
        "retrieval_case_migration_v2",
        "retrieval_cases_v2",
        "solution_scope_migration_v2",
    ]
