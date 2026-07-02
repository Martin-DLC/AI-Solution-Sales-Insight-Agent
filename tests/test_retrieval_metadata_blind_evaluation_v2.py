from __future__ import annotations

from evaluation.retrieval.metadata_blind_evaluation_v2 import (
    EXPECTED_LABELS_SHA256,
    EXPECTED_REPORT_SHA256,
    _build_effective_chunk_metadata,
    _load_inputs,
    _relevant_item_identity,
    _scope_contract_allowed,
    run_blind_metadata_evaluation,
)
from knowledge_base.contracts_v2 import KnowledgeChunkV2


def test_provenance_gate_matches_frozen_hashes() -> None:
    payload = run_blind_metadata_evaluation()

    assert payload["provenance_gate"]["passed"] is True
    assert payload["input_hashes"]["labels_sha256"] == EXPECTED_LABELS_SHA256
    assert payload["input_hashes"]["authoring_report_sha256"] == EXPECTED_REPORT_SHA256
    assert payload["provenance_gate"]["authoring_process_was_blind_to_cases_and_gold"] is True
    assert payload["labels_remain_immutable"] is True
    assert payload["evaluation_does_not_modify_labels"] is True


def test_mapping_and_effective_metadata_cover_all_documents_and_chunks() -> None:
    payload = run_blind_metadata_evaluation()
    inputs = _load_inputs()
    summary = _build_effective_chunk_metadata(inputs=inputs)

    assert payload["mapping_integrity"]["passed"] is True
    assert summary["document_count"] == 20
    assert summary["chunk_count"] == 40
    assert summary["document_default_mode_counts"] == {
        "full_applicable_scope": 8,
        "global_reusable": 1,
        "primary_in_scope": 11,
    }
    assert summary["chunk_override_count"] == 3
    assert summary["assignment_source_counts"] == {
        "document_default": 37,
        "chunk_override": 3,
    }
    assert summary["mode_static_across_cases"] is True


def test_relevant_identity_prefers_chunk_over_document() -> None:
    assert _relevant_item_identity(
        document_id="DOC-1",
        chunk_id="CHUNK-1",
        expected_document_ids={"DOC-1"},
        expected_chunk_ids={"CHUNK-1"},
    ) == "CHUNK-1"
    assert _relevant_item_identity(
        document_id="DOC-1",
        chunk_id="CHUNK-2",
        expected_document_ids={"DOC-1"},
        expected_chunk_ids={"CHUNK-1"},
    ) == "DOC-1"


def test_scope_contract_rules_cover_primary_full_and_global_modes() -> None:
    inputs = _load_inputs()
    case_by_id = {case.retrieval_case_id: case for case in inputs["cases"]}
    chunk_by_id = {chunk.chunk_id: chunk for chunk in inputs["chunks"]}

    assert _scope_contract_allowed(
        case=case_by_id["RET2-001"],
        chunk=chunk_by_id["KB-SOL-001#chunk-000-29777128c730"],
        effective_mode="primary_in_scope",
    ) is True
    assert _scope_contract_allowed(
        case=case_by_id["RET2-001"],
        chunk=chunk_by_id["KB-SOL-002#chunk-000-7c0d6600d6d0"],
        effective_mode="primary_in_scope",
    ) is False
    assert _scope_contract_allowed(
        case=case_by_id["RET2-004"],
        chunk=chunk_by_id["KB-INT-002#chunk-000-37797d7945a6"],
        effective_mode="full_applicable_scope",
    ) is True
    assert _scope_contract_allowed(
        case=case_by_id["RET2-001"],
        chunk=chunk_by_id["KB-CAP-002#chunk-000-8171eccaf5f9"],
        effective_mode="full_applicable_scope",
    ) is False
    assert _scope_contract_allowed(
        case=case_by_id["RET2-001"],
        chunk=chunk_by_id["KB-COM-001#chunk-000-c29de4d33d60"],
        effective_mode="global_reusable",
    ) is True


def test_excluded_solution_conflict_is_rejected() -> None:
    inputs = _load_inputs()
    case = next(case for case in inputs["cases"] if case.retrieval_case_id == "RET2-014")
    chunk = KnowledgeChunkV2.model_validate(
        {
            **inputs["chunks_by_id"]["KB-SOL-001#chunk-000-29777128c730"].model_dump(mode="json"),
            "primary_solution_id": case.runtime_context.operational_solution_scope[0],
            "applicable_solution_ids": [case.runtime_context.operational_solution_scope[0]],
            "excluded_solution_ids": [case.runtime_context.operational_solution_scope[1]],
        }
    )

    assert _scope_contract_allowed(case=case, chunk=chunk, effective_mode="primary_in_scope") is False


def test_pairwise_coverage_and_overall_metrics_match_frozen_evaluation() -> None:
    payload = run_blind_metadata_evaluation()

    assert payload["pairwise_evaluation_scope"]["pair_count"] == 640
    assert payload["overall_metrics"] == {
        "pair_count": 640,
        "relevant_pair_count": 64,
        "relevant_allowed_count": 62,
        "relevant_denied_count": 2,
        "relevant_candidate_retention_rate": 0.96875,
        "boundary_violating_pair_count": 375,
        "boundary_denied_count": 352,
        "boundary_allowed_count": 23,
        "boundary_candidate_removal_rate": 0.9386666666666666,
        "false_exclusion_count": 2,
        "false_inclusion_count": 23,
        "benchmark_contract_conflict_count": 0,
    }


def test_false_pairs_and_p0_status_match_observed_blind_result() -> None:
    payload = run_blind_metadata_evaluation()

    assert len(payload["false_exclusions"]) == 2
    assert len(payload["false_inclusions"]) == 23
    assert payload["benchmark_contract_conflicts"] == []
    assert payload["p1_vs_p0_comparison"]["hypothesis_replicated"] is False
    assert payload["evidence_classification"] == "P1_content_explainable_not_blind_validated"
    assert payload["p0_validation_status"] == "failed"
    assert payload["metadata_v2_1_versioning_status"] == "blocked_blind_validation_failed"
    assert payload["retriever_v2_status"] == "blocked"
    assert payload["ret2_015_016_status"] == "candidate_recall_unresolved"
    assert payload["architecture_c_status"] == "blocked"
