from __future__ import annotations

from datetime import date

from evaluation.retrieval.contracts_v2 import (
    RetrievalEvaluationCaseV2,
    RetrievalEvaluationGoldV2,
    RetrievalRuntimeContextV2,
    evaluate_candidate_boundary_v2,
    validate_retrieval_case_feasibility_v2,
)
from knowledge_base.contracts_v2 import KnowledgeChunkV2, KnowledgeDocumentV2, load_demo_solution_ids_v2


def _solutions() -> tuple[str, str, str]:
    solution_ids = load_demo_solution_ids_v2()
    return solution_ids[0], solution_ids[1], solution_ids[2]


def _doc(
    *,
    document_id: str,
    document_type: str,
    primary: str,
    applicable: list[str],
    excluded: list[str],
    scope_type: str,
    industries: list[str] | None = None,
    tags: list[str] | None = None,
) -> KnowledgeDocumentV2:
    return KnowledgeDocumentV2(
        document_id=document_id,
        document_type=document_type,
        status="approved",
        primary_solution_id=primary,
        applicable_solution_ids=applicable,
        excluded_solution_ids=excluded,
        scope_type=scope_type,
        scope_notes="demo",
        industries=industries or ["retail"],
        tags=tags or ["demo"],
    )


def _chunk(
    *,
    chunk_id: str,
    document_id: str,
    document_type: str,
    primary: str,
    applicable: list[str],
    excluded: list[str],
    scope_type: str,
) -> KnowledgeChunkV2:
    return KnowledgeChunkV2(
        chunk_id=chunk_id,
        document_id=document_id,
        document_type=document_type,
        primary_solution_id=primary,
        applicable_solution_ids=applicable,
        excluded_solution_ids=excluded,
        scope_type=scope_type,
        scope_notes="demo",
        industries=["retail"],
        tags=["demo"],
    )


def test_runtime_context_and_gold_are_structurally_isolated() -> None:
    solution_a, _, _ = _solutions()
    case = RetrievalEvaluationCaseV2(
        retrieval_case_id="RET-V2-001",
        source_case_id="DEV-01",
        query_type="solution_discovery",
        query="需要受控检索方案",
        runtime_context=RetrievalRuntimeContextV2(
            operational_solution_scope=[solution_a],
            allowed_document_types=["solution"],
            industries=["retail"],
        ),
        evaluation_gold=RetrievalEvaluationGoldV2(
            expected_relevant_document_ids=["DOC-001"],
            expected_relevant_chunk_ids=[],
            forbidden_document_ids=[],
            forbidden_solution_ids=[],
            minimum_relevant_hits=1,
        ),
    )
    assert case.runtime_context.operational_solution_scope == [solution_a]
    assert case.evaluation_gold.expected_relevant_document_ids == ["DOC-001"]


def test_expected_content_must_be_reachable() -> None:
    solution_a, solution_b, _ = _solutions()
    document = _doc(
        document_id="DOC-001",
        document_type="solution",
        primary=solution_a,
        applicable=[solution_a],
        excluded=[],
        scope_type="solution_specific",
    )
    case = RetrievalEvaluationCaseV2(
        retrieval_case_id="RET-V2-002",
        source_case_id="DEV-02",
        query_type="solution_discovery",
        query="需要受控检索方案",
        runtime_context=RetrievalRuntimeContextV2(
            operational_solution_scope=[solution_b],
            allowed_document_types=["solution"],
            industries=["retail"],
        ),
        evaluation_gold=RetrievalEvaluationGoldV2(
            expected_relevant_document_ids=["DOC-001"],
            minimum_relevant_hits=1,
        ),
    )
    result = validate_retrieval_case_feasibility_v2(
        case=case,
        documents=[document],
        chunks=[],
        evaluation_date=date(2026, 6, 30),
    )
    assert result.feasible is False
    assert "minimum_relevant_hits_exceeds_safe_expected_items" in result.reasons


def test_minimum_relevant_hits_must_be_satisfiable() -> None:
    solution_a, _, _ = _solutions()
    document = _doc(
        document_id="DOC-001",
        document_type="solution",
        primary=solution_a,
        applicable=[solution_a],
        excluded=[],
        scope_type="solution_specific",
    )
    case = RetrievalEvaluationCaseV2(
        retrieval_case_id="RET-V2-003",
        source_case_id="DEV-03",
        query_type="solution_discovery",
        query="需要受控检索方案",
        runtime_context=RetrievalRuntimeContextV2(
            operational_solution_scope=[solution_a],
            allowed_document_types=["solution"],
            industries=["retail"],
        ),
        evaluation_gold=RetrievalEvaluationGoldV2(
            expected_relevant_document_ids=["DOC-001"],
            minimum_relevant_hits=2,
        ),
    )
    result = validate_retrieval_case_feasibility_v2(
        case=case,
        documents=[document],
        chunks=[],
        evaluation_date=date(2026, 6, 30),
    )
    assert result.feasible is False
    assert result.safe_expected_item_count == 1


