from __future__ import annotations

import math
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from evaluation.retrieval.models import RetrievalCandidate, RetrievalMethod
from knowledge_base.models import KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentType, KnowledgeSourceStatus
from knowledge_base.retrieval.tokenizer import tokenize_lexical_text
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


class LexicalBaselineConfig(StrictBaseModel):
    baseline_version: str
    retrieval_method: str
    tokenizer_version: str
    top_k: int
    k1: float
    b: float
    evaluation_date: date
    active_statuses: list[KnowledgeSourceStatus] = Field(default_factory=list)
    field_weights: dict[str, int]
    score_round_digits: int
    tie_break_rule: str
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

    @field_validator("field_weights")
    @classmethod
    def validate_field_weights(cls, value: dict[str, int]) -> dict[str, int]:
        required = {
            "content",
            "citation_label",
            "tags",
            "industries",
            "solution_ids",
            "document_type",
        }
        if set(value) != required:
            raise ValueError("Lexical baseline field_weights must match the fixed weighted BM25 fields.")
        if any(weight <= 0 for weight in value.values()):
            raise ValueError("Lexical baseline field_weights must be positive integers.")
        return value

    @model_validator(mode="after")
    def validate_config(self) -> Self:
        if self.baseline_version != "lexical_v1":
            raise ValueError("Lexical baseline version must be lexical_v1.")
        if self.retrieval_method != "weighted_bm25":
            raise ValueError("Lexical baseline retrieval_method must be weighted_bm25.")
        if self.tokenizer_version != "mixed_lexical_v1":
            raise ValueError("Lexical baseline tokenizer_version must be mixed_lexical_v1.")
        if self.top_k != 5:
            raise ValueError("Lexical baseline top_k must be fixed at 5.")
        if self.synthetic_data is not True:
            raise ValueError("Lexical baseline synthetic_data must be true.")
        return self


@dataclass(frozen=True)
class _ChunkIndexEntry:
    chunk: KnowledgeChunk
    document: KnowledgeDocument
    weighted_tokens: list[str]
    term_frequencies: Counter[str]
    document_length: int


