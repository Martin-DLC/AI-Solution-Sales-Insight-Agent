from __future__ import annotations

import json
from pathlib import Path

from evaluation.retrieval import RetrievalEvaluationCaseV2
from evaluation.retrieval.dataset import load_retrieval_evaluation_cases


V1_CASES_PATH = Path("data/evaluation/retrieval/retrieval_cases.v1.jsonl")
V2_CASES_PATH = Path("data/evaluation/retrieval/retrieval_cases.v2.jsonl")
MIGRATION_PATH = Path("data/evaluation/retrieval/retrieval_case_migration.v2.json")


def _load_v2_cases() -> list[RetrievalEvaluationCaseV2]:
    return [
        RetrievalEvaluationCaseV2.model_validate(json.loads(line))
        for line in V2_CASES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_v2_cases_are_complete_and_ordered() -> None:
    cases = _load_v2_cases()

    assert len(cases) == 16
    assert [case.retrieval_case_id for case in cases] == [f"RET2-{index:03d}" for index in range(1, 17)]


def test_v2_cases_preserve_v1_query_and_split_runtime_from_gold() -> None:
    v1_cases = load_retrieval_evaluation_cases(V1_CASES_PATH)
    v1_by_retrieval_case_id = {case.retrieval_case_id: case for case in v1_cases}
    migration_payload = json.loads(MIGRATION_PATH.read_text(encoding="utf-8"))
    source_case_lookup = {
        row["target_case_id"]: row["source_retrieval_case_id"]
        for row in migration_payload["case_migrations"]
    }

    for case in _load_v2_cases():
        source = v1_by_retrieval_case_id[source_case_lookup[case.retrieval_case_id]]
        assert case.query == source.query
        assert case.runtime_context.operational_solution_scope == source.required_solution_ids
        assert case.evaluation_gold.forbidden_solution_ids == source.forbidden_solution_ids


def test_special_case_audit_and_rewrites_are_present() -> None:
    payload = json.loads(MIGRATION_PATH.read_text(encoding="utf-8"))
    migration_by_source_id = {row["source_retrieval_case_id"]: row for row in payload["case_migrations"]}

    assert sorted(payload["special_case_audit"]) == ["RET-001", "RET-002", "RET-005", "RET-006", "RET-009"]
    assert migration_by_source_id["RET-006"]["migration_status"] == "rewritten_for_feasibility"
    assert migration_by_source_id["RET-009"]["migration_status"] == "rewritten_for_feasibility"
    assert migration_by_source_id["RET-005"]["gold_changed"] is True


def test_v2_retrieval_gold_for_rewritten_cases_matches_tracked_expectations() -> None:
    cases = {case.retrieval_case_id: case for case in _load_v2_cases()}

    assert cases["RET2-006"].evaluation_gold.expected_relevant_document_ids == ["KB-SOL-003", "KB-SOL-004"]
    assert cases["RET2-009"].evaluation_gold.expected_relevant_chunk_ids == [
        "KB-SEC-001#chunk-000-f8c40d662005",
        "KB-CAP-001#chunk-001-bcb4fc0bf316",
    ]
