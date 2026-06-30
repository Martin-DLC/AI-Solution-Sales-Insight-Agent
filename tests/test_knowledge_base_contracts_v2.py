from __future__ import annotations

from datetime import date

import pytest

from knowledge_base.contracts_v2 import (
    KnowledgeChunkV2,
    KnowledgeDocumentV2,
    SolutionScopeType,
    load_demo_solution_ids_v2,
    validate_chunk_scope_against_document_v2,
)


def _solutions() -> tuple[str, str, str]:
    solution_ids = load_demo_solution_ids_v2()
    return solution_ids[0], solution_ids[1], solution_ids[2]


def test_primary_solution_must_belong_to_applicable() -> None:
    solution_a, solution_b, _ = _solutions()
    with pytest.raises(ValueError, match="primary_solution_id must belong"):
        KnowledgeDocumentV2(
            document_id="DOC-001",
            document_type="solution",
            status="approved",
            primary_solution_id=solution_a,
            applicable_solution_ids=[solution_b],
            excluded_solution_ids=[],
            scope_type="solution_specific",
            scope_notes="demo",
        )


def test_applicable_and_excluded_must_not_overlap() -> None:
    solution_a, _, _ = _solutions()
    with pytest.raises(ValueError, match="must not overlap"):
        KnowledgeDocumentV2(
            document_id="DOC-001",
            document_type="solution",
            status="approved",
            primary_solution_id=solution_a,
            applicable_solution_ids=[solution_a],
            excluded_solution_ids=[solution_a],
            scope_type="solution_specific",
            scope_notes="demo",
        )


def test_solution_specific_requires_exactly_one_solution() -> None:
    solution_a, solution_b, _ = _solutions()
    with pytest.raises(ValueError, match="exactly 1 applicable"):
        KnowledgeDocumentV2(
            document_id="DOC-001",
            document_type="solution",
            status="approved",
            primary_solution_id=solution_a,
            applicable_solution_ids=[solution_a, solution_b],
            excluded_solution_ids=[],
            scope_type="solution_specific",
            scope_notes="demo",
        )


def test_multi_solution_requires_at_least_two_solutions() -> None:
    solution_a, _, _ = _solutions()
    with pytest.raises(ValueError, match="at least 2 applicable solutions"):
        KnowledgeDocumentV2(
            document_id="DOC-001",
            document_type="solution",
            status="approved",
            primary_solution_id=solution_a,
            applicable_solution_ids=[solution_a],
            excluded_solution_ids=[],
            scope_type="multi_solution",
            scope_notes="demo",
        )


def test_global_policy_is_valid_without_boundary_failure() -> None:
    solution_ids = list(load_demo_solution_ids_v2())
    document = KnowledgeDocumentV2(
        document_id="DOC-001",
        document_type="commercial_rule",
        status="approved",
        primary_solution_id=solution_ids[0],
        applicable_solution_ids=solution_ids,
        excluded_solution_ids=[],
        scope_type="global_policy",
        scope_notes="Applies to the whole demo scope.",
        effective_from=date(2026, 1, 1),
    )
    assert document.scope_type is SolutionScopeType.global_policy


def test_chunk_can_only_narrow_document_scope() -> None:
    solution_a, solution_b, solution_c = _solutions()
    document = KnowledgeDocumentV2(
        document_id="DOC-001",
        document_type="implementation_playbook",
        status="approved",
        primary_solution_id=solution_a,
        applicable_solution_ids=[solution_a, solution_b],
        excluded_solution_ids=[solution_c],
        scope_type="multi_solution",
        scope_notes="Shared implementation playbook.",
    )
    chunk = KnowledgeChunkV2(
        chunk_id="DOC-001#chunk-001",
        document_id="DOC-001",
        document_type="implementation_playbook",
        primary_solution_id=solution_a,
        applicable_solution_ids=[solution_a],
        excluded_solution_ids=[solution_c],
        scope_type="solution_specific",
        scope_notes="Narrowed to one solution.",
    )
    validate_chunk_scope_against_document_v2(chunk=chunk, document=document)


def test_chunk_cannot_expand_document_scope() -> None:
    solution_a, solution_b, solution_c = _solutions()
    document = KnowledgeDocumentV2(
        document_id="DOC-001",
        document_type="implementation_playbook",
        status="approved",
        primary_solution_id=solution_a,
        applicable_solution_ids=[solution_a, solution_b],
        excluded_solution_ids=[solution_c],
        scope_type="multi_solution",
        scope_notes="Shared implementation playbook.",
    )
    chunk = KnowledgeChunkV2(
        chunk_id="DOC-001#chunk-001",
        document_id="DOC-001",
        document_type="implementation_playbook",
        primary_solution_id=solution_c,
        applicable_solution_ids=[solution_a, solution_c],
        excluded_solution_ids=[],
        scope_type="multi_solution",
        scope_notes="Incorrectly expanded scope.",
    )
    with pytest.raises(ValueError, match="must not expand"):
        validate_chunk_scope_against_document_v2(chunk=chunk, document=document)


def test_demo_scope_rejects_unknown_solution_id() -> None:
    solution_a, _, _ = _solutions()
    with pytest.raises(ValueError, match="6-solution demo scope"):
        KnowledgeDocumentV2(
            document_id="DOC-001",
            document_type="solution",
            status="approved",
            primary_solution_id=solution_a,
            applicable_solution_ids=[solution_a, "不存在的方案ID"],
            excluded_solution_ids=[],
            scope_type="multi_solution",
            scope_notes="demo",
        )
