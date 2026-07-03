from __future__ import annotations

from datetime import date

from evaluation.retrieval.candidate_generation_v2 import (
    ROUND_1_FORMAL_RESULT_HASHES,
    _candidate_recall_at,
    _expand_document_candidates_to_chunks,
    _merge_hybrid_candidates,
    _render_document_retrieval_text,
    _render_enriched_chunk_text,
    _render_recall_round_1_markdown_lines,
    _render_round_1_context_view_text,
    _runtime_safe_chunk_eligible,
    _winning_view_label,
    build_plan_payload,
    build_recall_round_1_plan_payload,
)
from evaluation.retrieval.contracts_v2 import RetrievalEvaluationCaseV2, RetrievalEvaluationGoldV2, RetrievalRuntimeContextV2
from knowledge_base.contracts_v2 import KnowledgeChunkV2, KnowledgeDocumentV2, load_demo_solution_ids_v2
from knowledge_base.retrieval.hybrid import HybridBaselineConfig


def _solution_ids() -> tuple[str, ...]:
    ids = load_demo_solution_ids_v2()
    assert len(ids) == 6
    return ids


def _make_document(
    document_id: str,
    *,
    primary_solution_id: str | None,
    applicable_solution_ids: list[str],
    scope_type: str,
    excluded_solution_ids: list[str] | None = None,
    document_type: str = "solution",
) -> KnowledgeDocumentV2:
    return KnowledgeDocumentV2(
        document_id=document_id,
        title=f"title-{document_id}",
        document_type=document_type,
        status="approved",
        summary="这是一个足够长的摘要文本。",
        content="这是一个足够长的正文文本，用于候选生成测试。",
        source_uri=f"synthetic://{document_id}",
        primary_solution_id=primary_solution_id,
        applicable_solution_ids=applicable_solution_ids,
        excluded_solution_ids=excluded_solution_ids or [],
        scope_type=scope_type,
        scope_notes="test",
    )


def _make_chunk(
    chunk_id: str,
    document_id: str,
    *,
    primary_solution_id: str | None,
    applicable_solution_ids: list[str],
    scope_type: str,
    excluded_solution_ids: list[str] | None = None,
) -> KnowledgeChunkV2:
    return KnowledgeChunkV2(
        chunk_id=chunk_id,
        document_id=document_id,
        document_type="solution",
        chunk_index=0,
        content="这是一个足够长的 chunk 正文内容，包含用于测试的稳定字段。",
        token_estimate=24,
        metadata={"section_title": "Section A"},
        citation_label="doc-title - Section A",
        primary_solution_id=primary_solution_id,
        applicable_solution_ids=applicable_solution_ids,
        excluded_solution_ids=excluded_solution_ids or [],
        scope_type=scope_type,
        scope_notes="test",
    )


def _make_case(
    *,
    operational_scope: list[str],
    expected_chunk_ids: list[str],
    forbidden_solution_ids: list[str] | None = None,
) -> RetrievalEvaluationCaseV2:
    return RetrievalEvaluationCaseV2(
        retrieval_case_id="RET2-TEST",
        source_case_id="DEV-TEST",
        query_type="solution_boundary",
        query="知识库 检索 测试",
        runtime_context=RetrievalRuntimeContextV2(
            operational_solution_scope=operational_scope,
            allowed_document_types=["solution", "commercial_rule"],
        ),
        evaluation_gold=RetrievalEvaluationGoldV2(
            expected_relevant_document_ids=[],
            expected_relevant_chunk_ids=expected_chunk_ids,
            forbidden_document_ids=[],
            forbidden_solution_ids=forbidden_solution_ids or [],
            minimum_relevant_hits=1,
        ),
    )


def test_plan_payload_is_diagnostic_only() -> None:
    payload = build_plan_payload()

    assert payload["mode"] == "plan"
    assert payload["diagnostic_only"] is True
    assert payload["formal_result_hashes"]


