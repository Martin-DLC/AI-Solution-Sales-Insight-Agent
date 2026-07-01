from __future__ import annotations

import json
from pathlib import Path

from evaluation.retrieval.contracts_v2 import RetrievalEvaluationCaseV2, RetrievalEvaluationGoldV2, RetrievalRuntimeContextV2
from evaluation.retrieval.counterfactuals_v2 import (
    COUNTERFACTUAL_OUTPUT_PATH,
    _build_method_run,
    _evaluate_counterfactual_combo,
    _evaluate_scope_strategy,
    _select_counterfactual_top5,
    _strategy_definitions,
    build_plan_payload,
)
from knowledge_base.contracts_v2 import KnowledgeChunkV2, KnowledgeDocumentV2, load_demo_solution_ids_v2


def _solution_ids() -> tuple[str, ...]:
    ids = load_demo_solution_ids_v2()
    assert len(ids) == 6
    return ids


def _make_case(
    *,
    operational_scope: list[str],
    expected_chunks: list[str],
    forbidden_solution_ids: list[str] | None = None,
) -> RetrievalEvaluationCaseV2:
    return RetrievalEvaluationCaseV2(
        retrieval_case_id="RET2-TEST",
        source_case_id="DEV-TEST",
        query_type="solution_boundary",
        query="scope fit test",
        runtime_context=RetrievalRuntimeContextV2(
            operational_solution_scope=operational_scope,
            allowed_document_types=["solution", "capability", "global_policy"],
        ),
        evaluation_gold=RetrievalEvaluationGoldV2(
            expected_relevant_document_ids=[],
            expected_relevant_chunk_ids=expected_chunks,
            forbidden_document_ids=[],
            forbidden_solution_ids=forbidden_solution_ids or [],
            minimum_relevant_hits=1,
        ),
    )


def _make_document(
    document_id: str,
    *,
    primary_solution_id: str | None,
    applicable_solution_ids: list[str],
    scope_type: str,
    document_type: str = "solution",
    excluded_solution_ids: list[str] | None = None,
) -> KnowledgeDocumentV2:
    return KnowledgeDocumentV2(
        document_id=document_id,
        title=document_id,
        document_type=document_type,
        status="approved",
        summary="这是一个足够长的测试摘要。",
        content="这是一个足够长的测试正文内容，用于反事实矩阵单元测试。",
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
    document_type: str = "solution",
    excluded_solution_ids: list[str] | None = None,
) -> KnowledgeChunkV2:
    return KnowledgeChunkV2(
        chunk_id=chunk_id,
        document_id=document_id,
        document_type=document_type,
        chunk_index=0,
        content="这是一个足够长的 chunk 内容，用于反事实矩阵测试。",
        token_estimate=32,
        primary_solution_id=primary_solution_id,
        applicable_solution_ids=applicable_solution_ids,
        excluded_solution_ids=excluded_solution_ids or [],
        scope_type=scope_type,
        scope_notes="test",
        citation_label=chunk_id,
    )


def test_plan_payload_keeps_formal_hashes_and_does_not_require_model_loading() -> None:
    payload = build_plan_payload()

    assert payload["mode"] == "plan"
    assert payload["diagnostic_only"] is True
    assert payload["formal_result_hashes"]
    assert payload["diagnosis_hash"]


