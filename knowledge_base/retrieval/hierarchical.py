from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any

from pydantic import Field, field_validator, model_validator

from evaluation.retrieval.contracts_v2 import RetrievalRuntimeContextV2
from evaluation.retrieval.models import RetrievalCandidate
from knowledge_base.contracts_v2 import KnowledgeChunkV2, KnowledgeDocumentV2
from knowledge_base.retrieval.embeddings import EmbeddingProvider
from schemas.common_models import StrictBaseModel


HIERARCHICAL_CANDIDATE_LIMIT = 20
HIERARCHICAL_RRF_K = 60


class HierarchicalRetrievalMode(str, Enum):
    off = "off"
    shadow = "shadow"


class HierarchicalCandidateType(str, Enum):
    document = "document"
    chunk = "chunk"


class HierarchicalCandidate(StrictBaseModel):
    candidate_id: str
    candidate_type: HierarchicalCandidateType
    document_id: str
    chunk_id: str | None = None
    parent_document_id: str | None = None
    title: str
    content: str
    citation_label: str
    semantic_score: float | None = None
    baseline_rank: int | None = None
    document_rank: int | None = None
    expansion_rank: int | None = None
    final_rank: int | None = None
    runtime_eligible: bool | None = None
    rejection_reasons: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    child_chunk_ids: list[str] = Field(default_factory=list)

    @field_validator("rejection_reasons", "child_chunk_ids")
    @classmethod
    def deduplicate_lists(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value and value not in seen:
                seen.add(value)
                result.append(value)
        return result

    @model_validator(mode="after")
    def validate_candidate(self) -> "HierarchicalCandidate":
        if self.candidate_type is HierarchicalCandidateType.document:
            if self.chunk_id is not None:
                raise ValueError("Document candidates must not include chunk_id.")
            if self.parent_document_id is not None:
                raise ValueError("Document candidates must not include parent_document_id.")
            if not self.candidate_id.startswith("document:"):
                raise ValueError("Document candidate_id must start with document:.")
        else:
            if self.chunk_id is None:
                raise ValueError("Chunk candidates must include chunk_id.")
            if self.parent_document_id != self.document_id:
                raise ValueError("Chunk candidates must set parent_document_id to their document_id.")
            if not self.candidate_id.startswith("chunk:"):
                raise ValueError("Chunk candidate_id must start with chunk:.")
        return self


class RuntimeEligibilityResult(StrictBaseModel):
    runtime_eligible: bool
    rejection_reasons: list[str] = Field(default_factory=list)


class MaterializedContextBlock(StrictBaseModel):
    block_id: str
    candidate_id: str
    candidate_type: HierarchicalCandidateType
    document_id: str
    chunk_id: str | None = None
    parent_document_id: str | None = None
    citation_label: str
    title: str
    content: str


class ContextMaterializationPreview(StrictBaseModel):
    materialized_blocks: list[MaterializedContextBlock] = Field(default_factory=list)
    document_block_count: int
    chunk_block_count: int
    estimated_character_count: int
    duplicate_blocks_removed: int
    duplicate_content_risk: bool


class CitationPreviewGroup(StrictBaseModel):
    parent_document: dict[str, Any]
    child_evidence: list[dict[str, Any]] = Field(default_factory=list)


class CitationPreview(StrictBaseModel):
    groups: list[CitationPreviewGroup] = Field(default_factory=list)


class CompletenessAssessment(StrictBaseModel):
    evidence_complete: bool
    fallback_recommended: bool
    fallback_reasons: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)


class HierarchicalShadowResult(StrictBaseModel):
    hierarchical_mode: HierarchicalRetrievalMode
    request_id: str
    query_hash: str
    candidate_count: int
    document_candidate_count: int
    chunk_candidate_count: int
    runtime_eligible_count: int
    runtime_rejected_count: int
    rejection_reason_counts: dict[str, int] = Field(default_factory=dict)
    context_document_blocks: int
    context_chunk_blocks: int
    duplicate_blocks_removed: int
    evidence_complete: bool
    fallback_recommended: bool
    fallback_reasons: list[str] = Field(default_factory=list)
    elapsed_ms: int
    shadow_error: str | None = None
    candidates: list[HierarchicalCandidate] = Field(default_factory=list)
    context_preview: ContextMaterializationPreview
    citation_preview: CitationPreview
    completeness_assessment: CompletenessAssessment