class WeightedBM25Retriever:
    def __init__(self, *, config: LexicalBaselineConfig) -> None:
        self._config = config
        self._entries: list[_ChunkIndexEntry] = []
        self._documents_by_id: dict[str, KnowledgeDocument] = {}
        self._idf: dict[str, float] = {}
        self._average_document_length: float = 0.0
        self._last_retrieval_debug: dict[str, Any] = {
            "query_tokens": [],
            "filtered_candidate_count": 0,
            "elapsed_ms": 0,
        }

    @property
    def config(self) -> LexicalBaselineConfig:
        return self._config

    @property
    def last_retrieval_debug(self) -> dict[str, Any]:
        return dict(self._last_retrieval_debug)

    def build_index(
        self,
        *,
        documents: list[KnowledgeDocument],
        chunks: list[KnowledgeChunk],
    ) -> None:
        self._documents_by_id = {document.document_id: document for document in documents}
        if len(self._documents_by_id) != len(documents):
            raise ValueError("Weighted BM25 retriever requires unique knowledge document IDs.")

        entries: list[_ChunkIndexEntry] = []
        for chunk in chunks:
            document = self._documents_by_id.get(chunk.document_id)
            if document is None:
                raise ValueError(f"Knowledge chunk {chunk.chunk_id} references an unknown document.")
            weighted_tokens = self._build_weighted_tokens(chunk=chunk)
            term_frequencies = Counter(weighted_tokens)
            entries.append(
                _ChunkIndexEntry(
                    chunk=chunk,
                    document=document,
                    weighted_tokens=weighted_tokens,
                    term_frequencies=term_frequencies,
                    document_length=len(weighted_tokens),
                )
            )

        self._entries = entries
        self._average_document_length = (
            sum(entry.document_length for entry in entries) / len(entries) if entries else 0.0
        )
        self._idf = self._build_idf(entries)

    def retrieve(
        self,
        *,
        query: str,
        filters: dict[str, object],
        top_k: int,
    ) -> list[RetrievalCandidate]:
        started = time.perf_counter()
        if top_k <= 0:
            raise ValueError("Weighted BM25 retrieval top_k must be greater than 0.")
        self._validate_filters(filters)

        query_tokens = tokenize_lexical_text(query)
        if not query_tokens:
            self._last_retrieval_debug = {
                "query_tokens": [],
                "filtered_candidate_count": 0,
                "elapsed_ms": 0,
            }
            return []

        filtered_entries = self._filter_entries(filters)
        if not filtered_entries:
            self._last_retrieval_debug = {
                "query_tokens": query_tokens,
                "filtered_candidate_count": 0,
                "elapsed_ms": 0,
            }
            return []

        scored_candidates: list[tuple[float, str, str, list[str], _ChunkIndexEntry]] = []
        for entry in filtered_entries:
            score = self._score_entry(entry=entry, query_tokens=query_tokens)
            if score <= 0:
                continue
            matched_terms = _deduplicate_preserve_order(
                token for token in query_tokens if token in entry.term_frequencies
            )
            scored_candidates.append(
                (
                    round(score, self._config.score_round_digits),
                    entry.chunk.document_id,
                    entry.chunk.chunk_id,
                    matched_terms,
                    entry,
                )
            )

        scored_candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
        elapsed_ms = max(0, int((time.perf_counter() - started) * 1000))
        self._last_retrieval_debug = {
            "query_tokens": query_tokens,
            "filtered_candidate_count": len(filtered_entries),
            "elapsed_ms": elapsed_ms,
        }
        return [
            RetrievalCandidate(
                rank=rank,
                document_id=document_id,
                chunk_id=chunk_id,
                score=score,
                retrieval_method=RetrievalMethod.lexical_v1,
                matched_terms=matched_terms,
                metadata={
                    "document_type": entry.chunk.document_type.value,
                    "status": entry.document.status.value,
                },
                citation_label=entry.chunk.citation_label,
                solution_ids=list(entry.chunk.solution_ids),
            )
            for rank, (score, document_id, chunk_id, matched_terms, entry) in enumerate(
                scored_candidates[:top_k],
                start=1,
            )
        ]

    def _build_weighted_tokens(self, *, chunk: KnowledgeChunk) -> list[str]:
        fields = {
            "content": tokenize_lexical_text(chunk.content),
            "citation_label": tokenize_lexical_text(chunk.citation_label),
            "tags": [token for value in chunk.tags for token in tokenize_lexical_text(value)],
            "industries": [token for value in chunk.industries for token in tokenize_lexical_text(value)],
            "solution_ids": [token for value in chunk.solution_ids for token in tokenize_lexical_text(value)],
            "document_type": tokenize_lexical_text(chunk.document_type.value),
        }
        weighted: list[str] = []
        for field_name, tokens in fields.items():
            weight = self._config.field_weights[field_name]
            for token in tokens:
                weighted.extend([token] * weight)
        return weighted

    def _build_idf(self, entries: list[_ChunkIndexEntry]) -> dict[str, float]:
        document_count = len(entries)
        if document_count == 0:
            return {}

        document_frequency: Counter[str] = Counter()
        for entry in entries:
            for term in entry.term_frequencies:
                document_frequency[term] += 1

        idf: dict[str, float] = {}
        for term, freq in document_frequency.items():
            idf[term] = math.log(1 + ((document_count - freq + 0.5) / (freq + 0.5)))
        return idf

    def _filter_entries(self, filters: dict[str, object]) -> list[_ChunkIndexEntry]:
        effective_on = self._extract_effective_on(filters)
        allowed_statuses = self._extract_statuses(filters)

        entries: list[_ChunkIndexEntry] = []
        for entry in self._entries:
            document = entry.document
            if document.status not in allowed_statuses:
                continue
            if document.is_expired(as_of=effective_on):
                continue
            if not self._matches_filter_values(document.document_type.value, filters.get("document_types")):
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
        statuses = {KnowledgeSourceStatus(value) for value in raw_statuses}
        return statuses

    def _extract_effective_on(self, filters: dict[str, object]) -> date:
        raw = filters.get("effective_on")
        if raw is None:
            return self._config.evaluation_date
        if not isinstance(raw, str):
            raise ValueError("Retrieval filter effective_on must be an ISO date string.")
        return date.fromisoformat(raw)

    def _score_entry(self, *, entry: _ChunkIndexEntry, query_tokens: list[str]) -> float:
        denominator_base = self._config.k1 * (
            1 - self._config.b + self._config.b * (entry.document_length / max(self._average_document_length, 1.0))
        )
        score = 0.0
        for term in query_tokens:
            term_frequency = entry.term_frequencies.get(term, 0)
            if term_frequency <= 0:
                continue
            idf = self._idf.get(term)
            if idf is None:
                continue
            numerator = term_frequency * (self._config.k1 + 1)
            denominator = term_frequency + denominator_base
            score += idf * (numerator / denominator)
        return score

    def _validate_filters(self, filters: dict[str, object]) -> None:
        unknown = set(filters) - SUPPORTED_FILTER_KEYS
        if unknown:
            raise ValueError(f"Unsupported retrieval filter keys: {sorted(unknown)}")

    @staticmethod
    def _matches_filter_values(value: str, expected: object) -> bool:
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
        expected_values = set(expected)
        return bool(expected_values & set(values))


def _deduplicate_preserve_order(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
