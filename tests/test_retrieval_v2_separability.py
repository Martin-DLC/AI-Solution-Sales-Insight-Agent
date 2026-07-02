from __future__ import annotations

from datetime import date

from evaluation.retrieval.contracts_v2 import RetrievalEvaluationCaseV2, RetrievalEvaluationGoldV2, RetrievalRuntimeContextV2
from evaluation.retrieval.separability_v2 import (
    _augment_query_with_runtime,
    _classify_case_separability,
    _decompose_query,
    _evaluate_runtime_rule,
    _merge_multi_ranked_lists,
)
from knowledge_base.contracts_v2 import KnowledgeChunkV2, KnowledgeDocumentV2, load_demo_solution_ids_v2


def _solution_ids() -> tuple[str, ...]:
    ids = load_demo_solution_ids_v2()
    assert len(ids) == 6
    return ids


def _make_document(
    document_id: str,
    *,
    document_type: str = "solution",
    scope_type: str = "solution_specific",
    primary_solution_id: str | None,
    applicable_solution_ids: list[str],
    excluded_solution_ids: list[str] | None = None,
) -> KnowledgeDocumentV2:
    return KnowledgeDocumentV2.model_validate(
        {
            "document_id": document_id,
            "title": f"title-{document_id}",
            "document_type": document_type,
            "status": "approved",
            "summary": "这是一个足够长的摘要文本。",
            "content": "这是一个足够长的正文内容，用于 separability 测试。",
            "source_uri": f"synthetic://{document_id}",
            "scope_type": scope_type,
            "scope_notes": "test",
            "primary_solution_id": primary_solution_id,
            "applicable_solution_ids": applicable_solution_ids,
            "excluded_solution_ids": excluded_solution_ids or [],
        }
    )


def _make_chunk(
    chunk_id: str,
    document_id: str,
    *,
    document_type: str = "solution",
    scope_type: str = "solution_specific",
    primary_solution_id: str | None,
    applicable_solution_ids: list[str],
    excluded_solution_ids: list[str] | None = None,
) -> KnowledgeChunkV2:
    return KnowledgeChunkV2.model_validate(
        {
            "chunk_id": chunk_id,
            "document_id": document_id,
            "document_type": document_type,
            "chunk_index": 0,
            "content": "这是一个用于 separability 的 chunk 内容。",
            "token_estimate": 20,
            "metadata": {"section_title": "Section A"},
            "citation_label": "Doc - Section A",
            "scope_type": scope_type,
            "scope_notes": "test",
            "primary_solution_id": primary_solution_id,
            "applicable_solution_ids": applicable_solution_ids,
            "excluded_solution_ids": excluded_solution_ids or [],
        }
    )


def _make_case(*, operational_scope: list[str], forbidden_solution_ids: list[str] | None = None) -> RetrievalEvaluationCaseV2:
    return RetrievalEvaluationCaseV2(
        retrieval_case_id="RET2-TEST",
        source_case_id="DEV-TEST",
        query_type="solution_boundary",
        query="需要 数据 集成，同时保证 安全 合规。",
        runtime_context=RetrievalRuntimeContextV2(
            operational_solution_scope=operational_scope,
            allowed_document_types=["solution", "commercial_rule"],
            industries=["manufacturing"],
            tags=["security"],
            effective_on=date(2026, 7, 1),
        ),
        evaluation_gold=RetrievalEvaluationGoldV2(
            expected_relevant_document_ids=["DOC-EXPECTED"],
            expected_relevant_chunk_ids=[],
            forbidden_document_ids=[],
            forbidden_solution_ids=forbidden_solution_ids or [],
            minimum_relevant_hits=1,
        ),
    )


def test_clause_decomposition_is_deterministic() -> None:
    query = "需要 数据 集成，以及 安全 合规；同时 支持 诊断。"

    clauses_a = _decompose_query(query)
    clauses_b = _decompose_query(query)

    assert clauses_a == clauses_b
    assert clauses_a


def test_runtime_context_augmentation_does_not_include_gold_fields() -> None:
    ids = _solution_ids()
    case = _make_case(operational_scope=[ids[0]], forbidden_solution_ids=[ids[1]])
    runtime_input = RetrievalRuntimeContextV2.model_validate(case.runtime_context.model_dump(mode="json"))
    proxy = type(
        "RuntimeInput",
        (),
        {
            "operational_solution_scope": tuple(runtime_input.operational_solution_scope),
            "allowed_document_types": tuple(runtime_input.allowed_document_types),
            "industries": tuple(runtime_input.industries),
            "tags": tuple(runtime_input.tags),
        },
    )()

    augmented = _augment_query_with_runtime(
        case.query,
        runtime_input=proxy,
        include_scope=True,
        include_document_types=True,
        include_taxonomy=True,
    )

    assert ids[1] not in augmented
    assert "forbidden" not in augmented.lower()