@dataclass(frozen=True)
class HierarchicalCorpus:
    documents_by_id: dict[str, KnowledgeDocumentV2]
    chunks_by_id: dict[str, KnowledgeChunkV2]
    child_chunk_ids_by_document: dict[str, list[str]]

    @classmethod
    def from_records(
        cls,
        *,
        documents: list[KnowledgeDocumentV2],
        chunks: list[KnowledgeChunkV2],
    ) -> "HierarchicalCorpus":
        documents_by_id = {document.document_id: document for document in documents}
        chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        child_chunk_ids_by_document: dict[str, list[str]] = {}
        for chunk in chunks:
            child_chunk_ids_by_document.setdefault(chunk.document_id, []).append(chunk.chunk_id)
        for chunk_ids in child_chunk_ids_by_document.values():
            chunk_ids.sort()
        return cls(
            documents_by_id=documents_by_id,
            chunks_by_id=chunks_by_id,
            child_chunk_ids_by_document=child_chunk_ids_by_document,
        )


class HierarchicalCandidateGenerator:
    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        corpus: HierarchicalCorpus,
        candidate_limit: int = HIERARCHICAL_CANDIDATE_LIMIT,
        rrf_k: int = HIERARCHICAL_RRF_K,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._corpus = corpus
        self._candidate_limit = candidate_limit
        self._rrf_k = rrf_k

    def generate(
        self,
        *,
        query: str,
        baseline_chunk_candidates: list[RetrievalCandidate],
    ) -> list[HierarchicalCandidate]:
        documents = list(self._corpus.documents_by_id.values())
        document_texts = [
            _render_document_context(document=document, child_chunks=self._child_chunks(document.document_id))
            for document in documents
        ]
        document_embeddings = self._embedding_provider.encode_documents(document_texts)
        query_embedding = self._embedding_provider.encode_queries([query])[0]

        baseline_rank_by_chunk_id = {
            candidate.chunk_id: candidate.rank
            for candidate in baseline_chunk_candidates
            if candidate.chunk_id is not None
        }
        baseline_candidate_by_chunk_id = {
            candidate.chunk_id: candidate
            for candidate in baseline_chunk_candidates
            if candidate.chunk_id is not None
        }

        best_child_rank_by_document: dict[str, int] = {}
        for candidate in baseline_chunk_candidates:
            if candidate.chunk_id is None:
                continue
            current = best_child_rank_by_document.get(candidate.document_id)
            if current is None or candidate.rank < current:
                best_child_rank_by_document[candidate.document_id] = candidate.rank

        document_rows: list[dict[str, Any]] = []
        for document, embedding in zip(documents, document_embeddings, strict=True):
            semantic_score = _dot(query_embedding, embedding)
            document_rows.append(
                {
                    "document_id": document.document_id,
                    "semantic_score": semantic_score,
                    "best_child_baseline_rank": best_child_rank_by_document.get(document.document_id),
                }
            )
        document_rows.sort(key=lambda item: (-item["semantic_score"], item["document_id"]))
        for semantic_rank, row in enumerate(document_rows, start=1):
            row["semantic_rank"] = semantic_rank
            row["fusion_score"] = _rrf_score(
                semantic_rank=semantic_rank,
                best_child_baseline_rank=row["best_child_baseline_rank"],
                k=self._rrf_k,
            )
        document_rows.sort(
            key=lambda item: (
                -item["fusion_score"],
                item["semantic_rank"],
                item["best_child_baseline_rank"] if item["best_child_baseline_rank"] is not None else 10_000,
                item["document_id"],
            )
        )

        results: list[HierarchicalCandidate] = []
        seen_candidate_ids: set[str] = set()
        for document_rank, row in enumerate(document_rows, start=1):
            document = self._corpus.documents_by_id[row["document_id"]]
            parent_candidate = HierarchicalCandidate(
                candidate_id=f"document:{document.document_id}",
                candidate_type=HierarchicalCandidateType.document,
                document_id=document.document_id,
                title=document.title,
                content=document.summary,
                citation_label=f"DOC:{document.document_id}",
                semantic_score=row["semantic_score"],
                baseline_rank=row["best_child_baseline_rank"],
                document_rank=document_rank,
                expansion_rank=0,
                final_rank=len(results) + 1,
                provenance={
                    "document_semantic_rank": row["semantic_rank"],
                    "best_child_baseline_rank": row["best_child_baseline_rank"],
                    "fusion_score": row["fusion_score"],
                    "source": "hierarchical_parent",
                },
                child_chunk_ids=list(self._corpus.child_chunk_ids_by_document.get(document.document_id, [])),
            )
            if parent_candidate.candidate_id not in seen_candidate_ids:
                results.append(parent_candidate)
                seen_candidate_ids.add(parent_candidate.candidate_id)
                if len(results) >= self._candidate_limit:
                    break

            child_ids = list(self._corpus.child_chunk_ids_by_document.get(document.document_id, []))
            child_ids.sort(key=lambda chunk_id: (baseline_rank_by_chunk_id.get(chunk_id, 10_000), chunk_id))
            for expansion_rank, chunk_id in enumerate(child_ids, start=1):
                candidate_id = f"chunk:{chunk_id}"
                if candidate_id in seen_candidate_ids:
                    continue
                chunk = self._corpus.chunks_by_id[chunk_id]
                baseline_candidate = baseline_candidate_by_chunk_id.get(chunk_id)
                candidate = HierarchicalCandidate(
                    candidate_id=candidate_id,
                    candidate_type=HierarchicalCandidateType.chunk,
                    document_id=document.document_id,
                    chunk_id=chunk.chunk_id,
                    parent_document_id=document.document_id,
                    title=document.title,
                    content=chunk.content,
                    citation_label=chunk.citation_label,
                    semantic_score=baseline_candidate.score if baseline_candidate is not None else None,
                    baseline_rank=baseline_rank_by_chunk_id.get(chunk_id),
                    document_rank=document_rank,
                    expansion_rank=expansion_rank,
                    final_rank=len(results) + 1,
                    provenance={
                        "source": "hierarchical_child_expansion",
                        "document_semantic_rank": row["semantic_rank"],
                        "best_child_baseline_rank": row["best_child_baseline_rank"],
                        "fusion_score": row["fusion_score"],
                        "baseline_chunk_score": baseline_candidate.score if baseline_candidate is not None else None,
                    },
                    child_chunk_ids=[],
                )
                results.append(candidate)
                seen_candidate_ids.add(candidate_id)
                if len(results) >= self._candidate_limit:
                    break
            if len(results) >= self._candidate_limit:
                break
        return results

    def _child_chunks(self, document_id: str) -> list[KnowledgeChunkV2]:
        return [
            self._corpus.chunks_by_id[chunk_id]
            for chunk_id in self._corpus.child_chunk_ids_by_document.get(document_id, [])
        ]


