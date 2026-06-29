from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge_base.dataset import load_knowledge_chunks, load_knowledge_documents, load_knowledge_manifest
from knowledge_base.retrieval import FakeEmbeddingProvider
from knowledge_base.retrieval.vector import ExactVectorRetriever, VectorBaselineConfig


def _config(tmp_path: Path) -> VectorBaselineConfig:
    payload = json.loads(Path("data/evaluation/retrieval/vector_baseline_config.v1.json").read_text(encoding="utf-8"))
    payload["cache_directory"] = "data/runtime/test-vector-cache"
    return VectorBaselineConfig.model_validate(payload)


def _documents():
    return load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")


def _chunks():
    return load_knowledge_chunks("data/knowledge_base/chunks.v1.jsonl")


def _manifest():
    return load_knowledge_manifest("data/knowledge_base/manifest.v1.json")


def test_vector_retriever_encodes_corpus_once(tmp_path: Path) -> None:
    provider = FakeEmbeddingProvider()
    retriever = ExactVectorRetriever(config=_config(tmp_path), embedding_provider=provider, project_root=tmp_path)

    retriever.build_index(documents=_documents(), chunks=_chunks(), knowledge_base_version=_manifest().knowledge_base_version)

    assert provider.document_calls == 1


def test_vector_config_preserves_required_query_and_document_prefixes(tmp_path: Path) -> None:
    config = _config(tmp_path)

    assert config.query_prefix == "query: "
    assert config.document_prefix == "passage: "


def test_vector_retriever_encodes_query_per_request(tmp_path: Path) -> None:
    provider = FakeEmbeddingProvider()
    retriever = ExactVectorRetriever(config=_config(tmp_path), embedding_provider=provider, project_root=tmp_path)
    retriever.build_index(documents=_documents(), chunks=_chunks(), knowledge_base_version=_manifest().knowledge_base_version)

    retriever.retrieve(query="客服 回复", filters={"document_types": ["solution"]}, top_k=5)
    retriever.retrieve(query="工单 集成", filters={"document_types": ["solution"]}, top_k=5)

    assert provider.query_calls == 2


def test_vector_retriever_returns_stable_scores_and_order(tmp_path: Path) -> None:
    retriever = ExactVectorRetriever(config=_config(tmp_path), embedding_provider=FakeEmbeddingProvider(), project_root=tmp_path)
    retriever.build_index(documents=_documents(), chunks=_chunks(), knowledge_base_version=_manifest().knowledge_base_version)

    candidates = retriever.retrieve(query="客服 回复 知识库", filters={"document_types": ["solution"]}, top_k=5)

    assert candidates == sorted(candidates, key=lambda item: (-item.score, item.document_id, item.chunk_id or ""))


def test_vector_retriever_applies_same_status_filters_as_lexical(tmp_path: Path) -> None:
    retriever = ExactVectorRetriever(config=_config(tmp_path), embedding_provider=FakeEmbeddingProvider(), project_root=tmp_path)
    retriever.build_index(documents=_documents(), chunks=_chunks(), knowledge_base_version=_manifest().knowledge_base_version)

    candidates = retriever.retrieve(query="私有化 部署", filters={"document_types": ["solution"]}, top_k=5)

    statuses = {chunk.metadata.get("status") for chunk in _chunks() if chunk.document_id in {c.document_id for c in candidates}}
    assert statuses <= {"approved"}


def test_vector_retriever_returns_empty_when_filters_exclude_all(tmp_path: Path) -> None:
    retriever = ExactVectorRetriever(config=_config(tmp_path), embedding_provider=FakeEmbeddingProvider(), project_root=tmp_path)
    retriever.build_index(documents=_documents(), chunks=_chunks(), knowledge_base_version=_manifest().knowledge_base_version)

    candidates = retriever.retrieve(query="客服", filters={"industries": ["non-existent"]}, top_k=5)

    assert candidates == []


def test_vector_retriever_does_not_store_embedding_in_candidate_metadata(tmp_path: Path) -> None:
    retriever = ExactVectorRetriever(config=_config(tmp_path), embedding_provider=FakeEmbeddingProvider(), project_root=tmp_path)
    retriever.build_index(documents=_documents(), chunks=_chunks(), knowledge_base_version=_manifest().knowledge_base_version)

    candidate = retriever.retrieve(query="客服", filters={"document_types": ["solution"]}, top_k=1)[0]

    assert "embedding" not in candidate.metadata
    assert "vector" not in candidate.metadata


def test_vector_retriever_rejects_unknown_filter_key(tmp_path: Path) -> None:
    retriever = ExactVectorRetriever(config=_config(tmp_path), embedding_provider=FakeEmbeddingProvider(), project_root=tmp_path)
    retriever.build_index(documents=_documents(), chunks=_chunks(), knowledge_base_version=_manifest().knowledge_base_version)

    with pytest.raises(ValueError, match="Unsupported retrieval filter keys"):
        retriever.retrieve(query="客服", filters={"unknown": ["x"]}, top_k=5)


def test_vector_retriever_cache_key_is_stable(tmp_path: Path) -> None:
    provider = FakeEmbeddingProvider()
    config = _config(tmp_path)
    retriever = ExactVectorRetriever(config=config, embedding_provider=provider, project_root=tmp_path)
    chunk = _chunks()[0]

    first = retriever._cache_path(knowledge_base_version="kb-demo-v1", chunk=chunk)  # noqa: SLF001
    second = retriever._cache_path(knowledge_base_version="kb-demo-v1", chunk=chunk)  # noqa: SLF001

    assert first == second


def test_vector_retriever_detects_cache_dimension_mismatch(tmp_path: Path) -> None:
    provider = FakeEmbeddingProvider(dimension=8)
    config = _config(tmp_path)
    retriever = ExactVectorRetriever(config=config, embedding_provider=provider, project_root=tmp_path)
    chunk = _chunks()[0]
    path = retriever._cache_path(knowledge_base_version="kb-demo-v1", chunk=chunk)  # noqa: SLF001
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"dimension": 99, "vector": [0.1] * 99}), encoding="utf-8")

    with pytest.raises(ValueError, match="dimension mismatch"):
        retriever.build_index(documents=_documents(), chunks=_chunks(), knowledge_base_version="kb-demo-v1")


def test_vector_retriever_does_not_modify_input_chunks(tmp_path: Path) -> None:
    chunks = _chunks()
    snapshot = [chunk.model_dump(mode="json") for chunk in chunks]
    retriever = ExactVectorRetriever(config=_config(tmp_path), embedding_provider=FakeEmbeddingProvider(), project_root=tmp_path)

    retriever.build_index(documents=_documents(), chunks=chunks, knowledge_base_version=_manifest().knowledge_base_version)

    assert [chunk.model_dump(mode="json") for chunk in chunks] == snapshot
