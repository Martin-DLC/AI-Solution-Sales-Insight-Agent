from __future__ import annotations

import json
from pathlib import Path

from evaluation.retrieval.metadata_blind_evaluation_v2 import (
    EXPECTED_LABELS_SHA256,
    EXPECTED_REPORT_SHA256,
    EXPECTED_LABELS_SHA256_V2_2,
    EXPECTED_REPORT_SHA256_V2_2,
    EXPECTED_FREEZE_MANIFEST_SHA256_V2_2,
    _build_effective_chunk_metadata,
    _load_inputs,
    _relevant_item_identity,
    _scope_contract_allowed,
    check_evaluation_outputs,
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


def test_attempt_1_check_still_matches_tracked_outputs() -> None:
    ok, differences = check_evaluation_outputs()
    assert ok is True
    assert differences == []


def test_attempt_2_provenance_gate_and_mapping_integrity() -> None:
    payload = run_blind_metadata_evaluation(protocol_version="2.2", attempt_number=2)

    assert payload["provenance_gate"]["passed"] is True
    assert payload["input_hashes"]["labels_sha256"] == EXPECTED_LABELS_SHA256_V2_2
    assert payload["input_hashes"]["authoring_report_sha256"] == EXPECTED_REPORT_SHA256_V2_2
    assert payload["input_hashes"]["freeze_manifest_sha256"] == EXPECTED_FREEZE_MANIFEST_SHA256_V2_2
    assert payload["mapping_integrity"]["passed"] is True
    assert payload["mapping_integrity"]["opaque_document_ids_mapped"] == 20
    assert payload["mapping_integrity"]["opaque_chunk_ids_mapped"] == 40
    assert payload["evaluation_scope"] == {
        "case_count": 16,
        "chunk_count": 40,
        "pair_count": 640,
    }


def test_attempt_2_scope_only_and_full_runtime_metrics_are_separate() -> None:
    payload = run_blind_metadata_evaluation(protocol_version="2.2", attempt_number=2)

    assert payload["scope_only_metrics"]["relevant_candidate_retention_rate"] == 0.96875
    assert payload["scope_only_metrics"]["boundary_candidate_removal_rate"] == 0.7226666666666667
    assert payload["full_runtime_metrics"]["relevant_candidate_retention_rate"] == 0.96875
    assert payload["full_runtime_metrics"]["boundary_candidate_removal_rate"] == 0.9786666666666667
    assert payload["scope_only_metrics"]["false_inclusion_count"] == 104
    assert payload["full_runtime_metrics"]["false_inclusion_count"] == 8


def test_attempt_2_closes_boundary_research_even_when_p0_fails() -> None:
    payload = run_blind_metadata_evaluation(protocol_version="2.2", attempt_number=2)

    assert payload["p0_validation_status"] == "failed"
    assert payload["boundary_contract_validation_status"] == "failed"
    assert payload["evidence_classification"] == "P1_blind_attempt_2_failed"
    assert payload["metadata_versioning_status"] == "blocked_with_known_limitations"
    assert payload["boundary_research_status"] == "closed_after_attempt_2_failed"
    assert payload["further_blind_attempts_allowed"] is False
    assert payload["labels_remain_immutable"] is True
    assert payload["ret2_015_016_status"] == "candidate_recall_unresolved"
    assert payload["architecture_c_status"] == "blocked"


def test_attempt_2_runtime_filter_attribution_and_attempt_comparison() -> None:
    payload = run_blind_metadata_evaluation(protocol_version="2.2", attempt_number=2)

    assert payload["runtime_filter_attribution"]["solution_scope"]["pair_count"] == 339
    assert payload["runtime_filter_attribution"]["solution_scope"]["boundary_pair_count"] == 271
    assert payload["runtime_filter_attribution"]["excluded_solution"]["pair_count"] == 0
    assert payload["attempt_1_vs_attempt_2"]["attempt_1_full_runtime_retention"] == 0.96875
    assert payload["attempt_1_vs_attempt_2"]["attempt_2_full_runtime_retention"] == 0.96875
    assert payload["attempt_1_vs_attempt_2"]["attempt_1_full_runtime_removal"] == 0.984
    assert payload["attempt_1_vs_attempt_2"]["attempt_2_full_runtime_removal"] == 0.9786666666666667
    assert payload["attempt_1_vs_attempt_2"]["guide_clarified_scope_runtime_responsibility"] is True
    assert payload["attempt_1_vs_attempt_2"]["guide_changed_assignment_distribution"] is True
    assert payload["attempt_1_vs_attempt_2"]["blind_performance_improved"] is False
    assert payload["attempt_1_vs_attempt_2"]["attempt_2_outperformed_attempt_1"] is False
    assert payload["attempt_1_vs_attempt_2"]["independent_reproducibility_improvement"] == "not_demonstrated"


def test_formal_results_hashes_remain_unchanged() -> None:
    expected_hashes = {
        "data/evaluation/retrieval/lexical_baseline_results.v2.jsonl": "41bfa53dda9a65e78f82eeab064e0a9436b47bb423b3c52d995e3b661e552bad",
        "data/evaluation/retrieval/lexical_baseline_summary.v2.json": "c5a48e917a897bd3ab76b2f815fdc07796e69ff0c9117534e50d0b13058f67e0",
        "data/evaluation/retrieval/vector_baseline_results.v2.jsonl": "9db04530b0240d00175dd5f386b7cc4cea030266ba90bb3180063a5c320244c4",
        "data/evaluation/retrieval/vector_baseline_summary.v2.json": "766801ae928598de3e9ed23097f497764eeeac84e09da56ad6ee60b61cc8d585",
        "data/evaluation/retrieval/hybrid_baseline_results.v2.jsonl": "c5a3ace3ce08914fc7af7426e2c20143863d123b9e5ea3cfff314c0cd8dc5c46",
        "data/evaluation/retrieval/hybrid_baseline_summary.v2.json": "d9543f66c64ff065ba5be0e6cc80a1a97dcafc1caa3fcb4622b6704052679d74",
        "data/evaluation/retrieval/retrieval_method_comparison.v2.json": "92c405e623246dacc154d935f31069f4e31b96e55c8886eea9ec9d314aea618d",
    }
    for path_str, expected_hash in expected_hashes.items():
        path = Path(path_str)
        actual_hash = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
        assert actual_hash == expected_hash, path_str