def test_runtime_safe_filter_uses_runtime_not_gold() -> None:
    ids = _solution_ids()
    document = _make_document(
        "DOC-001",
        primary_solution_id=ids[0],
        applicable_solution_ids=[ids[0]],
        scope_type="solution_specific",
    )
    chunk = _make_chunk(
        "DOC-001#chunk-0",
        "DOC-001",
        primary_solution_id=ids[0],
        applicable_solution_ids=[ids[0]],
        scope_type="solution_specific",
    )
    case_a = _make_case(operational_scope=[ids[0]], expected_chunk_ids=[chunk.chunk_id], forbidden_solution_ids=[])
    case_b = _make_case(operational_scope=[ids[0]], expected_chunk_ids=[chunk.chunk_id], forbidden_solution_ids=[ids[1]])
    runtime_input_a = type("RuntimeInput", (), {
        "effective_on": date(2026, 7, 1),
        "allowed_document_types": tuple(case_a.runtime_context.allowed_document_types),
        "industries": tuple(),
        "tags": tuple(),
        "operational_solution_scope": tuple(case_a.runtime_context.operational_solution_scope),
    })()
    runtime_input_b = type("RuntimeInput", (), {
        "effective_on": date(2026, 7, 1),
        "allowed_document_types": tuple(case_b.runtime_context.allowed_document_types),
        "industries": tuple(),
        "tags": tuple(),
        "operational_solution_scope": tuple(case_b.runtime_context.operational_solution_scope),
    })()

    assert _runtime_safe_chunk_eligible(case=case_a, runtime_input=runtime_input_a, document=document, chunk=chunk) is True
    assert _runtime_safe_chunk_eligible(case=case_b, runtime_input=runtime_input_b, document=document, chunk=chunk) is True


def test_global_policy_is_preserved_but_strict_subset_blocks_multi_solution() -> None:
    ids = _solution_ids()
    global_doc = _make_document(
        "DOC-GLOBAL",
        primary_solution_id=None,
        applicable_solution_ids=list(ids),
        scope_type="global_policy",
        document_type="commercial_rule",
    )
    global_chunk = _make_chunk(
        "DOC-GLOBAL#chunk-0",
        "DOC-GLOBAL",
        primary_solution_id=None,
        applicable_solution_ids=list(ids),
        scope_type="global_policy",
    )
    multi_doc = _make_document(
        "DOC-MULTI",
        primary_solution_id=ids[0],
        applicable_solution_ids=[ids[0], ids[1]],
        scope_type="multi_solution",
    )
    multi_chunk = _make_chunk(
        "DOC-MULTI#chunk-0",
        "DOC-MULTI",
        primary_solution_id=ids[0],
        applicable_solution_ids=[ids[0], ids[1]],
        scope_type="multi_solution",
    )
    case = _make_case(operational_scope=[ids[0]], expected_chunk_ids=[global_chunk.chunk_id])
    runtime_input = type("RuntimeInput", (), {
        "effective_on": date(2026, 7, 1),
        "allowed_document_types": tuple(case.runtime_context.allowed_document_types),
        "industries": tuple(),
        "tags": tuple(),
        "operational_solution_scope": tuple(case.runtime_context.operational_solution_scope),
    })()

    assert _runtime_safe_chunk_eligible(case=case, runtime_input=runtime_input, document=global_doc, chunk=global_chunk) is True
    assert _runtime_safe_chunk_eligible(case=case, runtime_input=runtime_input, document=multi_doc, chunk=multi_chunk) is False


def test_enriched_and_document_text_are_deterministic() -> None:
    ids = _solution_ids()
    document = _make_document(
        "DOC-002",
        primary_solution_id=ids[0],
        applicable_solution_ids=[ids[0]],
        scope_type="solution_specific",
    )
    chunk = _make_chunk(
        "DOC-002#chunk-0",
        "DOC-002",
        primary_solution_id=ids[0],
        applicable_solution_ids=[ids[0]],
        scope_type="solution_specific",
    )

    enriched = _render_enriched_chunk_text(document=document, chunk=chunk, section_title="Section A")
    document_text = _render_document_retrieval_text(document)

    assert enriched == _render_enriched_chunk_text(document=document, chunk=chunk, section_title="Section A")
    assert "Title:" in enriched and "Summary:" in enriched and "Section:" in enriched and "Content:" in enriched
    assert document_text == _render_document_retrieval_text(document)
    assert "Document Type:" in document_text


