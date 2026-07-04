from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

from evaluation.retrieval.contracts_v2 import RetrievalRuntimeContextV2
from evaluation.retrieval.models import RetrievalCandidate
from knowledge_base.contracts_v2 import KnowledgeChunkV2, KnowledgeDocumentV2
from knowledge_base.retrieval.embeddings import EmbeddingProvider
from knowledge_base.retrieval.hierarchical import (
    HierarchicalCandidate,
    HierarchicalCandidateGenerator,
    HierarchicalCorpus,
    HierarchicalRetrievalMode,
    HierarchicalShadowResult,
    assess_completeness,
    build_citation_preview,
    build_context_materialization_preview,
    build_query_hash,
    evaluate_runtime_eligibility,
    resolve_hierarchical_mode,
    summarize_rejection_reasons,
)


class RetrievalClient(Protocol):
    def retrieve(
        self,
        *,
        query: str,
        filters: dict[str, object],
        top_k: int,
    ) -> list[RetrievalCandidate]:
        ...


@dataclass(frozen=True)
class HierarchicalShadowConfig:
    mode: HierarchicalRetrievalMode = HierarchicalRetrievalMode.off
    formal_top_k: int = 5
    shadow_candidate_k: int = 20

    @classmethod
    def from_env(cls) -> "HierarchicalShadowConfig":
        return cls(mode=resolve_hierarchical_mode(os.getenv("HIERARCHICAL_RETRIEVAL_MODE")))

    def __post_init__(self) -> None:
        normalized = self.mode
        if isinstance(normalized, str):
            normalized = resolve_hierarchical_mode(normalized)
        object.__setattr__(self, "mode", normalized)


class ShadowHierarchicalRetrievalService:
    def __init__(
        self,
        *,
        formal_retriever: RetrievalClient,
        shadow_chunk_ranker: RetrievalClient,
        embedding_provider: EmbeddingProvider,
        documents: list[KnowledgeDocumentV2],
        chunks: list[KnowledgeChunkV2],
        config: HierarchicalShadowConfig | None = None,
    ) -> None:
        self._formal_retriever = formal_retriever
        self._shadow_chunk_ranker = shadow_chunk_ranker
        self._embedding_provider = embedding_provider
        self._config = config or HierarchicalShadowConfig.from_env()
        self._corpus = HierarchicalCorpus.from_records(documents=documents, chunks=chunks)
        self.last_shadow_result: HierarchicalShadowResult | None = None

    @property
    def mode(self) -> HierarchicalRetrievalMode:
        return self._config.mode

    def retrieve(
        self,
        *,
        query: str,
        filters: dict[str, object],
        runtime_context: RetrievalRuntimeContextV2,
        request_id: str | None = None,
    ) -> list[RetrievalCandidate]:
        formal_result = self._formal_retriever.retrieve(
            query=query,
            filters=filters,
            top_k=self._config.formal_top_k,
        )
        if self._config.mode != HierarchicalRetrievalMode.shadow:
            self.last_shadow_result = None
            return formal_result

        started = time.perf_counter()
        query_hash = build_query_hash(query)
        resolved_request_id = request_id or f"shadow:{query_hash}"
        try:
            baseline_candidates = self._shadow_chunk_ranker.retrieve(
                query=query,
                filters=filters,
                top_k=self._config.shadow_candidate_k,
            )
            generator = HierarchicalCandidateGenerator(
                embedding_provider=self._embedding_provider,
                corpus=self._corpus,
                candidate_limit=self._config.shadow_candidate_k,
            )
            candidates = generator.generate(query=query, baseline_chunk_candidates=baseline_candidates)
            evaluated_candidates = self._apply_runtime_eligibility(candidates=candidates, runtime_context=runtime_context)
            context_preview = build_context_materialization_preview(candidates=evaluated_candidates, corpus=self._corpus)
            citation_preview = build_citation_preview(candidates=evaluated_candidates, corpus=self._corpus)
            completeness = assess_completeness(
                candidates=evaluated_candidates,
                context_preview=context_preview,
                citation_preview=citation_preview,
            )
            elapsed_ms = max(0, int((time.perf_counter() - started) * 1000))
            self.last_shadow_result = HierarchicalShadowResult(
                hierarchical_mode=self._config.mode,
                request_id=resolved_request_id,
                query_hash=query_hash,
                candidate_count=len(evaluated_candidates),
                document_candidate_count=sum(1 for item in evaluated_candidates if item.candidate_type.value == "document"),
                chunk_candidate_count=sum(1 for item in evaluated_candidates if item.candidate_type.value == "chunk"),
                runtime_eligible_count=sum(1 for item in evaluated_candidates if item.runtime_eligible is True),
                runtime_rejected_count=sum(1 for item in evaluated_candidates if item.runtime_eligible is False),
                rejection_reason_counts=summarize_rejection_reasons(evaluated_candidates),
                context_document_blocks=context_preview.document_block_count,
                context_chunk_blocks=context_preview.chunk_block_count,
                duplicate_blocks_removed=context_preview.duplicate_blocks_removed,
                evidence_complete=completeness.evidence_complete,
                fallback_recommended=completeness.fallback_recommended,
                fallback_reasons=list(completeness.fallback_reasons),
                elapsed_ms=elapsed_ms,
                candidates=evaluated_candidates,
                context_preview=context_preview,
                citation_preview=citation_preview,
                completeness_assessment=completeness,
            )
        except Exception as exc:
            elapsed_ms = max(0, int((time.perf_counter() - started) * 1000))
            self.last_shadow_result = HierarchicalShadowResult(
                hierarchical_mode=self._config.mode,
                request_id=resolved_request_id,
                query_hash=query_hash,
                candidate_count=0,
                document_candidate_count=0,
                chunk_candidate_count=0,
                runtime_eligible_count=0,
                runtime_rejected_count=0,
                rejection_reason_counts={},
                context_document_blocks=0,
                context_chunk_blocks=0,
                duplicate_blocks_removed=0,
                evidence_complete=False,
                fallback_recommended=True,
                fallback_reasons=["shadow_pipeline_error"],
                elapsed_ms=elapsed_ms,
                shadow_error=f"{exc.__class__.__name__}: {exc}",
                candidates=[],
                context_preview=build_context_materialization_preview(candidates=[], corpus=self._corpus),
                citation_preview=build_citation_preview(candidates=[], corpus=self._corpus),
                completeness_assessment=assess_completeness(
                    candidates=[],
                    context_preview=build_context_materialization_preview(candidates=[], corpus=self._corpus),
                    citation_preview=build_citation_preview(candidates=[], corpus=self._corpus),
                ),
            )
        return formal_result

    def _apply_runtime_eligibility(
        self,
        *,
        candidates: list[HierarchicalCandidate],
        runtime_context: RetrievalRuntimeContextV2,
    ) -> list[HierarchicalCandidate]:
        evaluated: list[HierarchicalCandidate] = []
        for candidate in candidates:
            document = self._corpus.documents_by_id[candidate.document_id]
            chunk = self._corpus.chunks_by_id.get(candidate.chunk_id) if candidate.chunk_id is not None else None
            eligibility = evaluate_runtime_eligibility(
                candidate=candidate,
                runtime_context=runtime_context,
                document=document,
                chunk=chunk,
            )
            evaluated.append(
                candidate.model_copy(
                    update={
                        "runtime_eligible": eligibility.runtime_eligible,
                        "rejection_reasons": list(eligibility.rejection_reasons),
                    }
                )
            )
        return evaluated
