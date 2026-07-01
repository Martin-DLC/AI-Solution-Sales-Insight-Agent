from __future__ import annotations

import json
from pathlib import Path

from evaluation.retrieval.contracts_v2 import RetrievalEvaluationCaseV2, RetrievalEvaluationGoldV2, RetrievalRuntimeContextV2
from evaluation.retrieval.diagnostics_v2 import (
    DIAGNOSIS_OUTPUT_PATH,
    TOP_K_FORMAL,
    _candidate_relevance_id_for_case,
    _count_relevant_items_in_candidates,
    _scope_filter_and_backfill,
    build_case_recall_feasibility,
    compute_formal_result_hashes,
    load_diagnostic_context,
)
from knowledge_base.contracts_v2 import KnowledgeChunkV2, KnowledgeDocumentV2


def test_case_recall_feasibility_reports_all_v2_cases_as_top5_reachable() -> None:
    context = load_diagnostic_context()

    items = build_case_recall_feasibility(context.cases, top_k=TOP_K_FORMAL)

    assert len(items) == 16
    assert all(item["relevant_item_count"] <= 5 for item in items)
    assert all(item["recall_at_5_gate_feasible"] is True for item in items)
    assert all(item["minimum_hits_gate_feasible"] is True for item in items)


def test_relevant_item_identity_prefers_expected_chunk_over_document() -> None:
    case = RetrievalEvaluationCaseV2(
        retrieval_case_id="RET2-TEST",
        source_case_id="DEV-TEST",
        query_type="solution_discovery",
        query="test query",
        runtime_context=RetrievalRuntimeContextV2(),
        evaluation_gold=RetrievalEvaluationGoldV2(
            expected_relevant_document_ids=["DOC-001"],
            expected_relevant_chunk_ids=["DOC-001#chunk-001"],
            forbidden_document_ids=[],
            forbidden_solution_ids=[],
            minimum_relevant_hits=1,
        ),
    )
    candidate = {
        "document_id": "DOC-001",
        "chunk_id": "DOC-001#chunk-001",
    }

    identity = _candidate_relevance_id_for_case(case=case, candidate=candidate)
    hits = _count_relevant_items_in_candidates(case=case, candidates=[candidate], top_k=1)

    assert identity == "DOC-001#chunk-001"
    assert hits == 1


def test_scope_filter_backfill_uses_runtime_scope_metadata_only() -> None:
    allowed_solution = "合规政策RAG检索助手"
    blocked_solution = "客服辅助回复方案"
    case = RetrievalEvaluationCaseV2(
        retrieval_case_id="RET2-SCOPE",
        source_case_id="DEV-SCOPE",
        query_type="solution_boundary",
        query="scope test",
        runtime_context=RetrievalRuntimeContextV2(
            operational_solution_scope=[allowed_solution],
            allowed_document_types=["solution"],
        ),
        evaluation_gold=RetrievalEvaluationGoldV2(
            expected_relevant_document_ids=["DOC-ALLOW"],
            expected_relevant_chunk_ids=[],
            forbidden_document_ids=[],
            forbidden_solution_ids=[allowed_solution],
            minimum_relevant_hits=1,
        ),
    )
    documents_by_id = {
        "DOC-BLOCK": KnowledgeDocumentV2(
            document_id="DOC-BLOCK",
            document_type="solution",
            status="approved",
            owner="demo",
            summary="blocked summary",
            content="blocked content that is long enough.",
            source_uri="synthetic://blocked",
            primary_solution_id=blocked_solution,
            applicable_solution_ids=[blocked_solution],
            excluded_solution_ids=[],
            scope_type="solution_specific",
            scope_notes="blocked",
        ),
        "DOC-ALLOW": KnowledgeDocumentV2(
            document_id="DOC-ALLOW",
            document_type="solution",
            status="approved",
            owner="demo",
            summary="allowed summary",
            content="allowed content that is long enough.",
            source_uri="synthetic://allow",
            primary_solution_id=allowed_solution,
            applicable_solution_ids=[allowed_solution],
            excluded_solution_ids=[],
            scope_type="solution_specific",
            scope_notes="allowed",
        ),
    }
    chunks_by_id: dict[str, KnowledgeChunkV2] = {}
    candidates = [
        {
            "rank": 1,
            "document_id": "DOC-BLOCK",
            "chunk_id": None,
            "document_type": "solution",
            "boundary_violation": True,
        },
        {
            "rank": 2,
            "document_id": "DOC-ALLOW",
            "chunk_id": None,
            "document_type": "solution",
            "boundary_violation": False,
        },
    ]

    retained, removed = _scope_filter_and_backfill(
        case=case,
        candidates=candidates,
        documents_by_id=documents_by_id,
        chunks_by_id=chunks_by_id,
        top_k=1,
    )

    assert [item["document_id"] for item in retained] == ["DOC-ALLOW"]
    assert [item["document_id"] for item in removed] == ["DOC-BLOCK"]


def test_tracked_diagnosis_keeps_formal_result_hashes_unchanged() -> None:
    payload = json.loads(Path(DIAGNOSIS_OUTPUT_PATH).read_text(encoding="utf-8"))

    assert payload["diagnostic_only"] is True
    assert payload["architecture_c_status"] == "blocked"
    assert payload["formal_result_hashes"] == compute_formal_result_hashes()


def test_tracked_boundary_focus_cases_have_candidate_level_diagnostics() -> None:
    payload = json.loads(Path(DIAGNOSIS_OUTPUT_PATH).read_text(encoding="utf-8"))

    for case_id in ("RET2-005", "RET2-006", "RET2-009"):
        case_entry = payload["boundary_violation_diagnostics"][case_id]
        total_candidates = sum(len(items) for items in case_entry["violating_candidates_by_method"].values())
        assert total_candidates > 0
        assert case_entry["dominant_causes"]