def test_document_expansion_uses_child_rank_and_not_gold() -> None:
    ids = _solution_ids()
    chunk_a = _make_chunk(
        "DOC-010#chunk-0",
        "DOC-010",
        primary_solution_id=ids[0],
        applicable_solution_ids=[ids[0]],
        scope_type="solution_specific",
    )
    chunk_b = _make_chunk(
        "DOC-010#chunk-1",
        "DOC-010",
        primary_solution_id=ids[0],
        applicable_solution_ids=[ids[0]],
        scope_type="solution_specific",
    )
    expanded = _expand_document_candidates_to_chunks(
        document_candidates=[
            {"rank": 1, "document_id": "DOC-010", "chunk_id": "DOC-010#doc-000", "document_type": "solution", "score": 1.0, "matched_terms": []}
        ],
        child_chunk_ids={"DOC-010": [chunk_a.chunk_id, chunk_b.chunk_id]},
        child_rank_source=[
            {"rank": 2, "document_id": "DOC-010", "chunk_id": chunk_b.chunk_id},
            {"rank": 5, "document_id": "DOC-010", "chunk_id": chunk_a.chunk_id},
        ],
        chunks_by_id={chunk_a.chunk_id: chunk_a, chunk_b.chunk_id: chunk_b},
    )

    assert [item["chunk_id"] for item in expanded] == [chunk_b.chunk_id, chunk_a.chunk_id]
    assert all(item["candidate_sources"] == ["document_expanded"] for item in expanded)


def test_hybrid_merge_is_stable_and_deduplicates() -> None:
    config = HybridBaselineConfig.model_validate(
        {
            "baseline_version": "hybrid_rrf_v1",
            "retrieval_method": "lexical_vector_rrf",
            "lexical_method": "weighted_bm25",
            "vector_method": "dense_cosine",
            "lexical_candidate_k": 20,
            "vector_candidate_k": 20,
            "output_top_k": 5,
            "rrf_k": 60,
            "lexical_weight": 1.0,
            "vector_weight": 1.0,
            "score_round_digits": 8,
            "tie_break_rule": "rrf_score_desc_document_id_asc_chunk_id_asc",
            "synthetic_data": True,
        }
    )
    merged = _merge_hybrid_candidates(
        lexical_candidates=[
            {"rank": 1, "document_id": "DOC-A", "chunk_id": "DOC-A#chunk-0", "document_type": "solution", "score": 1.0, "matched_terms": ["知识"]},
            {"rank": 2, "document_id": "DOC-B", "chunk_id": "DOC-B#chunk-0", "document_type": "solution", "score": 0.8, "matched_terms": []},
        ],
        vector_candidates=[
            {"rank": 1, "document_id": "DOC-B", "chunk_id": "DOC-B#chunk-0", "document_type": "solution", "score": 0.9, "matched_terms": []},
            {"rank": 2, "document_id": "DOC-C", "chunk_id": "DOC-C#chunk-0", "document_type": "solution", "score": 0.7, "matched_terms": []},
        ],
        config=config,
        source_label="chunk",
    )

    assert [item["chunk_id"] for item in merged] == ["DOC-B#chunk-0", "DOC-A#chunk-0", "DOC-C#chunk-0"]
    assert "chunk:lexical" in merged[0]["candidate_sources"] and "chunk:vector" in merged[0]["candidate_sources"]


def test_candidate_recall_counts_chunk_hits() -> None:
    ids = _solution_ids()
    case = _make_case(operational_scope=[ids[0]], expected_chunk_ids=["DOC-100#chunk-0", "DOC-101#chunk-0"])
    candidates = [
        {"rank": 1, "document_id": "DOC-100", "chunk_id": "DOC-100#chunk-0"},
        {"rank": 2, "document_id": "DOC-102", "chunk_id": "DOC-102#chunk-0"},
        {"rank": 3, "document_id": "DOC-101", "chunk_id": "DOC-101#chunk-0"},
    ]

    assert _candidate_recall_at(case=case, candidates=candidates, top_k=1) == 0.5
    assert _candidate_recall_at(case=case, candidates=candidates, top_k=3) == 1.0


def test_candidate_recall_does_not_exceed_one_when_document_and_chunk_both_match() -> None:
    ids = _solution_ids()
    case = RetrievalEvaluationCaseV2(
        retrieval_case_id="RET2-DOC-CHUNK",
        source_case_id="DEV-TEST",
        query_type="solution_boundary",
        query="文档 与 chunk 双重命中",
        runtime_context=RetrievalRuntimeContextV2(
            operational_solution_scope=[ids[0]],
            allowed_document_types=["solution"],
        ),
        evaluation_gold=RetrievalEvaluationGoldV2(
            expected_relevant_document_ids=["DOC-200"],
            expected_relevant_chunk_ids=["DOC-200#chunk-0"],
            forbidden_document_ids=[],
            forbidden_solution_ids=[],
            minimum_relevant_hits=1,
        ),
    )
    candidates = [
        {"rank": 1, "document_id": "DOC-200", "chunk_id": "DOC-200#chunk-0"},
        {"rank": 2, "document_id": "DOC-200"},
    ]

    assert _candidate_recall_at(case=case, candidates=candidates, top_k=2) == 1.0


