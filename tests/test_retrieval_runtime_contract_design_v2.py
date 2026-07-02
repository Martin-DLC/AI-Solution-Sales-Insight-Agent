from __future__ import annotations

from evaluation.retrieval.candidate_generation_v2 import _load_experiment_context
from evaluation.retrieval.runtime_contract_design_v2 import (
    _allow_candidate_metadata_only_extension,
    _allow_oracle_contract,
    _build_joinability_matrix,
    _current_gold_boundary_allowed,
    _derive_runtime_scope_match_mode,
    build_runtime_contract_design_payload,
    build_plan_payload,
)
from evaluation.retrieval.runner_v2 import make_runtime_input_v2


def _get_case(context, case_id: str):
    return next(case for case in context.cases if case.retrieval_case_id == case_id)


def _get_chunk(context, chunk_id: str):
    return next(chunk for chunk in context.chunks_v2 if chunk.chunk_id == chunk_id)


def _build_record(context, *, case_id: str, chunk_id: str):
    case = _get_case(context, case_id)
    chunk = _get_chunk(context, chunk_id)
    document = context.documents_by_id[chunk.document_id]
    return type(
        "FakeRecord",
        (),
        {
            "case_id": case_id,
            "method_id": "lexical_v1",
            "document": document,
            "chunk": chunk,
            "candidate": chunk,
            "candidate_id": chunk.chunk_id,
            "relevant": True,
            "boundary": not _current_gold_boundary_allowed(case=case, document=document, chunk=chunk),
        },
    )()


def test_joinability_matrix_contains_scope_type_gap() -> None:
    matrix = _build_joinability_matrix()
    entry = next(
        item
        for item in matrix
        if item["runtime_field"] == "operational_solution_scope" and item["candidate_field"] == "scope_type"
    )
    assert entry["comparable"] is True
    assert entry["missing_signal"] is True


def test_candidate_scope_match_mode_is_static_per_candidate() -> None:
    context = _load_experiment_context()
    candidate_id = "KB-CAP-001#chunk-000-4a0d2db10fea"
    mode_a = _derive_runtime_scope_match_mode(record=_build_record(context, case_id="RET2-003", chunk_id=candidate_id))
    mode_b = _derive_runtime_scope_match_mode(record=_build_record(context, case_id="RET2-005", chunk_id=candidate_id))
    assert mode_a == mode_b == "full_applicable_scope"


def test_candidate_scope_match_mode_depends_only_on_static_candidate_fields() -> None:
    context = _load_experiment_context()
    base_record = _build_record(context, case_id="RET2-003", chunk_id="KB-CAP-001#chunk-000-4a0d2db10fea")
    altered_record = type(
        "FakeRecord",
        (),
        {
            "case_id": "RET2-999",
            "method_id": "hybrid_v1",
            "document": base_record.document,
            "chunk": base_record.chunk,
            "candidate": base_record.candidate,
            "candidate_id": base_record.candidate_id,
            "relevant": False,
            "boundary": True,
        },
    )()

    assert _derive_runtime_scope_match_mode(record=base_record) == "full_applicable_scope"
    assert _derive_runtime_scope_match_mode(record=altered_record) == "full_applicable_scope"


def test_cross_cutting_rule_keeps_shared_prerequisite() -> None:
    context = _load_experiment_context()
    case = _get_case(context, "RET2-001")
    chunk_id = "KB-SEC-001#chunk-000-f8c40d662005"
    record = _build_record(context, case_id="RET2-001", chunk_id=chunk_id)
    runtime_input = make_runtime_input_v2(case=case, top_k=20)

    assert _derive_runtime_scope_match_mode(record=record) == "primary_in_scope"
    assert _allow_candidate_metadata_only_extension(case=case, runtime_input=runtime_input, record=record) is True


def test_multi_solution_rule_filters_partial_scope_only_candidate() -> None:
    context = _load_experiment_context()
    chunk_id = "KB-CAP-001#chunk-000-4a0d2db10fea"
    relevant_case = _get_case(context, "RET2-003")
    boundary_case = _get_case(context, "RET2-005")
    record = _build_record(context, case_id="RET2-003", chunk_id=chunk_id)

    assert _derive_runtime_scope_match_mode(record=record) == "full_applicable_scope"
    assert _allow_candidate_metadata_only_extension(
        case=relevant_case,
        runtime_input=make_runtime_input_v2(case=relevant_case, top_k=20),
        record=record,
    ) is True
    assert _allow_candidate_metadata_only_extension(
        case=boundary_case,
        runtime_input=make_runtime_input_v2(case=boundary_case, top_k=20),
        record=record,
    ) is False


def test_oracle_contract_is_gold_dependent() -> None:
    context = _load_experiment_context()
    case = _get_case(context, "RET2-005")
    record = _build_record(context, case_id="RET2-005", chunk_id="KB-CAP-001#chunk-000-4a0d2db10fea")
    allowed = _allow_oracle_contract(case=case, runtime_input=make_runtime_input_v2(case=case, top_k=20), record=record)
    assert allowed is False


def test_plan_payload_keeps_architecture_blocked_and_hashes() -> None:
    payload = build_plan_payload()
    assert payload["diagnostic_only"] is True
    assert "formal_result_hashes" in payload
    assert payload["planned_outputs"]["json"].endswith("retrieval_runtime_contract_v2_1_proposal.json")


def test_runtime_contract_payload_marks_c2_as_p1_hypothesis() -> None:
    payload = build_runtime_contract_design_payload()
    c2 = next(item for item in payload["counterfactual_results"] if item["contract_id"] == "C2")

    assert payload["evidence_classification"] == "P1_content_explainable_not_blind_validated"
    assert payload["blind_authoring_validated"] is False
    assert payload["deployment_validated"] is False
    assert payload["boundary_contract_ready_for_versioning"] is False
    assert payload["ready_for_blind_authoring"] is True
    assert payload["proposed_upgrade_scope"] == "knowledge_metadata_only_v2_1"
    assert payload["final_upgrade_scope_decision"] == "pending_blind_authoring_validation"
    assert payload["recommended_metadata_granularity"] == "document_default_with_chunk_override"
    assert payload["assignment_rule_case_independent"] is True
    assert payload["assignment_rule_uses_candidate_static_fields_only"] is True
    assert payload["assignment_rule_has_id_hardcoding"] is False
    assert payload["authoring_process_was_blind_to_cases_and_gold"] is False
    assert payload["runtime_matching_rule_uses_gold"] is False
    assert payload["candidate_assignment_rule_reads_gold_fields"] is False
    assert payload["architecture_c_status"] == "blocked"
    assert payload["retriever_v2_ready_for_implementation"] is False
    assert c2["relevant_candidate_retention_rate"] == 1.0
    assert c2["boundary_candidate_removal_rate"] == 1.0
    assert c2["candidate_recall_at_20"] == 0.96875
    assert c2["authoring_process_was_blind"] is False
    assert c2["validated_contract"] is False
    assert c2["hypothesis_supported"] is True
