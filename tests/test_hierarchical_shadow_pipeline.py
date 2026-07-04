from __future__ import annotations

from evaluation.retrieval.contracts_v2 import RetrievalRuntimeContextV2
from evaluation.retrieval.models import RetrievalCandidate, RetrievalMethod
from knowledge_base.contracts_v2 import KnowledgeChunkV2, KnowledgeDocumentV2, load_demo_solution_ids_v2
from knowledge_base.retrieval.embeddings import FakeEmbeddingProvider
from knowledge_base.retrieval.hierarchical import HierarchicalRetrievalMode, resolve_hierarchical_mode
from knowledge_base.retrieval.shadow import HierarchicalShadowConfig, ShadowHierarchicalRetrievalService


class FakeRetriever:
    def __init__(self, candidates: list[RetrievalCandidate], *, fail: bool = False) -> None:
        self._candidates = candidates
        self._fail = fail
        self.calls = 0

    def retrieve(self, *, query: str, filters: dict[str, object], top_k: int) -> list[RetrievalCandidate]:
        self.calls += 1
        if self._fail:
            raise RuntimeError("shadow failed")
        return list(self._candidates[:top_k])


def _solution_ids() -> tuple[str, str]:
    ids = load_demo_solution_ids_v2()
    return ids[0], ids[1]


def _document(document_id: str, *, applicable: list[str]) -> KnowledgeDocumentV2:
    return KnowledgeDocumentV2(
        document_id=document_id,
        title=f"title-{document_id}",
        document_type="solution",
        status="approved",
        summary="这是一个足够长的摘要文本。",
        content="这是一个足够长的正文内容，用于 shadow 集成测试。",
        tags=["priority"],
        industries=["retail"],
        source_uri=f"synthetic://{document_id}",
        primary_solution_id=applicable[0],
        applicable_solution_ids=applicable,
        excluded_solution_ids=[],
        scope_type="solution_specific",
        scope_notes="test",
    )


def _chunk(chunk_id: str, document_id: str, *, applicable: list[str]) -> KnowledgeChunkV2:
    return KnowledgeChunkV2(
        chunk_id=chunk_id,
        document_id=document_id,
        document_type="solution",
        chunk_index=0,
        content=f"这是 {chunk_id} 的正文内容，长度足够稳定。",
        token_estimate=16,
        tags=["priority"],
        industries=["retail"],
        metadata={"section_title": "Overview"},
        citation_label=f"{document_id} - Overview",
        primary_solution_id=applicable[0],
        applicable_solution_ids=applicable,
        excluded_solution_ids=[],
        scope_type="solution_specific",
        scope_notes="test",
    )


def _candidate(document_id: str, chunk_id: str | None, score: float, rank: int, solution_id: str) -> RetrievalCandidate:
    return RetrievalCandidate(
        rank=rank,
        document_id=document_id,
        chunk_id=chunk_id,
        score=score,
        retrieval_method=RetrievalMethod.vector_v1,
        matched_terms=[],
        metadata={},
        citation_label=f"{document_id} - Overview",
        solution_ids=[solution_id],
    )


