from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from knowledge_base.chunking import build_knowledge_chunks
from knowledge_base.dataset import load_knowledge_documents
from knowledge_base.models import (
    KnowledgeConfidentiality,
    KnowledgeDocument,
    KnowledgeDocumentType,
    KnowledgeSourceStatus,
)


def _sample_document(content: str) -> KnowledgeDocument:
    return KnowledgeDocument(
        document_id="KB-TEST-001",
        title="Synthetic Test Document",
        document_type=KnowledgeDocumentType.capability,
        status=KnowledgeSourceStatus.approved,
        version="1.0",
        effective_from=datetime(2026, 6, 1, tzinfo=UTC).date(),
        effective_until=datetime(2027, 6, 1, tzinfo=UTC).date(),
        owner="synthetic-test",
        summary="Synthetic chunking test document.",
        content=content,
        tags=["demo"],
        industries=["retail"],
        solution_ids=["客服辅助回复方案"],
        source_uri="synthetic://enterprise-demo/tests/chunking",
        confidentiality=KnowledgeConfidentiality.synthetic_demo,
        created_at=datetime(2026, 6, 29, tzinfo=UTC),
        updated_at=datetime(2026, 6, 29, tzinfo=UTC),
    )


def test_chunk_builder_is_deterministic_on_real_dataset() -> None:
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")

    first = [chunk.model_dump(mode="json") for chunk in build_knowledge_chunks(documents)]
    second = [chunk.model_dump(mode="json") for chunk in build_knowledge_chunks(documents)]

    assert first == second


def test_real_dataset_chunk_count_is_within_expected_range() -> None:
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")
    chunks = build_knowledge_chunks(documents)

    assert 40 <= len(chunks) <= 70


def test_chunk_ids_are_unique_and_stable() -> None:
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")
    chunks = build_knowledge_chunks(documents)

    chunk_ids = [chunk.chunk_id for chunk in chunks]
    assert len(chunk_ids) == len(set(chunk_ids))
    assert chunk_ids == [chunk.chunk_id for chunk in build_knowledge_chunks(documents)]


def test_chunk_order_preserves_document_order() -> None:
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")
    chunks = build_knowledge_chunks(documents)

    first_chunk_by_document = {}
    for position, chunk in enumerate(chunks):
        first_chunk_by_document.setdefault(chunk.document_id, position)

    document_order = [document.document_id for document in documents]
    assert list(first_chunk_by_document) == document_order


def test_chunk_indexes_are_continuous_per_document() -> None:
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")
    chunks = build_knowledge_chunks(documents)

    indexes = defaultdict(list)
    for chunk in chunks:
        indexes[chunk.document_id].append(chunk.chunk_index)

    for values in indexes.values():
        assert values == list(range(len(values)))


def test_markdown_sections_split_into_distinct_chunks() -> None:
    document = _sample_document(
        "## First Section\n"
        "This section explains a confirmed capability and keeps enough detail for one chunk.\n\n"
        "## Second Section\n"
        "This section explains a boundary and stays separate because the heading changed."
    )

    chunks = build_knowledge_chunks([document], max_chars=400, min_chars=120)

    assert len(chunks) == 2
    assert chunks[0].citation_label.endswith("First Section")
    assert chunks[1].citation_label.endswith("Second Section")


def test_long_paragraph_splits_on_safe_boundaries() -> None:
    paragraph = (
        "## Section\n"
        "First sentence is deliberately long enough to help the splitter work. "
        "Second sentence continues the same topic and should stay within a safe boundary. "
        "Third sentence keeps adding detail so the final result requires multiple chunks."
    )
    document = _sample_document(paragraph)

    chunks = build_knowledge_chunks([document], max_chars=120, min_chars=40)

    assert len(chunks) >= 2
    assert all(len(chunk.content) <= 120 for chunk in chunks)


def test_overlong_sentence_uses_safe_hard_split() -> None:
    document = _sample_document(
        "## Section\n" + ("A" * 260)
    )

    chunks = build_knowledge_chunks([document], max_chars=100, min_chars=20)

    assert len(chunks) >= 3
    assert all(len(chunk.content) <= 100 for chunk in chunks)


def test_token_estimate_is_positive_and_stable() -> None:
    document = _sample_document("## Section\nA compact synthetic section for token estimation stability.")

    first = build_knowledge_chunks([document])[0]
    second = build_knowledge_chunks([document])[0]

    assert first.token_estimate > 0
    assert first.token_estimate == second.token_estimate


def test_chunk_metadata_and_solution_ids_inherit_from_document() -> None:
    document = _sample_document("## Section\nSynthetic content for metadata inheritance checks.")

    chunk = build_knowledge_chunks([document])[0]

    assert chunk.solution_ids == document.solution_ids
    assert chunk.tags == document.tags
    assert chunk.industries == document.industries
    assert chunk.metadata["source_uri"] == document.source_uri
    assert chunk.metadata["status"] == document.status.value


def test_chunk_dump_does_not_include_embedding_field() -> None:
    document = _sample_document("## Section\nSynthetic content for serialization checks.")

    payload = build_knowledge_chunks([document])[0].model_dump(mode="json")

    assert "embedding" not in payload