def test_expected_with_forbidden_scope_is_infeasible() -> None:
    solution_a, solution_b, _ = _solutions()
    document = _doc(
        document_id="DOC-001",
        document_type="solution",
        primary=solution_a,
        applicable=[solution_a, solution_b],
        excluded=[],
        scope_type="multi_solution",
    )
    case = RetrievalEvaluationCaseV2(
        retrieval_case_id="RET-V2-004",
        source_case_id="DEV-04",
        query_type="solution_boundary",
        query="需要边界说明",
        runtime_context=RetrievalRuntimeContextV2(
            operational_solution_scope=[solution_a],
            allowed_document_types=["solution"],
            industries=["retail"],
        ),
        evaluation_gold=RetrievalEvaluationGoldV2(
            expected_relevant_document_ids=["DOC-001"],
            forbidden_solution_ids=[solution_b],
            minimum_relevant_hits=1,
        ),
    )
    result = validate_retrieval_case_feasibility_v2(
        case=case,
        documents=[document],
        chunks=[],
        evaluation_date=date(2026, 6, 30),
    )
    assert result.feasible is False
    assert "expected_relevant_items_conflict_with_boundary" in result.reasons


def test_ret_006_style_case_is_infeasible() -> None:
    solution_a, solution_b, _ = _solutions()
    document = _doc(
        document_id="DOC-001",
        document_type="unsupported_scenario",
        primary=solution_a,
        applicable=[solution_a, solution_b],
        excluded=[],
        scope_type="multi_solution",
    )
    chunk = _chunk(
        chunk_id="DOC-001#chunk-001",
        document_id="DOC-001",
        document_type="unsupported_scenario",
        primary=solution_a,
        applicable=[solution_a, solution_b],
        excluded=[],
        scope_type="multi_solution",
    )
    case = RetrievalEvaluationCaseV2(
        retrieval_case_id="RET-V2-006",
        source_case_id="DEV-08",
        query_type="solution_boundary",
        query="边界说明",
        runtime_context=RetrievalRuntimeContextV2(
            operational_solution_scope=[solution_a],
            allowed_document_types=["unsupported_scenario"],
            industries=["retail"],
        ),
        evaluation_gold=RetrievalEvaluationGoldV2(
            expected_relevant_document_ids=["DOC-001"],
            expected_relevant_chunk_ids=["DOC-001#chunk-001"],
            forbidden_solution_ids=[solution_b],
            minimum_relevant_hits=2,
        ),
    )
    result = validate_retrieval_case_feasibility_v2(
        case=case,
        documents=[document],
        chunks=[chunk],
        evaluation_date=date(2026, 6, 30),
    )
    assert result.feasible is False
    assert "minimum_relevant_hits_exceeds_safe_expected_items" in result.reasons


def test_ret_009_style_case_is_infeasible() -> None:
    solution_a, solution_b, _ = _solutions()
    document = _doc(
        document_id="DOC-001",
        document_type="capability",
        primary=solution_a,
        applicable=[solution_a, solution_b],
        excluded=[],
        scope_type="multi_solution",
    )
    case = RetrievalEvaluationCaseV2(
        retrieval_case_id="RET-V2-009",
        source_case_id="DEV-04",
        query_type="compliance_requirement",
        query="引用和留痕要求",
        runtime_context=RetrievalRuntimeContextV2(
            operational_solution_scope=[solution_a],
            allowed_document_types=["capability"],
            industries=["retail"],
        ),
        evaluation_gold=RetrievalEvaluationGoldV2(
            expected_relevant_document_ids=["DOC-001"],
            forbidden_solution_ids=[solution_b],
            minimum_relevant_hits=1,
        ),
    )
    result = validate_retrieval_case_feasibility_v2(
        case=case,
        documents=[document],
        chunks=[],
        evaluation_date=date(2026, 6, 30),
    )
    assert result.feasible is False
    assert "expected_relevant_items_conflict_with_boundary" in result.reasons


def test_global_policy_is_not_automatic_boundary_violation() -> None:
    solution_ids = list(load_demo_solution_ids_v2())
    document = _doc(
        document_id="DOC-GLOBAL",
        document_type="commercial_rule",
        primary=solution_ids[0],
        applicable=solution_ids,
        excluded=[],
        scope_type="global_policy",
    )
    case = RetrievalEvaluationCaseV2(
        retrieval_case_id="RET-V2-010",
        source_case_id="DEV-10",
        query_type="compliance_requirement",
        query="全局政策",
        runtime_context=RetrievalRuntimeContextV2(
            operational_solution_scope=[solution_ids[0]],
            allowed_document_types=["commercial_rule"],
            industries=["retail"],
        ),
        evaluation_gold=RetrievalEvaluationGoldV2(
            expected_relevant_document_ids=["DOC-GLOBAL"],
            forbidden_solution_ids=[solution_ids[1]],
            minimum_relevant_hits=1,
        ),
    )
    decision = evaluate_candidate_boundary_v2(case=case, document=document)
    assert decision.candidate_allowed is True


def test_operational_filter_excludes_expected_is_infeasible() -> None:
    solution_a, _, _ = _solutions()
    document = _doc(
        document_id="DOC-001",
        document_type="solution",
        primary=solution_a,
        applicable=[solution_a],
        excluded=[],
        scope_type="solution_specific",
        industries=["financial_services"],
    )
    case = RetrievalEvaluationCaseV2(
        retrieval_case_id="RET-V2-011",
        source_case_id="DEV-11",
        query_type="solution_discovery",
        query="需要方案",
        runtime_context=RetrievalRuntimeContextV2(
            operational_solution_scope=[solution_a],
            allowed_document_types=["solution"],
            industries=["retail"],
        ),
        evaluation_gold=RetrievalEvaluationGoldV2(
            expected_relevant_document_ids=["DOC-001"],
            minimum_relevant_hits=1,
        ),
    )
    result = validate_retrieval_case_feasibility_v2(
        case=case,
        documents=[document],
        chunks=[],
        evaluation_date=date(2026, 6, 30),
    )
    assert result.feasible is False
    assert "operational_filters_exclude_all_expected_items" in result.reasons
