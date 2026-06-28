from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from knowledge_base.models import (
    KnowledgeBaseCorpus,
    KnowledgeChunk,
    KnowledgeConfidentiality,
    KnowledgeDocument,
    KnowledgeDocumentType,
    KnowledgeSourceStatus,
    KnowledgeValidationStatus,
    build_manifest,
)


def sample_document(**overrides):
    payload = {
        "document_id": "KB-SOL-001",
        "title": "Service Risk Dashboard",
        "document_type": KnowledgeDocumentType.solution,
        "status": KnowledgeSourceStatus.approved,
        "version": "1.0",
        "effective_from": date(2026, 1, 1),
        "effective_until": date(2026, 12, 31),
        "owner": "solution-marketing",
        "summary": "Synthetic solution profile for service risk visibility.",
        "content": "Service Risk Dashboard supports renewal visibility, operational health tracking, and service manager review workflows.",
        "tags": ["service", "renewal", "service"],
        "industries": ["field_services", "field_services"],
        "solution_ids": ["service-risk-dashboard", "service-risk-dashboard"],
        "source_uri": "knowledge/solutions/service-risk-dashboard.md",
        "confidentiality": KnowledgeConfidentiality.synthetic_demo,
        "created_at": datetime(2026, 6, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 6, 2, tzinfo=UTC),
    }
    payload.update(overrides)
    return KnowledgeDocument.model_validate(payload)


def sample_chunk(**overrides):
    content = overrides.pop("content", "Dashboard module supports renewal-risk review and queue triage.")
    payload = {
        "chunk_id": KnowledgeChunk.build_chunk_id(
            document_id="KB-SOL-001",
            chunk_index=0,
            content=content,
        ),
        "document_id": "KB-SOL-001",
        "document_type": KnowledgeDocumentType.solution,
        "chunk_index": 0,
        "content": content,
        "token_estimate": 24,
        "tags": ["service", "service"],
        "industries": ["field_services"],
        "solution_ids": ["service-risk-dashboard", "service-risk-dashboard"],
        "metadata": {"section": "overview", "priority": 1},
        "citation_label": "KB-SOL-001 §overview",
    }
    payload.update(overrides)
    return KnowledgeChunk.model_validate(payload)


def test_document_lists_are_deduplicated() -> None:
    document = sample_document()

    assert document.tags == ["service", "renewal"]
    assert document.industries == ["field_services"]
    assert document.solution_ids == ["service-risk-dashboard"]


def test_document_status_enum_is_supported() -> None:
    document = sample_document(status=KnowledgeSourceStatus.draft)

    assert document.status is KnowledgeSourceStatus.draft


def test_document_rejects_invalid_date_range() -> None:
    with pytest.raises(ValueError, match="effective_until"):
        sample_document(
            effective_from=date(2026, 12, 31),
            effective_until=date(2026, 1, 1),
        )


def test_deprecated_document_is_not_retrieval_eligible() -> None:
    document = sample_document(status=KnowledgeSourceStatus.deprecated)

    assert document.is_retrieval_eligible() is False


def test_expired_document_is_detected_from_status_or_date() -> None:
    expired_by_status = sample_document(status=KnowledgeSourceStatus.expired)
    expired_by_date = sample_document(
        effective_from=date(2024, 1, 1),
        effective_until=date(2025, 1, 1),
    )

    assert expired_by_status.is_expired() is True
    assert expired_by_date.is_expired(as_of=date(2026, 6, 29)) is True


def test_document_rejects_http_source_uri() -> None:
    with pytest.raises(ValueError, match="HTTP URL"):
        sample_document(source_uri="https://example.com/kb.md")


def test_chunk_id_builder_is_stable() -> None:
    first = KnowledgeChunk.build_chunk_id(
        document_id="KB-SOL-001",
        chunk_index=2,
        content="same content",
    )
    second = KnowledgeChunk.build_chunk_id(
        document_id="KB-SOL-001",
        chunk_index=2,
        content="same content",
    )

    assert first == second


def test_chunk_rejects_negative_index() -> None:
    with pytest.raises(ValueError, match="chunk_index"):
        sample_chunk(chunk_index=-1)


def test_chunk_rejects_non_positive_token_estimate() -> None:
    with pytest.raises(ValueError, match="token_estimate"):
        sample_chunk(token_estimate=0)


def test_chunk_rejects_non_json_safe_metadata() -> None:
    with pytest.raises(ValueError, match="JSON-safe"):
        sample_chunk(metadata={"bad": {1, 2, 3}})


def test_manifest_counts_are_built_correctly() -> None:
    document = sample_document()
    chunk = sample_chunk()

    manifest = build_manifest(
        knowledge_base_version="kb-v1",
        documents=[document],
        chunks=[chunk],
        validation_status=KnowledgeValidationStatus.valid,
    )

    assert manifest.document_count == 1
    assert manifest.chunk_count == 1
    assert manifest.document_type_counts == {KnowledgeDocumentType.solution: 1}
    assert manifest.solution_ids == ["service-risk-dashboard"]
    assert manifest.synthetic_data is True


def test_corpus_enforces_document_id_uniqueness_and_manifest_alignment() -> None:
    document = sample_document()
    chunk = sample_chunk()
    manifest = build_manifest(
        knowledge_base_version="kb-v1",
        documents=[document],
        chunks=[chunk],
    )

    corpus = KnowledgeBaseCorpus(
        documents=[document],
        chunks=[chunk],
        manifest=manifest,
    )

    assert corpus.manifest.document_count == 1

    with pytest.raises(ValueError, match="document IDs must be unique"):
        KnowledgeBaseCorpus(
            documents=[document, document],
            chunks=[chunk],
            manifest=manifest,
        )
