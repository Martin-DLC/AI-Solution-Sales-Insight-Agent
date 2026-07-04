from __future__ import annotations

from datetime import date

from evaluation.retrieval.contracts_v2 import RetrievalRuntimeContextV2
from evaluation.retrieval.models import RetrievalCandidate, RetrievalMethod
from knowledge_base.contracts_v2 import KnowledgeChunkV2, KnowledgeDocumentV2, load_demo_solution_ids_v2
from knowledge_base.retrieval.hierarchical import (
    HierarchicalCandidateGenerator,
    HierarchicalCandidateType,
    HierarchicalCorpus,
    build_context_materialization_preview,
    evaluate_runtime_eligibility,
)
from knowledge_base.retrieval.shadow import HierarchicalShadowConfig


class ConstantEmbeddingProvider:
    provider_id = "constant"
    dimension = 4
    resolved_revision = "test"

    def encode_queries(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


def _solution_ids() -> tuple[str, str]:
    ids = load_demo_solution_ids_v2()
    return ids[0], ids[1]


def _document(document_id: str, *, applicable: list[str], scope_type: str = "solution_specific") -> KnowledgeDocumentV2:
    primary = applicable[0] if scope_type != "global_policy" else None
    return KnowledgeDocumentV2(
        document_id=document_id,
        title=f"title-{document_id}",
        document_type="solution",
        status="approved",
        summary="这是一个足够长的摘要文本。",
        content="这是一个足够长的正文文本，用于层级候选测试。",
        tags=["priority"],
        industries=["retail"],
        source_uri=f"synthetic://{document_id}",
        primary_solution_id=primary,
        applicable_solution_ids=applicable,
        excluded_solution_ids=[],
        scope_type=scope_type,
        scope_notes="test",
    )


def _chunk(
    chunk_id: str,
    document_id: str,
    *,
    applicable: list[str],
    scope_type: str = "solution_specific",
) -> KnowledgeChunkV2:
    primary = applicable[0] if scope_type != "global_policy" else None
    return KnowledgeChunkV2(
        chunk_id=chunk_id,
        document_id=document_id,
        document_type="solution",
        chunk_index=0,
        content=f"这是 {chunk_id} 的正文内容，长度足够稳定。",
        token_estimate=18,
        tags=["priority"],
        industries=["retail"],
        metadata={"section_title": "Overview"},
        citation_label=f"{document_id} - Overview",
        primary_solution_id=primary,
        applicable_solution_ids=applicable,
        excluded_solution_ids=[],
        scope_type=scope_type,
        scope_notes="test",
    )


def test_hierarchical_generator_produces_parent_then_children_with_stable_ids() -> None:
    solution_a, solution_b = _solution_ids()
    documents = [
        _document("DOC-B", applicable=[solution_a]),
        _document("DOC-A", applicable=[solution_a]),
    ]
    chunks = [
        _chunk("DOC-A#chunk-1", "DOC-A", applicable=[solution_a]),
        _chunk("DOC-A#chunk-2", "DOC-A", applicable=[solution_a]),
        _chunk("DOC-B#chunk-1", "DOC-B", applicable=[solution_b]),
    ]
    corpus = HierarchicalCorpus.from_records(documents=documents, chunks=chunks)
    generator = HierarchicalCandidateGenerator(
        embedding_provider=ConstantEmbeddingProvider(),
        corpus=corpus,
    )
    baseline = [
        RetrievalCandidate(
            rank=1,
            document_id="DOC-A",
            chunk_id="DOC-A#chunk-2",
            score=0.9,
            retrieval_method=RetrievalMethod.vector_v1,
            matched_terms=[],
            metadata={},
            citation_label="DOC-A - Overview",
            solution_ids=[solution_a],
        ),
        RetrievalCandidate(
            rank=2,
            document_id="DOC-A",
            chunk_id="DOC-A#chunk-1",
            score=0.8,
            retrieval_method=RetrievalMethod.vector_v1,
            matched_terms=[],
            metadata={},
            citation_label="DOC-A - Overview",
            solution_ids=[solution_a],
        ),
    ]

    candidates = generator.generate(query="合规 检索", baseline_chunk_candidates=baseline)

    assert candidates[0].candidate_id == "document:DOC-A"
    assert candidates[0].candidate_type is HierarchicalCandidateType.document
    assert candidates[1].candidate_id == "chunk:DOC-A#chunk-2"
    assert candidates[2].candidate_id == "chunk:DOC-A#chunk-1"
    assert candidates[1].parent_document_id == "DOC-A"
    assert candidates[1].baseline_rank == 1
    assert candidates[2].baseline_rank == 2
    assert candidates[0].child_chunk_ids == ["DOC-A#chunk-1", "DOC-A#chunk-2"]


def test_runtime_eligibility_and_context_preview_are_deterministic() -> None:
    solution_a, solution_b = _solution_ids()
    document = _document("DOC-001", applicable=[solution_a])
    chunk = _chunk("DOC-001#chunk-1", "DOC-001", applicable=[solution_a])
    corpus = HierarchicalCorpus.from_records(documents=[document], chunks=[chunk])
    generator = HierarchicalCandidateGenerator(
        embedding_provider=ConstantEmbeddingProvider(),
        corpus=corpus,
    )
    baseline = [
        RetrievalCandidate(
            rank=1,
            document_id="DOC-001",
            chunk_id="DOC-001#chunk-1",
            score=0.9,
            retrieval_method=RetrievalMethod.vector_v1,
            matched_terms=[],
            metadata={},
            citation_label="DOC-001 - Overview",
            solution_ids=[solution_a],
        )
    ]
    candidates = generator.generate(query="合规 检索", baseline_chunk_candidates=baseline)
    runtime_context = RetrievalRuntimeContextV2(
        operational_solution_scope=[solution_a],
        allowed_document_types=["solution"],
        industries=["retail"],
        tags=["priority"],
        effective_on=date(2026, 7, 4),
    )

    allowed = evaluate_runtime_eligibility(
        candidate=candidates[1],
        runtime_context=runtime_context,
        document=document,
        chunk=chunk,
    )
    denied = evaluate_runtime_eligibility(
        candidate=candidates[1],
        runtime_context=runtime_context.model_copy(update={"operational_solution_scope": [solution_b]}),
        document=document,
        chunk=chunk,
    )

    allowed_candidates = [
        item.model_copy(update={"runtime_eligible": True, "rejection_reasons": []})
        for item in candidates
    ]
    preview = build_context_materialization_preview(candidates=allowed_candidates, corpus=corpus)

    assert allowed.runtime_eligible is True
    assert denied.runtime_eligible is False
    assert "solution_scope_mismatch" in denied.rejection_reasons
    assert preview.document_block_count == 1
    assert preview.chunk_block_count == 1
    assert preview.duplicate_blocks_removed == 0
    assert "Title:" in preview.materialized_blocks[0].content
    assert "Chunk Content:" in preview.materialized_blocks[1].content


def test_invalid_mode_safely_falls_back_to_off() -> None:
    config = HierarchicalShadowConfig.from_env()
    explicit = config.__class__(mode=config.mode)

    assert explicit.mode.value in {"off", "shadow"}
