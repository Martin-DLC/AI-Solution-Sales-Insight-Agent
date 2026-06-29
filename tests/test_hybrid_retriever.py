from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge_base.dataset import load_knowledge_chunks, load_knowledge_documents, load_knowledge_manifest
from knowledge_base.retrieval import FakeEmbeddingProvider, LexicalBaselineConfig, WeightedBM25Retriever
from knowledge_base.retrieval.hybrid import HybridBaselineConfig, ReciprocalRankFusionRetriever
from knowledge_base.retrieval.vector import ExactVectorRetriever, VectorBaselineConfig


def _lexical_config() -> LexicalBaselineConfig:
    return LexicalBaselineConfig.model_validate(
        json.loads(Path("data/evaluation/retrieval/lexical_baseline_config.v1.json").read_text(encoding="utf-8"))
    )


def _vector_config(tmp_path: Path) -> VectorBaselineConfig:
    payload = json.loads(Path("data/evaluation/retrieval/vector_baseline_config.v1.json").read_text(encoding="utf-8"))
    payload["cache_directory"] = "data/runtime/test-hybrid-cache"
    payload["cache_enabled"] = False
    return VectorBaselineConfig.model_validate(payload)


def _hybrid_config() -> HybridBaselineConfig:
    return HybridBaselineConfig.model_validate(
        json.loads(Path("data/evaluation/retrieval/hybrid_baseline_config.v1.json").read_text(encoding="utf-8"))
    )


def _hybrid(tmp_path: Path) -> ReciprocalRankFusionRetriever:
    lexical = WeightedBM25Retriever(config=_lexical_config())
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")
    chunks = load_knowledge_chunks("data/knowledge_base/chunks.v1.jsonl")
    lexical.build_index(documents=documents, chunks=chunks)

    vector = ExactVectorRetriever(
        config=_vector_config(tmp_path),
        embedding_provider=FakeEmbeddingProvider(),
        project_root=tmp_path,
    )
    vector.build_index(
        documents=documents,
        chunks=chunks,
        knowledge_base_version=load_knowledge_manifest("data/knowledge_base/manifest.v1.json").knowledge_base_version,
    )
    return ReciprocalRankFusionRetriever(config=_hybrid_config(), lexical_retriever=lexical, vector_retriever=vector)


def test_hybrid_retriever_returns_ranked_candidates(tmp_path: Path) -> None:
    candidates = _hybrid(tmp_path).retrieve(
        query="客服 回复 知识库",
        filters={"document_types": ["solution"]},
        top_k=5,
    )

    assert candidates
    assert candidates == sorted(candidates, key=lambda item: (-item.score, item.document_id, item.chunk_id or ""))


def test_hybrid_metadata_contains_dual_rank_information(tmp_path: Path) -> None:
    candidate = _hybrid(tmp_path).retrieve(
        query="客服 回复",
        filters={"document_types": ["solution"]},
        top_k=1,
    )[0]

    assert "lexical_rank" in candidate.metadata
    assert "vector_rank" in candidate.metadata
    assert "rrf_score" in candidate.metadata


def test_hybrid_supports_single_sided_hits(tmp_path: Path, monkeypatch) -> None:
    hybrid = _hybrid(tmp_path)

    monkeypatch.setattr(
        hybrid._lexical_retriever,  # noqa: SLF001
        "retrieve",
        lambda **kwargs: [],
    )

    candidates = hybrid.retrieve(query="客服", filters={"document_types": ["solution"]}, top_k=5)

    assert candidates


def test_hybrid_propagates_retriever_errors(tmp_path: Path, monkeypatch) -> None:
    hybrid = _hybrid(tmp_path)

    def boom(**kwargs):
        raise ValueError("vector failed")

    monkeypatch.setattr(hybrid._vector_retriever, "retrieve", boom)  # noqa: SLF001

    with pytest.raises(ValueError, match="vector failed"):
        hybrid.retrieve(query="客服", filters={"document_types": ["solution"]}, top_k=5)
