from __future__ import annotations

from evaluation.retrieval.metadata_blind_failure_analysis_v2 import (
    build_plan_payload,
    run_blind_failure_analysis,
)


def test_plan_payload_is_read_only() -> None:
    payload = build_plan_payload()

    assert payload["mode"] == "plan"
    assert payload["reads_gold_content"] is False
    assert payload["writes_output_files"] is False
    assert payload["guarantees"]["labels_remain_immutable"] is True


def test_failure_analysis_preserves_frozen_inputs_and_reports_summary_counts() -> None:
    payload = run_blind_failure_analysis()

    assert payload["source_blind_label_hash"] == "58729c71ba03adce96f7e89170a9bc52bf637a028a7cfb33f1acd1b504327e92"
    assert payload["labels_remain_immutable"] is True
    assert payload["evaluator_technical_fix_audit"]["metrics_generated_before_fix"] is True
    assert payload["evaluator_technical_fix_audit"]["labels_modified_during_fix"] is False
    assert payload["error_pair_summary"] == {
        "error_pair_count": 25,
        "false_exclusion_count": 2,
        "false_inclusion_count": 23,
        "unique_error_candidate_count": 11,
    }


def test_false_exclusion_pairs_match_frozen_playbook_chunks() -> None:
    payload = run_blind_failure_analysis()

    pairs = payload["false_exclusion_analysis"]["pairs"]
    assert [pair["case_id"] for pair in pairs] == ["RET2-002", "RET2-002"]
    assert [pair["source_chunk_id"] for pair in pairs] == [
        "KB-PLAY-001#chunk-000-0015819a0dd7",
        "KB-PLAY-001#chunk-001-e90933b01fb0",
    ]


def test_candidate_satisfiability_distinguishes_misclassification_and_unsatisfiable_chunks() -> None:
    payload = run_blind_failure_analysis()
    candidates = {item["source_chunk_id"]: item for item in payload["unique_error_candidates"]}

    playbook_chunk = candidates["KB-PLAY-001#chunk-000-0015819a0dd7"]
    security_chunk = candidates["KB-SEC-001#chunk-000-f8c40d662005"]

    assert playbook_chunk["root_cause_category"] == "A_blind_authoring_misclassification"
    assert playbook_chunk["available_perfect_modes"] == ["primary_in_scope"]
    assert playbook_chunk["alternative_existing_mode_is_perfect"] is True

    assert security_chunk["root_cause_category"] == "C_three_mode_schema_unsatisfiable"
    assert security_chunk["available_perfect_modes"] == []
    assert security_chunk["no_existing_mode_is_perfect"] is True


def test_global_counts_require_v2_2_before_new_blind_attempt() -> None:
    payload = run_blind_failure_analysis()

    assert len(payload["authoring_misclassifications"]) == 9
    assert len(payload["missing_chunk_overrides"]) == 0
    assert len(payload["schema_unsatisfiable_candidates"]) == 2
    assert len(payload["observable_state_conflicts"]) == 6
    assert payload["metadata_v2_2_design_required"] is True
    assert payload["benchmark_case_review_required"] is False
    assert payload["recommended_next_step"] == "design_metadata_contract_v2_2_then_run_new_blind_attempt"
    assert payload["retriever_v2_status"] == "blocked"
    assert payload["architecture_c_status"] == "blocked"

