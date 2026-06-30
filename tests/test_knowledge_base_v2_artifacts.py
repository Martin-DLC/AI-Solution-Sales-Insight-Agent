from __future__ import annotations

import json
from pathlib import Path

from knowledge_base import (
    KnowledgeChunkV2,
    KnowledgeDocumentV2,
    chunk_content_projection_v1,
    document_content_projection_v1,
    load_knowledge_chunks,
    load_knowledge_documents,
    validate_chunk_scope_against_document_v2,
)


DOCUMENTS_V1_PATH = Path("data/knowledge_base/documents.v1.jsonl")
CHUNKS_V1_PATH = Path("data/knowledge_base/chunks.v1.jsonl")
DOCUMENTS_V2_PATH = Path("data/knowledge_base/documents.v2.jsonl")
CHUNKS_V2_PATH = Path("data/knowledge_base/chunks.v2.jsonl")
MIGRATION_PATH = Path("data/knowledge_base/solution_scope_migration.v2.json")
MANIFEST_PATH = Path("data/knowledge_base/manifest.v2.json")


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_tracked_v2_documents_and_chunks_validate_and_match_counts() -> None:
    documents = [KnowledgeDocumentV2.model_validate(row) for row in _load_jsonl(DOCUMENTS_V2_PATH)]
    chunks = [KnowledgeChunkV2.model_validate(row) for row in _load_jsonl(CHUNKS_V2_PATH)]

    assert len(documents) == 20
    assert len(chunks) == 40


def test_v2_payloads_preserve_v1_business_content_projection() -> None:
    v1_documents = {document.document_id: document for document in load_knowledge_documents(DOCUMENTS_V1_PATH)}
    v1_chunks = {chunk.chunk_id: chunk for chunk in load_knowledge_chunks(CHUNKS_V1_PATH)}
    v2_documents = {row["document_id"]: KnowledgeDocumentV2.model_validate(row) for row in _load_jsonl(DOCUMENTS_V2_PATH)}
    v2_chunks = {row["chunk_id"]: KnowledgeChunkV2.model_validate(row) for row in _load_jsonl(CHUNKS_V2_PATH)}

    for document_id, v1_document in v1_documents.items():
        assert document_content_projection_v1(v1_document) == document_content_projection_v1(v2_documents[document_id])
    for chunk_id, v1_chunk in v1_chunks.items():
        assert chunk_content_projection_v1(v1_chunk) == chunk_content_projection_v1(v2_chunks[chunk_id])


def test_chunk_scope_never_expands_beyond_document_scope() -> None:
    documents = {row["document_id"]: KnowledgeDocumentV2.model_validate(row) for row in _load_jsonl(DOCUMENTS_V2_PATH)}
    chunks = [KnowledgeChunkV2.model_validate(row) for row in _load_jsonl(CHUNKS_V2_PATH)]

    for chunk in chunks:
        validate_chunk_scope_against_document_v2(chunk=chunk, document=documents[chunk.document_id])


def test_global_policy_and_multi_solution_migrations_are_tracked() -> None:
    payload = json.loads(MIGRATION_PATH.read_text(encoding="utf-8"))
    document_records = {row["document_id"]: row for row in payload["document_scope_migrations"]}

    assert document_records["KB-COM-001"]["target_scope_type"] == "global_policy"
    assert payload["stats"]["multi_solution_document_count"] == 14
    assert payload["stats"]["narrowed_scope_chunk_count"] == 4


def test_manifest_v2_hashes_match_tracked_artifacts() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["document_count"] == 20
    assert manifest["chunk_count"] == 40
    assert manifest["contract_version"] == "v2"
    assert manifest["knowledge_base_version"] == "kb-demo-v2"