def test_runtime_rule_r3_two_channel_allows_cross_cutting_without_gold() -> None:
    ids = _solution_ids()
    case = _make_case(operational_scope=[ids[0]])
    document = _make_document(
        "DOC-001",
        document_type="commercial_rule",
        scope_type="cross_cutting_requirement",
        primary_solution_id=ids[0],
        applicable_solution_ids=[ids[0], ids[1]],
    )
    chunk = _make_chunk(
        "DOC-001#chunk-0",
        "DOC-001",
        document_type="commercial_rule",
        scope_type="cross_cutting_requirement",
        primary_solution_id=ids[0],
        applicable_solution_ids=[ids[0], ids[1]],
    )
    runtime_input = type(
        "RuntimeInput",
        (),
        {
            "operational_solution_scope": tuple(case.runtime_context.operational_solution_scope),
            "allowed_document_types": tuple(case.runtime_context.allowed_document_types),
            "industries": tuple(),
            "tags": tuple(),
            "effective_on": date(2026, 7, 1),
        },
    )()

    decision = _evaluate_runtime_rule(
        rule_id="R3",
        case=case,
        runtime_input=runtime_input,
        document=document,
        chunk=chunk,
    )

    assert decision["allowed"] is True
    assert decision["channel"] == "cross_cutting_evidence"


def test_runtime_rule_non_oracle_does_not_fail_on_forbidden_solution_scope() -> None:
    ids = _solution_ids()
    case = _make_case(operational_scope=[ids[0]], forbidden_solution_ids=[ids[0]])
    document = _make_document(
        "DOC-002",
        primary_solution_id=ids[0],
        applicable_solution_ids=[ids[0]],
    )
    chunk = _make_chunk(
        "DOC-002#chunk-0",
        "DOC-002",
        primary_solution_id=ids[0],
        applicable_solution_ids=[ids[0]],
    )
    runtime_input = type(
        "RuntimeInput",
        (),
        {
            "operational_solution_scope": tuple(case.runtime_context.operational_solution_scope),
            "allowed_document_types": tuple(case.runtime_context.allowed_document_types),
            "industries": tuple(),
            "tags": tuple(),
            "effective_on": date(2026, 7, 1),
        },
    )()

    non_oracle = _evaluate_runtime_rule(
        rule_id="R2",
        case=case,
        runtime_input=runtime_input,
        document=document,
        chunk=chunk,
    )
    oracle = _evaluate_runtime_rule(
        rule_id="R5",
        case=case,
        runtime_input=runtime_input,
        document=document,
        chunk=chunk,
    )

    assert non_oracle["allowed"] is True
    assert oracle["allowed"] is False


def test_multi_list_rrf_merge_is_stable() -> None:
    merged = _merge_multi_ranked_lists(
        [
            [
                {"rank": 1, "document_id": "DOC-A", "chunk_id": "A#0", "score": 1.0, "candidate_sources": []},
                {"rank": 2, "document_id": "DOC-B", "chunk_id": "B#0", "score": 0.8, "candidate_sources": []},
            ],
            [
                {"rank": 1, "document_id": "DOC-B", "chunk_id": "B#0", "score": 0.9, "candidate_sources": []},
                {"rank": 2, "document_id": "DOC-C", "chunk_id": "C#0", "score": 0.7, "candidate_sources": []},
            ],
        ]
    )

    assert [item["chunk_id"] for item in merged] == ["B#0", "A#0", "C#0"]


def test_case_separability_classification_detects_field_gap() -> None:
    ids = _solution_ids()
    case = _make_case(operational_scope=[ids[0]])
    classification = _classify_case_separability(
        case=case,
        expected_overlaps=[
            {
                "expected_item_id": "DOC-003#chunk-0",
                "query_overlap_with_title": ["诊断"],
                "query_overlap_with_summary": [],
                "query_overlap_with_content": [],
            }
        ],
        expected_ranks={"lexical_v1": {"DOC-003#chunk-0": None}},
        runtime_input=type("RuntimeInput", (), {"operational_solution_scope": tuple(case.runtime_context.operational_solution_scope)})(),
    )

    assert classification == "field_representation_gap"