def evaluate_runtime_eligibility(
    *,
    candidate: HierarchicalCandidate,
    runtime_context: RetrievalRuntimeContextV2,
    document: KnowledgeDocumentV2,
    chunk: KnowledgeChunkV2 | None = None,
) -> RuntimeEligibilityResult:
    reasons: list[str] = []
    effective_on = runtime_context.effective_on or date.today()
    target = chunk or document

    if not document.is_active(as_of=effective_on):
        reasons.append("not_effective")
    if runtime_context.allowed_document_types and document.document_type.value not in set(runtime_context.allowed_document_types):
        reasons.append("document_type_not_allowed")
    if runtime_context.industries and document.industries and set(document.industries).isdisjoint(set(runtime_context.industries)):
        reasons.append("industry_mismatch")
    if runtime_context.tags and document.tags and set(document.tags).isdisjoint(set(runtime_context.tags)):
        reasons.append("tag_mismatch")

    operational_scope = set(runtime_context.operational_solution_scope)
    applicable = set(target.applicable_solution_ids)
    excluded = set(target.excluded_solution_ids)
    if operational_scope and excluded & operational_scope:
        reasons.append("excluded_solution_conflict")
    if target.scope_type.value != "global_policy" and applicable and operational_scope and not applicable.issubset(operational_scope):
        reasons.append("solution_scope_mismatch")

    return RuntimeEligibilityResult(runtime_eligible=not reasons, rejection_reasons=reasons)