def test_scope_strategies_keep_global_policy_exception_and_strict_subset() -> None:
    ids = _solution_ids()
    doc = _make_document(
        "DOC-GLOBAL",
        primary_solution_id=None,
        applicable_solution_ids=list(ids),
        scope_type="global_policy",
        document_type="commercial_rule",
    )
    case = _make_case(operational_scope=[ids[0]], expected_chunks=["DOC-GLOBAL#chunk-0"])
    runtime_input = type("RuntimeInput", (), {
        "operational_solution_scope": tuple(case.runtime_context.operational_solution_scope),
        "allowed_document_types": tuple(case.runtime_context.allowed_document_types),
        "industries": tuple(),
        "tags": tuple(),
        "effective_on": case.runtime_context.effective_on or __import__("datetime").date(2026, 7, 1),
    })()
    source_view = type("SourceView", (), {
        "scope_type": doc.scope_type.value,
        "primary_solution_id": doc.primary_solution_id,
        "applicable_solution_ids": tuple(doc.applicable_solution_ids),
        "excluded_solution_ids": tuple(doc.excluded_solution_ids),
        "industries": tuple(doc.industries),
        "tags": tuple(doc.tags),
        "document_type": doc.document_type.value,
        "document": doc,
        "chunk": None,
    })()

    assert _evaluate_scope_strategy(strategy="S1", case=case, runtime_input=runtime_input, source_view=source_view)["allowed"] is True

    multi = _make_document(
        "DOC-MULTI",
        primary_solution_id=ids[0],
        applicable_solution_ids=[ids[0], ids[1]],
        scope_type="multi_solution",
    )
    multi_view = type("SourceView", (), {
        "scope_type": multi.scope_type.value,
        "primary_solution_id": multi.primary_solution_id,
        "applicable_solution_ids": tuple(multi.applicable_solution_ids),
        "excluded_solution_ids": tuple(multi.excluded_solution_ids),
        "industries": tuple(multi.industries),
        "tags": tuple(multi.tags),
        "document_type": multi.document_type.value,
        "document": multi,
        "chunk": None,
    })()

    assert _evaluate_scope_strategy(strategy="S0", case=case, runtime_input=runtime_input, source_view=multi_view)["allowed"] is True
    assert _evaluate_scope_strategy(strategy="S1", case=case, runtime_input=runtime_input, source_view=multi_view)["allowed"] is False


def test_oracle_strategy_is_explicitly_gold_aware_and_runtime_safe_strategy_is_not() -> None:
    ids = _solution_ids()
    case = _make_case(
        operational_scope=[ids[0]],
        expected_chunks=["DOC-001#chunk-0"],
        forbidden_solution_ids=[ids[1]],
    )
    doc = _make_document(
        "DOC-001",
        primary_solution_id=ids[0],
        applicable_solution_ids=[ids[0], ids[1]],
        scope_type="multi_solution",
    )
    chunk = _make_chunk(
        "DOC-001#chunk-0",
        "DOC-001",
        primary_solution_id=ids[0],
        applicable_solution_ids=[ids[0], ids[1]],
        scope_type="multi_solution",
    )
    runtime_input = type("RuntimeInput", (), {
        "operational_solution_scope": tuple(case.runtime_context.operational_solution_scope),
        "allowed_document_types": tuple(case.runtime_context.allowed_document_types),
        "industries": tuple(),
        "tags": tuple(),
        "effective_on": __import__("datetime").date(2026, 7, 1),
    })()
    source_view = type("SourceView", (), {
        "scope_type": chunk.scope_type.value,
        "primary_solution_id": chunk.primary_solution_id,
        "applicable_solution_ids": tuple(chunk.applicable_solution_ids),
        "excluded_solution_ids": tuple(chunk.excluded_solution_ids),
        "industries": tuple(chunk.industries),
        "tags": tuple(chunk.tags),
        "document_type": chunk.document_type.value,
        "document": doc,
        "chunk": chunk,
    })()

    runtime_safe = _evaluate_scope_strategy(strategy="S0", case=case, runtime_input=runtime_input, source_view=source_view)
    oracle = _evaluate_scope_strategy(strategy="S4", case=case, runtime_input=runtime_input, source_view=source_view)

    assert runtime_safe["oracle_only"] is False
    assert runtime_safe["allowed"] is True
    assert oracle["oracle_only"] is True
    assert oracle["allowed"] is False


