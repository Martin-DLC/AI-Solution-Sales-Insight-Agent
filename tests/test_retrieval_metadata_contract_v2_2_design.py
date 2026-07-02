from __future__ import annotations

import hashlib
from pathlib import Path

from evaluation.retrieval.metadata_contract_v2_2_design import (
    TRACKED_FAILURE_ANALYSIS_JSON_PATH,
    TRACKED_PROPOSAL_DOC_PATH,
    TRACKED_PROPOSAL_OUTPUT_PATH,
    TRACKED_EVALUATION_OUTPUT_PATH,
    UNSATISFIABLE_CHUNK_IDS,
    _load_inputs,
    _mode_allows,
    build_metadata_contract_v2_2_payload,
    build_plan_payload,
    check_metadata_contract_v2_2_outputs,
    write_metadata_contract_v2_2_outputs,
)


def test_plan_payload_is_read_only() -> None:
    payload = build_plan_payload()

    assert payload["mode"] == "plan"
    assert payload["writes_output_files"] is False
    assert payload["mutates_frozen_blind_labels"] is False
    assert payload["starts_blind_attempt_2"] is False


def test_payload_reads_frozen_hashes_without_mutation() -> None:
    payload = build_metadata_contract_v2_2_payload()

    assert payload["source_blind_label_hash"] == "58729c71ba03adce96f7e89170a9bc52bf637a028a7cfb33f1acd1b504327e92"
    assert payload["source_blind_evaluation_hash"] == hashlib.sha256(
        TRACKED_EVALUATION_OUTPUT_PATH.read_bytes()
    ).hexdigest()
    assert payload["source_failure_analysis_hash"] == hashlib.sha256(
        TRACKED_FAILURE_ANALYSIS_JSON_PATH.read_bytes()
    ).hexdigest()


def test_unsatisfiable_candidates_are_loaded_from_failure_snapshot() -> None:
    payload = build_metadata_contract_v2_2_payload()

    assert payload["unsatisfiable_candidate_analysis"]["candidate_ids"] == UNSATISFIABLE_CHUNK_IDS
    assert payload["source_failure_analysis_snapshot"]["schema_unsatisfiable_candidate_ids"] == UNSATISFIABLE_CHUNK_IDS


def test_any_applicable_scope_is_scope_based_not_case_id_based() -> None:
    inputs = _load_inputs()
    chunk = inputs["chunks_by_id"]["KB-SEC-001#chunk-000-f8c40d662005"]
    allow_case = next(case for case in inputs["cases"] if case.retrieval_case_id == "RET2-001")
    deny_case = next(case for case in inputs["cases"] if case.retrieval_case_id == "RET2-005")

    assert _mode_allows(case=allow_case, chunk=chunk, mode="any_applicable_scope") is True
    assert _mode_allows(case=deny_case, chunk=chunk, mode="any_applicable_scope") is True


def test_d0_is_minimal_when_existing_runtime_filters_are_joined() -> None:
    payload = build_metadata_contract_v2_2_payload()
    d0 = next(item for item in payload["schema_variants"] if item["variant_id"] == "D0")
    d1 = next(item for item in payload["schema_variants"] if item["variant_id"] == "D1")

    assert d0["perfect_candidate_count"] == 40
    assert d0["unsatisfiable_candidate_count"] == 0
    assert d0["false_exclusion_count"] == 0
    assert d0["false_inclusion_count"] == 0
    assert d1["perfect_candidate_count"] == 40
    assert payload["best_schema_variant"]["variant_id"] == "D0"
    assert payload["single_enum_extension_results"]["necessary_under_full_existing_runtime_join"] is False


def test_all_40_chunks_have_perfect_assignment_and_no_new_value_is_required() -> None:
    payload = build_metadata_contract_v2_2_payload()
    summary = payload["per_chunk_satisfiability"]

    assert summary["perfect_existing_v2_1_count"] == 29
    assert summary["requires_new_v2_2_value_count"] == 0
    assert summary["schema_unsatisfiable_count"] == 0
    assert all(chunk["no_perfect_assignment"] is False for chunk in summary["chunks"])


def test_existing_candidate_plus_existing_runtime_is_sufficient() -> None:
    payload = build_metadata_contract_v2_2_payload()

    assert payload["runtime_joinability"]["runtime_only_sufficient"] is False
    assert payload["runtime_joinability"]["candidate_only_sufficient"] is False
    assert payload["runtime_joinability"]["existing_candidate_plus_existing_runtime_sufficient"] is True
    assert payload["runtime_joinability"]["paired_upgrade_required"] is False


def test_assignment_rules_do_not_depend_on_case_id_fields() -> None:
    payload = build_metadata_contract_v2_2_payload()
    schema_text = str(payload["proposed_candidate_schema"])

    assert "case_id" not in schema_text
    assert payload["blind_authoring_requirements"]["case_id_forbidden"] is True
    assert payload["blind_authoring_requirements"]["gold_forbidden"] is True


def test_v2_2_stays_p1_and_keeps_architecture_blocked() -> None:
    payload = build_metadata_contract_v2_2_payload()

    assert payload["evidence_classification"] == "P1_post_hoc_schema_design_not_blind_validated"
    assert payload["metadata_v2_2_ready_for_versioning"] is False
    assert payload["ready_for_blind_protocol_v2_2"] is True
    assert payload["retriever_v2_status"] == "blocked_by_candidate_recall"
    assert payload["architecture_c_status"] == "blocked"


def test_write_and_check_outputs_are_stable(tmp_path, monkeypatch) -> None:
    json_path = tmp_path / "proposal.json"
    doc_path = tmp_path / "proposal.md"
    monkeypatch.setattr(
        "evaluation.retrieval.metadata_contract_v2_2_design.TRACKED_PROPOSAL_OUTPUT_PATH",
        json_path,
    )
    monkeypatch.setattr(
        "evaluation.retrieval.metadata_contract_v2_2_design.TRACKED_PROPOSAL_DOC_PATH",
        doc_path,
    )

    payload = build_metadata_contract_v2_2_payload()
    write_metadata_contract_v2_2_outputs(payload)
    ok, differences = check_metadata_contract_v2_2_outputs()

    assert json_path.exists()
    assert doc_path.exists()
    assert ok is True
    assert differences == []