def test_recall_round_1_plan_payload_is_scope_limited() -> None:
    payload = build_recall_round_1_plan_payload()

    assert payload["mode"] == "plan"
    assert payload["experiment_id"] == "retrieval_v2_candidate_recall_round_1"
    assert payload["experiment_scope"] == "document_aware_multi_view_vector_retrieval"
    assert payload["focus_case_ids"] == ["RET2-015", "RET2-016"]
    assert payload["representation_fields"]["chunk_view"] == ["chunk.content"]
    assert "chunk.content" in payload["representation_fields"]["context_view"]
    assert payload["formal_results_modified"] is False
    assert payload["retriever_modified"] is False
    assert payload["boundary_research_status"] == "closed"


def test_round_1_context_view_is_deterministic_and_gold_independent() -> None:
    ids = _solution_ids()
    document = _make_document(
        "DOC-ROUND1",
        primary_solution_id=ids[0],
        applicable_solution_ids=[ids[0], ids[1]],
        scope_type="multi_solution",
    ).model_copy(update={"industries": ["retail"], "tags": ["demo-tag"]})
    chunk = _make_chunk(
        "DOC-ROUND1#chunk-0",
        "DOC-ROUND1",
        primary_solution_id=ids[0],
        applicable_solution_ids=[ids[0], ids[1]],
        scope_type="multi_solution",
    )
    solution_name_lookup = {
        ids[0]: "方案一",
        ids[1]: "方案二",
    }

    text = _render_round_1_context_view_text(
        document=document,
        chunk=chunk,
        solution_name_lookup=solution_name_lookup,
    )

    assert text == _render_round_1_context_view_text(
        document=document,
        chunk=chunk,
        solution_name_lookup=solution_name_lookup,
    )
    assert "Document Title:" in text
    assert "Document Summary:" in text
    assert "Document Type:" in text
    assert "Scope Type:" in text
    assert "Citation Label:" in text
    assert "Primary Solution Name:" in text
    assert "Applicable Solution Names:" in text
    assert "Industries:" in text
    assert "Tags:" in text
    assert "Chunk Content:" in text
    assert "RET2-015" not in text
    assert "expected_relevant" not in text
    assert "forbidden_document_ids" not in text
    assert "KB-CASE-001" not in text


def test_round_1_winning_view_label_and_markdown_lines_are_stable() -> None:
    assert _winning_view_label(chunk_view_score=0.8, context_view_score=0.8) == "both"
    assert _winning_view_label(chunk_view_score=0.8, context_view_score=0.9) == "context_view"
    assert _winning_view_label(chunk_view_score=0.9, context_view_score=0.8) == "chunk_view"

    lines = _render_recall_round_1_markdown_lines(
        {
            "experiment_id": "retrieval_v2_candidate_recall_round_1",
            "experiment_scope": "document_aware_multi_view_vector_retrieval",
            "source_model": "intfloat/multilingual-e5-small",
            "model_revision": "rev",
            "embedding_dimension": 384,
            "scoring_rule": "multi_view_score = max(chunk_view_score, context_view_score)",
            "overall_metrics": {
                "candidate_recall_at_5": 0.5,
                "candidate_recall_at_10": 0.75,
                "candidate_recall_at_20": 0.875,
                "full_recall_case_count_at_20": 14,
                "failed_case_ids": ["RET2-015", "RET2-016"],
            },
            "success_gate": {"passed": False},
            "round_status": "failed_frozen_move_to_round_2",
            "next_step": "round_2_document_level_retrieval_plus_child_chunk_expansion",
        }
    )

    rendered = "\n".join(lines)
    assert "Candidate Recall Round 1" in rendered
    assert "RET2-015, RET2-016" in rendered
    assert "failed_frozen_move_to_round_2" in rendered


def test_round_1_formal_hash_constants_match_frozen_values() -> None:
    assert ROUND_1_FORMAL_RESULT_HASHES["lexical_results"] == "41bfa53dda9a65e78f82eeab064e0a9436b47bb423b3c52d995e3b661e552bad"
    assert ROUND_1_FORMAL_RESULT_HASHES["comparison"] == "92c405e623246dacc154d935f31069f4e31b96e55c8886eea9ec9d314aea618d"
