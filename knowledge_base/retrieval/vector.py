from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from evaluation.retrieval.models import RetrievalCandidate, RetrievalMethod
from knowledge_base.models import KnowledgeChunk, KnowledgeDocument, KnowledgeSourceStatus
from knowledge_base.retrieval.embeddings import EmbeddingProvider
from schemas.common_models import StrictBaseModel


SUPPORTED_FILTER_KEYS = frozenset(
    {
        "document_types",
        "industries",
        "solution_ids",
        "tags",
        "statuses",
        "effective_on",
    }
)


class VectorBaselineConfig(StrictBaseModel):
    baseline_version: str
    retrieval_method: str
    embedding_provider: str
    model_name_or_path: str
    model_revision: str | None = None
    query_prefix: str
    document_prefix: str
    normalize_embeddings: bool
    device: str
    batch_size: int
    top_k: int
    candidate_k: int
    score_round_digits: int
    tie_break_rule: str
    active_statuses: list[KnowledgeSourceStatus] = Field(default_factory=list)
    evaluation_date: date
    cache_enabled: bool
    cache_directory: str
    synthetic_data: bool

    @field_validator("active_statuses")
    @classmethod
    def deduplicate_statuses(cls, values: list[KnowledgeSourceStatus]) -> list[KnowledgeSourceStatus]:
        seen: set[KnowledgeSourceStatus] = set()
        result: list[KnowledgeSourceStatus] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result

    @field_validator("cache_directory")
    @classmethod
    def validate_cache_directory(cls, value: str) -> str:
        if value.startswith("/"):
            raise ValueError("Vector cache_directory must be project-relative, not absolute.")
        if ".." in Path(value).parts:
            raise ValueError("Vector cache_directory must stay inside the project.")
        return value

    @model_validator(mode="after")
    def validate_config(self) -> Self:
        if self.baseline_version != "vector_v1":
            raise ValueError("Vector baseline version must be vector_v1.")
        if self.retrieval_method != "dense_cosine":
            raise ValueError("Vector retrieval_method must be dense_cosine.")
        if self.embedding_provider != "sentence_transformers":
            raise ValueError("Vector embedding_provider must be sentence_transformers.")
        if self.top_k != 5:
            raise ValueError("Vector top_k must be fixed at 5.")
        if self.candidate_k != 20:
            raise ValueError("Vector candidate_k must be fixed at 20.")
        if self.synthetic_data is not True:
            raise ValueError("Vector synthetic_data must be true.")
        if self.query_prefix not in {"query:", "query: "}:
            raise ValueError("Vector query_prefix must be fixed to 'query: '.")
        if self.document_prefix not in {"passage:", "passage: "}:
            raise ValueError("Vector document_prefix must be fixed to 'passage: '.")
        object.__setattr__(self, "query_prefix", "query: ")
        object.__setattr__(self, "document_prefix", "passage: ")
        return self


@dataclass(frozen=True)
class _VectorIndexEntry:
    chunk: KnowledgeChunk
    document: KnowledgeDocument
    embedding: list[float]