def build_context_materialization_preview(
    *,
    candidates: list[HierarchicalCandidate],
    corpus: HierarchicalCorpus,
) -> ContextMaterializationPreview:
    blocks: list[MaterializedContextBlock] = []
    seen_document_parent_blocks: set[str] = set()
    seen_chunk_blocks: set[str] = set()
    normalized_contents: set[str] = set()
    duplicate_blocks_removed = 0
    duplicate_content_risk = False

    for candidate in candidates:
        if candidate.runtime_eligible is not True:
            continue
        if candidate.candidate_type is HierarchicalCandidateType.document:
            if candidate.document_id in seen_document_parent_blocks:
                duplicate_blocks_removed += 1
                continue
            document = corpus.documents_by_id[candidate.document_id]
            content = _render_document_materialized_block(document)
            normalized = _normalize_block_content(content)
            if normalized in normalized_contents:
                duplicate_content_risk = True
            normalized_contents.add(normalized)
            blocks.append(
                MaterializedContextBlock(
                    block_id=f"document-block:{candidate.document_id}",
                    candidate_id=candidate.candidate_id,
                    candidate_type=candidate.candidate_type,
                    document_id=candidate.document_id,
                    citation_label=candidate.citation_label,
                    title=document.title,
                    content=content,
                )
            )
            seen_document_parent_blocks.add(candidate.document_id)
        else:
            assert candidate.chunk_id is not None
            if candidate.chunk_id in seen_chunk_blocks:
                duplicate_blocks_removed += 1
                continue
            chunk = corpus.chunks_by_id[candidate.chunk_id]
            document = corpus.documents_by_id[candidate.document_id]
            content = _render_chunk_materialized_block(document=document, chunk=chunk)
            normalized = _normalize_block_content(content)
            if normalized in normalized_contents:
                duplicate_content_risk = True
            normalized_contents.add(normalized)
            blocks.append(
                MaterializedContextBlock(
                    block_id=f"chunk-block:{candidate.chunk_id}",
                    candidate_id=candidate.candidate_id,
                    candidate_type=candidate.candidate_type,
                    document_id=candidate.document_id,
                    chunk_id=candidate.chunk_id,
                    parent_document_id=candidate.parent_document_id,
                    citation_label=chunk.citation_label,
                    title=document.title,
                    content=content,
                )
            )
            seen_chunk_blocks.add(candidate.chunk_id)

    return ContextMaterializationPreview(
        materialized_blocks=blocks,
        document_block_count=sum(1 for block in blocks if block.candidate_type is HierarchicalCandidateType.document),
        chunk_block_count=sum(1 for block in blocks if block.candidate_type is HierarchicalCandidateType.chunk),
        estimated_character_count=sum(len(block.content) for block in blocks),
        duplicate_blocks_removed=duplicate_blocks_removed,
        duplicate_content_risk=duplicate_content_risk,
    )


def build_citation_preview(
    *,
    candidates: list[HierarchicalCandidate],
    corpus: HierarchicalCorpus,
) -> CitationPreview:
    groups: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if candidate.runtime_eligible is not True:
            continue
        document = corpus.documents_by_id[candidate.document_id]
        group = groups.setdefault(
            candidate.document_id,
            {
                "parent_document": {
                    "candidate_type": "document",
                    "document_id": document.document_id,
                    "title": document.title,
                    "citation_label": f"DOC:{document.document_id}",
                },
                "child_evidence": [],
            },
        )
        if candidate.candidate_type is HierarchicalCandidateType.chunk:
            group["child_evidence"].append(
                {
                    "candidate_type": "chunk",
                    "document_id": candidate.document_id,
                    "chunk_id": candidate.chunk_id,
                    "citation_label": candidate.citation_label,
                    "parent_title": document.title,
                }
            )
    return CitationPreview(groups=[CitationPreviewGroup.model_validate(group) for group in groups.values()])


