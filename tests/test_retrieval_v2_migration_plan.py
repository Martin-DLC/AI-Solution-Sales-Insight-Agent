from __future__ import annotations

import scripts.plan_retrieval_v2_migration as migration_cli


def test_migration_plan_marks_infeasible_v1_cases() -> None:
    payload = migration_cli.build_migration_plan_payload()

    assert payload["infeasible_v1_case_ids"] == ["RET-006", "RET-009"]
    assert payload["no_v1_files_modified"] is True


def test_migration_plan_tracks_multi_solution_documents() -> None:
    payload = migration_cli.build_migration_plan_payload()

    assert "KB-COM-001" in payload["multi_solution_document_ids"]
    assert any(
        action["action"] == "re-express_global_policy_documents"
        for action in payload["document_scope_migration_actions"]
    )


def test_migration_plan_lists_required_v2_files() -> None:
    payload = migration_cli.build_migration_plan_payload()

    assert "data/knowledge_base/documents.v2.jsonl" in payload["required_new_v2_files"]
    assert "data/evaluation/retrieval/retrieval_cases.v2.jsonl" in payload["required_new_v2_files"]
