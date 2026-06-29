from __future__ import annotations

from collections import Counter

import pytest

from knowledge_base.chunking import build_knowledge_chunks
from knowledge_base.dataset import (
    load_demo_solution_scope,
    load_knowledge_documents,
    load_knowledge_manifest,
    validate_knowledge_base_dataset,
)
from knowledge_base.models import KnowledgeDocumentType


def _allowed_solution_ids() -> set[str]:
    scope = load_demo_solution_scope("data/knowledge_base/demo_solution_scope.v1.json")
    return set(scope.selected_solution_ids) | set(scope.excluded_solution_ids)


def test_demo_scope_counts_and_selected_ids_are_fixed() -> None:
    scope = load_demo_solution_scope("data/knowledge_base/demo_solution_scope.v1.json")

    assert scope.source_solution_id_count == 63
    assert scope.selected_solution_id_count == 6
    assert len(scope.selected_solution_ids) == 6
    assert len(scope.excluded_solution_ids) == 57
    assert scope.synthetic_data is True


def test_documents_file_contains_exactly_20_documents() -> None:
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")

    assert len(documents) == 20


def test_all_10_document_types_are_present() -> None:
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")

    assert {document.document_type for document in documents} == set(KnowledgeDocumentType)


def test_document_ids_are_unique() -> None:
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")

    document_ids = [document.document_id for document in documents]
    assert len(document_ids) == len(set(document_ids))


def test_all_document_solution_ids_stay_inside_demo_scope() -> None:
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")
    selected = set(load_demo_solution_scope("data/knowledge_base/demo_solution_scope.v1.json").selected_solution_ids)

    assert all(set(document.solution_ids).issubset(selected) for document in documents)


def test_each_selected_solution_has_one_solution_doc_and_two_non_solution_refs() -> None:
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")
    scope = load_demo_solution_scope("data/knowledge_base/demo_solution_scope.v1.json")

    for solution_id in scope.selected_solution_ids:
        solution_docs = [
            document.document_id
            for document in documents
            if document.document_type is KnowledgeDocumentType.solution and solution_id in document.solution_ids
        ]
        non_solution_docs = [
            document.document_id
            for document in documents
            if document.document_type is not KnowledgeDocumentType.solution and solution_id in document.solution_ids
        ]
        assert len(solution_docs) == 1
        assert len(non_solution_docs) >= 2


def test_source_uri_values_are_safe() -> None:
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")

    for document in documents:
        assert not document.source_uri.startswith("http")
        assert not document.source_uri.startswith("/Users/")
        assert "data/runtime" not in document.source_uri


def test_manifest_matches_real_dataset() -> None:
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")
    chunks = build_knowledge_chunks(documents)
    manifest = load_knowledge_manifest("data/knowledge_base/manifest.v1.json")

    assert manifest.document_count == len(documents)
    assert manifest.chunk_count == len(chunks)
    assert manifest.synthetic_data is True
    assert manifest.source_mode.value == "local_static"


def test_validate_knowledge_base_dataset_passes_for_tracked_files() -> None:
    scope = load_demo_solution_scope("data/knowledge_base/demo_solution_scope.v1.json")
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")
    chunks = build_knowledge_chunks(documents)
    manifest = load_knowledge_manifest("data/knowledge_base/manifest.v1.json")

    validate_knowledge_base_dataset(
        documents=documents,
        chunks=chunks,
        manifest=manifest,
        demo_scope=scope,
        allowed_solution_ids=_allowed_solution_ids(),
    )


def test_validate_knowledge_base_dataset_rejects_excluded_solution_reference() -> None:
    scope = load_demo_solution_scope("data/knowledge_base/demo_solution_scope.v1.json")
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")
    chunks = build_knowledge_chunks(documents)
    manifest = load_knowledge_manifest("data/knowledge_base/manifest.v1.json")

    mutated_documents = [document.model_copy(deep=True) for document in documents]
    mutated_documents[0].solution_ids = ["AI商品导购方案"]

    with pytest.raises(ValueError, match="outside the demo scope"):
        validate_knowledge_base_dataset(
            documents=mutated_documents,
            chunks=chunks,
            manifest=manifest,
            demo_scope=scope,
            allowed_solution_ids=_allowed_solution_ids(),
        )


def test_manifest_solution_ids_match_selected_scope() -> None:
    scope = load_demo_solution_scope("data/knowledge_base/demo_solution_scope.v1.json")
    manifest = load_knowledge_manifest("data/knowledge_base/manifest.v1.json")

    assert set(manifest.solution_ids) == set(scope.selected_solution_ids)
