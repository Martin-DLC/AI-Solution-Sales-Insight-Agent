from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge_base.dataset import load_knowledge_chunks, load_knowledge_documents
from knowledge_base.retrieval.lexical import LexicalBaselineConfig, WeightedBM25Retriever


def retriever() -> WeightedBM25Retriever:
    config = LexicalBaselineConfig.model_validate(
        json.loads(
            Path("data/evaluation/retrieval/lexical_baseline_config.v1.json").read_text(encoding="utf-8")
        )
    )
    instance = WeightedBM25Retriever(config=config)
    instance.build_index(
        documents=load_knowledge_documents("data/knowledge_base/documents.v1.jsonl"),
        chunks=load_knowledge_chunks("data/knowledge_base/chunks.v1.jsonl"),
    )
    return instance


def test_retriever_returns_ranked_candidates_for_real_query() -> None:
    candidates = retriever().retrieve(
        query="需要制度问答、出处引用和人工复核",
        filters={"industries": ["enterprise_shared_services"], "document_types": ["solution", "security_compliance"]},
        top_k=5,
    )

    assert candidates
    assert candidates[0].rank == 1
    assert candidates == sorted(candidates, key=lambda item: (-item.score, item.document_id, item.chunk_id or ""))


def test_retriever_filters_out_non_approved_documents_by_default() -> None:
    candidates = retriever().retrieve(
        query="私有化部署 运维 节奏",
        filters={"document_types": ["solution"]},
        top_k=5,
    )

    assert all(candidate.metadata["status"] == "approved" for candidate in candidates)


def test_retriever_rejects_unknown_filter_key() -> None:
    with pytest.raises(ValueError, match="Unsupported retrieval filter keys"):
        retriever().retrieve(query="客服", filters={"unknown": ["x"]}, top_k=5)


def test_retriever_returns_empty_when_filters_exclude_all_candidates() -> None:
    instance = retriever()
    candidates = instance.retrieve(
        query="客服 辅助 回复",
        filters={"industries": ["non-existent-industry"]},
        top_k=5,
    )

    assert candidates == []
    assert instance.last_retrieval_debug["filtered_candidate_count"] == 0
