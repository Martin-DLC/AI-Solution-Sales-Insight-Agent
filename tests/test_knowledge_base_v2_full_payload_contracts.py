from __future__ import annotations

from copy import deepcopy

import pytest

from knowledge_base import load_knowledge_chunks, load_knowledge_documents
from knowledge_base.contracts_v2 import (
    KnowledgeChunkV2,
    KnowledgeDocumentV2,
    SolutionScopeV2,
    chunk_content_projection_v1,
    content_projection_hash,
    document_content_projection_v1,
)


def _document_scope_from_v1(document_id: str) -> SolutionScopeV2:
    if document_id == "KB-COM-001":
        return SolutionScopeV2(
            primary_solution_id=None,
            applicable_solution_ids=[
                "合规政策RAG检索助手",
                "客户身份统一与数据集成方案",
                "商品知识库RAG方案",
                "客服辅助回复方案",
                "服务工单系统集成方案",
                "私有化大模型部署方案",
            ],
            excluded_solution_ids=[],
            scope_type="global_policy",
            scope_notes="Public demo commercial boundary applies to all demo solutions.",
        )
    return SolutionScopeV2(
        primary_solution_id=document_id and load_knowledge_documents()[0].solution_ids[0],  # placeholder overwritten below
        applicable_solution_ids=[],
        excluded_solution_ids=[],
        scope_type="solution_specific",
        scope_notes="placeholder",
    )


def _scope_for_document(document) -> SolutionScopeV2:
    if document.document_id == "KB-COM-001":
        return _document_scope_from_v1(document.document_id)
    return SolutionScopeV2(
        primary_solution_id=document.solution_ids[0],
        applicable_solution_ids=list(document.solution_ids),
        excluded_solution_ids=[],
        scope_type="solution_specific" if len(document.solution_ids) == 1 else "multi_solution",
        scope_notes="Test scope derived from v1 for payload regression only.",
    )


def _scope_for_chunk(chunk) -> SolutionScopeV2:
    if chunk.document_id == "KB-COM-001":
        return _document_scope_from_v1(chunk.document_id)
    return SolutionScopeV2(
        primary_solution_id=chunk.solution_ids[0],
        applicable_solution_ids=list(chunk.solution_ids),
        excluded_solution_ids=[],
        scope_type="solution_specific" if len(chunk.solution_ids) == 1 else "multi_solution",
        scope_notes="Test scope derived from v1 for payload regression only.",
    )


def test_from_v1_document_preserves_full_payload() -> None:
    source = load_knowledge_documents()[0]
    converted = KnowledgeDocumentV2.from_v1(source, scope=_scope_for_document(source))

    assert converted.document_id == source.document_id
    assert converted.title == source.title
    assert converted.summary == source.summary
    assert converted.content == source.content
    assert converted.source_uri == source.source_uri
    assert converted.document_type == source.document_type
    assert converted.status == source.status
    assert converted.version == source.version
    assert converted.tags == source.tags
    assert converted.industries == source.industries
    assert converted.contract_version == "v2"


def test_from_v1_chunk_preserves_full_payload() -> None:
    source = load_knowledge_chunks()[0]
    converted = KnowledgeChunkV2.from_v1(source, scope=_scope_for_chunk(source))

    assert converted.chunk_id == source.chunk_id
    assert converted.document_id == source.document_id
    assert converted.chunk_index == source.chunk_index
    assert converted.content == source.content
    assert converted.token_estimate == source.token_estimate
    assert converted.metadata == source.metadata
    assert converted.citation_label == source.citation_label
    assert converted.contract_version == "v2"


def test_document_projection_matches_between_v1_and_v2() -> None:
    source = load_knowledge_documents()[0]
    converted = KnowledgeDocumentV2.from_v1(source, scope=_scope_for_document(source))

    assert document_content_projection_v1(source) == document_content_projection_v1(converted)


def test_chunk_projection_matches_between_v1_and_v2() -> None:
    source = load_knowledge_chunks()[0]
    converted = KnowledgeChunkV2.from_v1(source, scope=_scope_for_chunk(source))

    assert chunk_content_projection_v1(source) == chunk_content_projection_v1(converted)


def test_content_hash_is_stable_and_ignores_scope_changes() -> None:
    source = load_knowledge_documents()[0]
    converted = KnowledgeDocumentV2.from_v1(source, scope=_scope_for_document(source))
    projection = document_content_projection_v1(converted)
    first_hash = content_projection_hash(projection)
    second_hash = content_projection_hash(document_content_projection_v1(converted))

    altered_scope = converted.model_copy(
        update={
            "scope_notes": "Changed scope only.",
            "excluded_solution_ids": ["客服辅助回复方案"] if "客服辅助回复方案" not in converted.applicable_solution_ids else [],
        }
    )
    assert first_hash == second_hash
    assert first_hash == content_projection_hash(document_content_projection_v1(altered_scope))


def test_projection_detects_content_change() -> None:
    source = load_knowledge_documents()[0]
    converted = KnowledgeDocumentV2.from_v1(source, scope=_scope_for_document(source))
    changed = converted.model_copy(update={"content": converted.content + "新增内容"})
    assert document_content_projection_v1(converted) != document_content_projection_v1(changed)


def test_projection_detects_title_or_source_change() -> None:
    source = load_knowledge_documents()[0]
    converted = KnowledgeDocumentV2.from_v1(source, scope=_scope_for_document(source))
    changed_title = converted.model_copy(update={"title": "不同标题"})
    changed_source = converted.model_copy(update={"source_uri": "synthetic://other/source"})
    assert document_content_projection_v1(converted) != document_content_projection_v1(changed_title)
    assert document_content_projection_v1(converted) != document_content_projection_v1(changed_source)


def test_v2_formal_scope_does_not_persist_legacy_solution_ids() -> None:
    source = load_knowledge_documents()[0]
    converted = KnowledgeDocumentV2.from_v1(source, scope=_scope_for_document(source))
    dumped = converted.model_dump(mode="json")
    assert "solution_ids" not in dumped


def test_v2_conversion_requires_explicit_scope() -> None:
    source = load_knowledge_documents()[0]
    with pytest.raises(TypeError):
        KnowledgeDocumentV2.from_v1(source)  # type: ignore[misc]


def test_chunk_projection_preserves_boundary_fields_but_not_scope_fields() -> None:
    source = load_knowledge_chunks()[0]
    converted = KnowledgeChunkV2.from_v1(source, scope=_scope_for_chunk(source))
    projection = chunk_content_projection_v1(converted)
    assert "applicable_solution_ids" not in projection
    assert projection["chunk_index"] == source.chunk_index
    assert projection["content"] == source.content


def test_extra_fields_are_forbidden() -> None:
    source = load_knowledge_documents()[0]
    payload = KnowledgeDocumentV2.from_v1(source, scope=_scope_for_document(source)).model_dump(mode="json")
    payload["unexpected"] = "boom"
    with pytest.raises(ValueError):
        KnowledgeDocumentV2.model_validate(payload)
