from __future__ import annotations

import json

import scripts.analyze_retrieval_v1_failures as analysis_cli


def test_analysis_marks_empty_query_tokens_as_misclassification() -> None:
    payload = analysis_cli.build_analysis_payload()

    audit = payload["empty_query_tokens_audit"]
    assert audit["raw_query_empty_case_ids"] == []
    assert audit["vector_all_cases_have_candidates"] is True
    assert audit["hybrid_all_cases_have_candidates"] is True
    assert audit["classification"] == "failure_taxonomy_misclassification"
    assert audit["impacts_eligible_for_rag"] is False


def test_counterfactual_only_changes_failure_reasons_not_formal_metrics() -> None:
    payload = analysis_cli.build_analysis_payload()

    counterfactual = payload["empty_query_tokens_counterfactual"]
    assert counterfactual["counterfactual_only"] is True
    assert "empty_query_tokens" not in counterfactual["vector"]["disqualification_reasons"]
    assert "empty_query_tokens" not in counterfactual["hybrid"]["disqualification_reasons"]
    assert counterfactual["vector"]["case_level_pass_count_after_exclusion"] > 0
    assert counterfactual["vector"]["method_still_ineligible_due_to_frozen_summary_metrics"] is True
    assert counterfactual["hybrid"]["method_still_ineligible_due_to_frozen_summary_metrics"] is True


def test_analysis_detects_infeasible_cases_from_boundary_contract() -> None:
    payload = analysis_cli.build_analysis_payload()

    feasibility = payload["benchmark_feasibility"]
    assert feasibility["infeasible_case_ids"] == ["RET-006", "RET-009"]
    assert (
        feasibility["infeasibility_reasons_by_case"]["RET-006"]
        == ["minimum_relevant_hits_exceeds_safe_expected_items", "expected_relevant_items_conflict_with_boundary"]
    )


def test_analysis_tracks_multi_solution_metadata_pressure_points() -> None:
    payload = analysis_cli.build_analysis_payload()

    findings = payload["knowledge_metadata_findings"]
    assert findings["document_solution_cardinality_distribution"] == {"1": 6, "2": 10, "3": 3, "6": 1}
    assert findings["chunk_inherits_document_solution_scope"] is True
    assert any(item["document_id"] == "KB-COM-001" for item in findings["multi_solution_documents"])


def test_analysis_output_omits_full_queries_and_document_content() -> None:
    payload = analysis_cli.build_analysis_payload()
    serialized = json.dumps(payload, ensure_ascii=False)

    assert "hidden reference" not in serialized.casefold()
    assert "data/runtime/" not in serialized
    assert "synthetic retrieval query probe" not in serialized
    assert '"query":' not in serialized
    assert '"content":' not in serialized