def test_shadow_mode_preserves_formal_output_and_records_shadow_metrics() -> None:
    solution_a, _solution_b = _solution_ids()
    documents = [_document("DOC-001", applicable=[solution_a])]
    chunks = [_chunk("DOC-001#chunk-1", "DOC-001", applicable=[solution_a])]
    formal_candidates = [_candidate("DOC-001", "DOC-001#chunk-1", 0.7, 1, solution_a)]
    shadow_candidates = [_candidate("DOC-001", "DOC-001#chunk-1", 0.9, 1, solution_a)]
    service = ShadowHierarchicalRetrievalService(
        formal_retriever=FakeRetriever(formal_candidates),
        shadow_chunk_ranker=FakeRetriever(shadow_candidates),
        embedding_provider=FakeEmbeddingProvider(),
        documents=documents,
        chunks=chunks,
        config=HierarchicalShadowConfig(mode=HierarchicalRetrievalMode.shadow),
    )
    runtime_context = RetrievalRuntimeContextV2(
        operational_solution_scope=[solution_a],
        allowed_document_types=["solution"],
        industries=["retail"],
        tags=["priority"],
    )

    result = service.retrieve(
        query="合规 检索",
        filters={"solution_ids": [solution_a], "document_types": ["solution"]},
        runtime_context=runtime_context,
        request_id="req-001",
    )

    assert result == formal_candidates
    assert service.last_shadow_result is not None
    assert service.last_shadow_result.request_id == "req-001"
    assert service.last_shadow_result.hierarchical_mode is HierarchicalRetrievalMode.shadow
    assert service.last_shadow_result.candidate_count >= 2
    assert service.last_shadow_result.runtime_eligible_count >= 1
    assert service.last_shadow_result.shadow_error is None
    assert service.last_shadow_result.context_document_blocks == 1
    assert service.last_shadow_result.context_chunk_blocks == 1


def test_off_mode_skips_shadow_pipeline_entirely() -> None:
    solution_a, _solution_b = _solution_ids()
    documents = [_document("DOC-001", applicable=[solution_a])]
    chunks = [_chunk("DOC-001#chunk-1", "DOC-001", applicable=[solution_a])]
    formal = FakeRetriever([_candidate("DOC-001", "DOC-001#chunk-1", 0.7, 1, solution_a)])
    shadow = FakeRetriever([_candidate("DOC-001", "DOC-001#chunk-1", 0.9, 1, solution_a)])
    service = ShadowHierarchicalRetrievalService(
        formal_retriever=formal,
        shadow_chunk_ranker=shadow,
        embedding_provider=FakeEmbeddingProvider(),
        documents=documents,
        chunks=chunks,
        config=HierarchicalShadowConfig(mode=HierarchicalRetrievalMode.off),
    )

    result = service.retrieve(
        query="合规 检索",
        filters={"solution_ids": [solution_a]},
        runtime_context=RetrievalRuntimeContextV2(operational_solution_scope=[solution_a]),
    )

    assert result[0].document_id == "DOC-001"
    assert formal.calls == 1
    assert shadow.calls == 0
    assert service.last_shadow_result is None


def test_shadow_errors_are_captured_without_affecting_formal_output() -> None:
    solution_a, _solution_b = _solution_ids()
    documents = [_document("DOC-001", applicable=[solution_a])]
    chunks = [_chunk("DOC-001#chunk-1", "DOC-001", applicable=[solution_a])]
    formal_candidates = [_candidate("DOC-001", "DOC-001#chunk-1", 0.7, 1, solution_a)]
    service = ShadowHierarchicalRetrievalService(
        formal_retriever=FakeRetriever(formal_candidates),
        shadow_chunk_ranker=FakeRetriever([], fail=True),
        embedding_provider=FakeEmbeddingProvider(),
        documents=documents,
        chunks=chunks,
        config=HierarchicalShadowConfig(mode=HierarchicalRetrievalMode.shadow),
    )

    result = service.retrieve(
        query="合规 检索",
        filters={"solution_ids": [solution_a]},
        runtime_context=RetrievalRuntimeContextV2(operational_solution_scope=[solution_a]),
    )

    assert result == formal_candidates
    assert service.last_shadow_result is not None
    assert service.last_shadow_result.shadow_error == "RuntimeError: shadow failed"
    assert service.last_shadow_result.fallback_recommended is True
    assert service.last_shadow_result.fallback_reasons == ["shadow_pipeline_error"]


def test_invalid_mode_resolves_to_off() -> None:
    assert resolve_hierarchical_mode("active") is HierarchicalRetrievalMode.off
    assert resolve_hierarchical_mode("shadow") is HierarchicalRetrievalMode.shadow