class ExactVectorRetriever:
    def __init__(
        self,
        *,
        config: VectorBaselineConfig,
        embedding_provider: EmbeddingProvider,
        project_root: Path | None = None,
    ) -> None:
        self._config = config
        self._embedding_provider = embedding_provider
        self._project_root = project_root or Path.cwd()
        self._entries: list[_VectorIndexEntry] = []
        self._documents_by_id: dict[str, KnowledgeDocument] = {}
        self._last_retrieval_debug: dict[str, Any] = {
            "filtered_candidate_count": 0,
            "elapsed_ms": 0,
        }

    @property
    def config(self) -> VectorBaselineConfig:
        return self._config

    @property
    def last_retrieval_debug(self) -> dict[str, Any]:
        return dict(self._last_retrieval_debug)

    def build_index(
        self,
        *,
        documents: list[KnowledgeDocument],
        chunks: list[KnowledgeChunk],
        knowledge_base_version: str,
    ) -> None:
        self._documents_by_id = {document.document_id: document for document in documents}
        if len(self._documents_by_id) != len(documents):
            raise ValueError("Exact vector retriever requires unique knowledge document IDs.")

        missing_chunks: list[KnowledgeChunk] = []
        cached_embeddings: dict[str, list[float]] = {}
        for chunk in chunks:
            document = self._documents_by_id.get(chunk.document_id)
            if document is None:
                raise ValueError(f"Knowledge chunk {chunk.chunk_id} references an unknown document.")
            if self._config.cache_enabled:
                cached = self._load_cached_embedding(
                    knowledge_base_version=knowledge_base_version,
                    chunk=chunk,
                )
                if cached is not None:
                    cached_embeddings[chunk.chunk_id] = cached
                    continue
            missing_chunks.append(chunk)

        if missing_chunks:
            encoded_vectors = self._embedding_provider.encode_documents([chunk.content for chunk in missing_chunks])
            for chunk, embedding in zip(missing_chunks, encoded_vectors):
                cached_embeddings[chunk.chunk_id] = embedding
                if self._config.cache_enabled:
                    self._write_cached_embedding(
                        knowledge_base_version=knowledge_base_version,
                        chunk=chunk,
                        embedding=embedding,
                    )

        entries: list[_VectorIndexEntry] = []
        for chunk in chunks:
            document = self._documents_by_id[chunk.document_id]
            embedding = cached_embeddings.get(chunk.chunk_id)
            if embedding is None:
                raise ValueError(f"Missing cached vector embedding for chunk {chunk.chunk_id}.")
            entries.append(_VectorIndexEntry(chunk=chunk, document=document, embedding=embedding))
        self._entries = entries

    def retrieve(
        self,
        *,
        query: str,
        filters: dict[str, object],
        top_k: int,
    ) -> list[RetrievalCandidate]:
        started = time.perf_counter()
        if top_k <= 0:
            raise ValueError("Exact vector retrieval top_k must be greater than 0.")
        self._validate_filters(filters)

        if not query.strip():
            self._last_retrieval_debug = {
                "filtered_candidate_count": 0,
                "elapsed_ms": 0,
            }
            return []

        filtered_entries = self._filter_entries(filters)
        if not filtered_entries:
            self._last_retrieval_debug = {
                "filtered_candidate_count": 0,
                "elapsed_ms": 0,
            }
            return []

        query_embedding = self._embedding_provider.encode_queries([query])[0]
        scored_candidates: list[tuple[float, str, str, _VectorIndexEntry]] = []
        for entry in filtered_entries:
            score = round(_dot(query_embedding, entry.embedding), self._config.score_round_digits)
            scored_candidates.append((score, entry.chunk.document_id, entry.chunk.chunk_id, entry))

        scored_candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
        elapsed_ms = max(0, int((time.perf_counter() - started) * 1000))
        self._last_retrieval_debug = {
            "filtered_candidate_count": len(filtered_entries),
            "elapsed_ms": elapsed_ms,
        }
        return [
            RetrievalCandidate(
                rank=rank,
                document_id=document_id,
                chunk_id=chunk_id,
                score=score,
                retrieval_method=RetrievalMethod.vector_v1,
                matched_terms=[],
                metadata={
                    "embedding_provider_id": self._embedding_provider.provider_id,
                    "document_type": entry.chunk.document_type.value,
                    "solution_ids": list(entry.chunk.solution_ids),
                    "industries": list(entry.chunk.industries),
                },
                citation_label=entry.chunk.citation_label,
                solution_ids=list(entry.chunk.solution_ids),
            )
            for rank, (score, document_id, chunk_id, entry) in enumerate(scored_candidates[:top_k], start=1)
        ]

    def _filter_entries(self, filters: dict[str, object]) -> list[_VectorIndexEntry]:
        effective_on = self._extract_effective_on(filters)
        allowed_statuses = self._extract_statuses(filters)

        entries: list[_VectorIndexEntry] = []
        for entry in self._entries:
            document = entry.document
            if document.status not in allowed_statuses:
                continue
            if document.is_expired(as_of=effective_on):
                continue
            if not self._matches_scalar_filter(document.document_type.value, filters.get("document_types")):
                continue
            if not self._matches_collection_filter(document.industries, filters.get("industries")):
                continue
            if not self._matches_collection_filter(document.solution_ids, filters.get("solution_ids")):
                continue
            if not self._matches_collection_filter(document.tags, filters.get("tags")):
                continue
            entries.append(entry)
        return entries

    def _extract_statuses(self, filters: dict[str, object]) -> set[KnowledgeSourceStatus]:
        raw_statuses = filters.get("statuses")
        if raw_statuses is None:
            return set(self._config.active_statuses)
        if not isinstance(raw_statuses, list):
            raise ValueError("Retrieval filter statuses must be a list.")
        return {KnowledgeSourceStatus(value) for value in raw_statuses}

    def _extract_effective_on(self, filters: dict[str, object]) -> date:
        raw = filters.get("effective_on")
        if raw is None:
            return self._config.evaluation_date
        if not isinstance(raw, str):
            raise ValueError("Retrieval filter effective_on must be an ISO date string.")
        return date.fromisoformat(raw)

    def _validate_filters(self, filters: dict[str, object]) -> None:
        unknown = set(filters) - SUPPORTED_FILTER_KEYS
        if unknown:
            raise ValueError(f"Unsupported retrieval filter keys: {sorted(unknown)}")

    @staticmethod
    def _matches_scalar_filter(value: str, expected: object) -> bool:
        if expected is None:
            return True
        if not isinstance(expected, list):
            raise ValueError("Retrieval filter values must be lists for document_types.")
        return value in expected

    @staticmethod
    def _matches_collection_filter(values: list[str], expected: object) -> bool:
        if expected is None:
            return True
        if not isinstance(expected, list):
            raise ValueError("Retrieval filter values must be lists.")
        return bool(set(values) & set(expected))

    def _cache_path(self, *, knowledge_base_version: str, chunk: KnowledgeChunk) -> Path:
        key = {
            "knowledge_base_version": knowledge_base_version,
            "chunk_id": chunk.chunk_id,
            "content_hash": hashlib.sha1(chunk.content.encode("utf-8")).hexdigest(),
            "provider_id": self._embedding_provider.provider_id,
            "model_name": getattr(self._embedding_provider, "model_name", self._embedding_provider.provider_id),
            "normalize_embeddings": self._config.normalize_embeddings,
        }
        digest = hashlib.sha1(json.dumps(key, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        return self._project_root / self._config.cache_directory / f"{digest}.json"

    def _load_cached_embedding(
        self,
        *,
        knowledge_base_version: str,
        chunk: KnowledgeChunk,
    ) -> list[float] | None:
        cache_path = self._cache_path(knowledge_base_version=knowledge_base_version, chunk=chunk)
        if not cache_path.exists():
            return None
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        vector = payload.get("vector")
        dimension = payload.get("dimension")
        if not isinstance(vector, list) or not isinstance(dimension, int):
            raise ValueError("Cached embedding file is invalid.")
        if dimension != self._embedding_provider.dimension or len(vector) != self._embedding_provider.dimension:
            raise ValueError("Cached embedding dimension mismatch; rebuild the vector cache before retrying.")
        normalized = [float(value) for value in vector]
        for value in normalized:
            if not math.isfinite(value):
                raise ValueError("Cached embedding contains non-finite values.")
        return normalized

    def _write_cached_embedding(
        self,
        *,
        knowledge_base_version: str,
        chunk: KnowledgeChunk,
        embedding: list[float],
    ) -> None:
        cache_path = self._cache_path(knowledge_base_version=knowledge_base_version, chunk=chunk)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "knowledge_base_version": knowledge_base_version,
            "chunk_id": chunk.chunk_id,
            "provider_id": self._embedding_provider.provider_id,
            "dimension": self._embedding_provider.dimension,
            "vector": embedding,
        }
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _dot(first: list[float], second: list[float]) -> float:
    return sum(left * right for left, right in zip(first, second))