def test_selection_applies_diversity_and_stable_backfill() -> None:
    ids = _solution_ids()
    case = _make_case(operational_scope=[ids[0]], expected_chunks=["DOC-A#chunk-2"])
    doc_a = _make_document("DOC-A", primary_solution_id=ids[0], applicable_solution_ids=[ids[0]], scope_type="solution_specific")
    doc_b = _make_document("DOC-B", primary_solution_id=ids[0], applicable_solution_ids=[ids[0]], scope_type="solution_specific")
    chunks_by_id = {
        f"DOC-A#chunk-{i}": _make_chunk(
            f"DOC-A#chunk-{i}",
            "DOC-A",
            primary_solution_id=ids[0],
            applicable_solution_ids=[ids[0]],
            scope_type="solution_specific",
        )
        for i in range(3)
    }
    chunks_by_id["DOC-B#chunk-0"] = _make_chunk(
        "DOC-B#chunk-0",
        "DOC-B",
        primary_solution_id=ids[0],
        applicable_solution_ids=[ids[0]],
        scope_type="solution_specific",
    )
    documents_by_id = {"DOC-A": doc_a, "DOC-B": doc_b}
    runtime_input = type("RuntimeInput", (), {
        "operational_solution_scope": tuple(case.runtime_context.operational_solution_scope),
        "allowed_document_types": tuple(case.runtime_context.allowed_document_types),
        "industries": tuple(),
        "tags": tuple(),
        "effective_on": __import__("datetime").date(2026, 7, 1),
    })()
    candidates = [
        {"rank": 1, "document_id": "DOC-A", "chunk_id": "DOC-A#chunk-0", "document_type": "solution", "score": 1.0},
        {"rank": 2, "document_id": "DOC-A", "chunk_id": "DOC-A#chunk-1", "document_type": "solution", "score": 0.9},
        {"rank": 3, "document_id": "DOC-A", "chunk_id": "DOC-A#chunk-2", "document_type": "solution", "score": 0.8},
        {"rank": 4, "document_id": "DOC-B", "chunk_id": "DOC-B#chunk-0", "document_type": "solution", "score": 0.7},
    ]

    selected, stats = _select_counterfactual_top5(
        case=case,
        runtime_input=runtime_input,
        candidates=candidates,
        documents_by_id=documents_by_id,
        chunks_by_id=chunks_by_id,
        strategy="S1",
        pool_size=4,
        diversity_mode="max_1_chunk_per_document",
        rerank_mode="original_rank",
    )

    assert [item["chunk_id"] for item in selected] == ["DOC-A#chunk-0", "DOC-B#chunk-0"]
    assert stats["diversity_skipped_candidate_count"] == 2
    assert stats["backfilled_candidate_count"] == 0


def test_runtime_scope_fit_selection_does_not_depend_on_gold_fields() -> None:
    ids = _solution_ids()
    doc_primary = _make_document("DOC-PRIMARY", primary_solution_id=ids[0], applicable_solution_ids=[ids[0]], scope_type="solution_specific")
    doc_multi = _make_document("DOC-MULTI", primary_solution_id=ids[1], applicable_solution_ids=[ids[0], ids[1]], scope_type="multi_solution")
    chunk_primary = _make_chunk("DOC-PRIMARY#chunk-0", "DOC-PRIMARY", primary_solution_id=ids[0], applicable_solution_ids=[ids[0]], scope_type="solution_specific")
    chunk_multi = _make_chunk("DOC-MULTI#chunk-0", "DOC-MULTI", primary_solution_id=ids[1], applicable_solution_ids=[ids[0], ids[1]], scope_type="multi_solution")
    documents_by_id = {"DOC-PRIMARY": doc_primary, "DOC-MULTI": doc_multi}
    chunks_by_id = {
        "DOC-PRIMARY#chunk-0": chunk_primary,
        "DOC-MULTI#chunk-0": chunk_multi,
    }
    candidates = [
        {"rank": 1, "document_id": "DOC-MULTI", "chunk_id": "DOC-MULTI#chunk-0", "document_type": "solution", "score": 0.9},
        {"rank": 2, "document_id": "DOC-PRIMARY", "chunk_id": "DOC-PRIMARY#chunk-0", "document_type": "solution", "score": 0.8},
    ]
    runtime_input = type("RuntimeInput", (), {
        "operational_solution_scope": (ids[0],),
        "allowed_document_types": ("solution",),
        "industries": tuple(),
        "tags": tuple(),
        "effective_on": __import__("datetime").date(2026, 7, 1),
    })()
    case_a = _make_case(operational_scope=[ids[0]], expected_chunks=["DOC-PRIMARY#chunk-0"], forbidden_solution_ids=[])
    case_b = _make_case(operational_scope=[ids[0]], expected_chunks=["DOC-MULTI#chunk-0"], forbidden_solution_ids=[ids[1]])

    selected_a, _ = _select_counterfactual_top5(
        case=case_a,
        runtime_input=runtime_input,
        candidates=candidates,
        documents_by_id=documents_by_id,
        chunks_by_id=chunks_by_id,
        strategy="S1",
        pool_size=2,
        diversity_mode="no_diversity",
        rerank_mode="runtime_scope_fit",
    )
    selected_b, _ = _select_counterfactual_top5(
        case=case_b,
        runtime_input=runtime_input,
        candidates=candidates,
        documents_by_id=documents_by_id,
        chunks_by_id=chunks_by_id,
        strategy="S1",
        pool_size=2,
        diversity_mode="no_diversity",
        rerank_mode="runtime_scope_fit",
    )

    assert [item["chunk_id"] for item in selected_a] == [item["chunk_id"] for item in selected_b]