def assess_completeness(
    *,
    candidates: list[HierarchicalCandidate],
    context_preview: ContextMaterializationPreview,
    citation_preview: CitationPreview,
) -> CompletenessAssessment:
    fallback_reasons: list[str] = []
    suggested_actions: list[str] = []
    eligible_candidates = [candidate for candidate in candidates if candidate.runtime_eligible is True]
    eligible_chunk_count = sum(1 for candidate in eligible_candidates if candidate.candidate_type is HierarchicalCandidateType.chunk)
    eligible_document_count = sum(1 for candidate in eligible_candidates if candidate.candidate_type is HierarchicalCandidateType.document)

    if not candidates:
        fallback_reasons.append("hierarchical_pool_empty")
    if candidates and not eligible_candidates:
        fallback_reasons.append("runtime_eligibility_rejected_all_candidates")
    if eligible_candidates and eligible_chunk_count == 0:
        fallback_reasons.append("required_evidence_missing")
    if context_preview.materialized_blocks and eligible_candidates and len(context_preview.materialized_blocks) < min(2, len(eligible_candidates)):
        fallback_reasons.append("final_evidence_count_insufficient")
    if context_preview.duplicate_content_risk:
        fallback_reasons.append("candidate_structure_or_citation_not_safely_materialized")
    if any(candidate.candidate_type is HierarchicalCandidateType.chunk and candidate.parent_document_id != candidate.document_id for candidate in candidates):
        fallback_reasons.append("parent_child_metadata_conflict")
    if eligible_document_count and eligible_chunk_count and len(citation_preview.groups) == 0:
        fallback_reasons.append("candidate_structure_or_citation_not_safely_materialized")

    if fallback_reasons:
        suggested_actions = [
            "require_human_confirmation",
            "return_verified_evidence_only",
            "mark_answer_incomplete",
        ]

    return CompletenessAssessment(
        evidence_complete=not fallback_reasons,
        fallback_recommended=bool(fallback_reasons),
        fallback_reasons=fallback_reasons,
        suggested_actions=suggested_actions,
    )


def resolve_hierarchical_mode(raw_value: str | None) -> HierarchicalRetrievalMode:
    normalized = (raw_value or "off").strip().casefold()
    if normalized == HierarchicalRetrievalMode.shadow.value:
        return HierarchicalRetrievalMode.shadow
    return HierarchicalRetrievalMode.off


def build_query_hash(query: str) -> str:
    return hashlib.sha256(query.strip().encode("utf-8")).hexdigest()[:16]


def summarize_rejection_reasons(candidates: list[HierarchicalCandidate]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for candidate in candidates:
        counter.update(candidate.rejection_reasons)
    return dict(sorted(counter.items()))


def _render_document_context(
    *,
    document: KnowledgeDocumentV2,
    child_chunks: list[KnowledgeChunkV2],
) -> str:
    section_titles = [
        str(chunk.metadata.get("section_title", "")).strip()
        for chunk in child_chunks
        if isinstance(chunk.metadata, dict) and chunk.metadata.get("section_title")
    ]
    parts = [
        f"Document Title: {document.title}",
        f"Document Summary: {document.summary}",
        f"Document Type: {document.document_type.value}",
        f"Scope Type: {document.scope_type.value}",
    ]
    if document.primary_solution_id:
        parts.append(f"Primary Solution Name: {document.primary_solution_id}")
    if document.applicable_solution_ids:
        parts.append(f"Applicable Solution Names: {', '.join(document.applicable_solution_ids)}")
    if document.industries:
        parts.append(f"Industries: {', '.join(document.industries)}")
    if document.tags:
        parts.append(f"Tags: {', '.join(document.tags)}")
    if section_titles:
        parts.append(f"Child Citation Labels: {' | '.join(section_titles)}")
    if child_chunks:
        parts.append(f"Child Chunk Contents: {' || '.join(chunk.content for chunk in child_chunks)}")
    return "\n".join(parts).strip()


def _render_document_materialized_block(document: KnowledgeDocumentV2) -> str:
    parts = [
        f"Title: {document.title}",
        f"Summary: {document.summary}",
        f"Document Type: {document.document_type.value}",
        f"Scope Type: {document.scope_type.value}",
    ]
    if document.applicable_solution_ids:
        parts.append(f"Applicable Solutions: {', '.join(document.applicable_solution_ids)}")
    return "\n".join(parts).strip()


def _render_chunk_materialized_block(
    *,
    document: KnowledgeDocumentV2,
    chunk: KnowledgeChunkV2,
) -> str:
    return "\n".join(
        [
            f"Parent Title: {document.title}",
            f"Citation: {chunk.citation_label}",
            f"Chunk Content: {chunk.content}",
        ]
    ).strip()


def _normalize_block_content(content: str) -> str:
    return " ".join(content.split())


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _rrf_score(
    *,
    semantic_rank: int,
    best_child_baseline_rank: int | None,
    k: int,
) -> float:
    score = 1.0 / (k + semantic_rank)
    if best_child_baseline_rank is not None:
        score += 1.0 / (k + best_child_baseline_rank)
    return score