def test_combo_evaluation_is_deterministic_and_stays_blocked() -> None:
    ids = _solution_ids()
    case = _make_case(operational_scope=[ids[0]], expected_chunks=["DOC-001#chunk-0"])
    document = _make_document("DOC-001", primary_solution_id=ids[0], applicable_solution_ids=[ids[0]], scope_type="solution_specific")
    chunk = _make_chunk("DOC-001#chunk-0", "DOC-001", primary_solution_id=ids[0], applicable_solution_ids=[ids[0]], scope_type="solution_specific")
    documents_by_id = {"DOC-001": document}
    chunks_by_id = {"DOC-001#chunk-0": chunk}
    diagnostic_case_result = {
        "retrieval_case_id": case.retrieval_case_id,
        "candidates": [
            {
                "rank": 1,
                "document_id": "DOC-001",
                "chunk_id": "DOC-001#chunk-0",
                "document_type": "solution",
                "score": 1.0,
                "scope_type": "solution_specific",
                "applicable_solution_ids": [ids[0]],
                "boundary_violation": False,
            }
        ],
    }
    method_run = _build_method_run(method_id="lexical_v1", case_results=[diagnostic_case_result])
    runtime_inputs = {
        case.retrieval_case_id: type("RuntimeInput", (), {
            "operational_solution_scope": tuple(case.runtime_context.operational_solution_scope),
            "allowed_document_types": tuple(case.runtime_context.allowed_document_types),
            "industries": tuple(),
            "tags": tuple(),
            "effective_on": __import__("datetime").date(2026, 7, 1),
        })()
    }
    blocking_gate = json.loads(Path("data/evaluation/retrieval/retrieval_benchmark_config.v2.json").read_text(encoding="utf-8"))["blocking_gate"]

    first = _evaluate_counterfactual_combo(
        method_id="lexical_v1",
        method_run=method_run,
        cases=[case],
        runtime_inputs=runtime_inputs,
        documents_by_id=documents_by_id,
        chunks_by_id=chunks_by_id,
        strategy="S1",
        pool_size=5,
        diversity_mode="no_diversity",
        rerank_mode="original_rank",
        blocking_gate=blocking_gate,
    )
    second = _evaluate_counterfactual_combo(
        method_id="lexical_v1",
        method_run=method_run,
        cases=[case],
        runtime_inputs=runtime_inputs,
        documents_by_id=documents_by_id,
        chunks_by_id=chunks_by_id,
        strategy="S1",
        pool_size=5,
        diversity_mode="no_diversity",
        rerank_mode="original_rank",
        blocking_gate=blocking_gate,
    )

    assert first == second
    assert _strategy_definitions()["S4"]["oracle_only"] is True
    if COUNTERFACTUAL_OUTPUT_PATH.exists():
        tracked = json.loads(COUNTERFACTUAL_OUTPUT_PATH.read_text(encoding="utf-8"))
        assert tracked["architecture_c_status"] == "blocked"
