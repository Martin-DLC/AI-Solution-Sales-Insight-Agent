from __future__ import annotations

import time
from typing import Any, Self

from pydantic import model_validator

from evaluation.retrieval.models import RetrievalCandidate, RetrievalMethod
from knowledge_base.retrieval.lexical import WeightedBM25Retriever
from knowledge_base.retrieval.vector import ExactVectorRetriever
from schemas.common_models import StrictBaseModel


class HybridBaselineConfig(StrictBaseModel):
    baseline_version: str
    retrieval_method: str
    lexical_method: str
    vector_method: str
    lexical_candidate_k: int
    vector_candidate_k: int
    output_top_k: int
    rrf_k: int
    lexical_weight: float
    vector_weight: float
    score_round_digits: int
    tie_break_rule: str
    synthetic_data: bool

    @model_validator(mode="after")
    def validate_config(self) -> Self:
        if self.baseline_version != "hybrid_rrf_v1":
            raise ValueError("Hybrid baseline version must be hybrid_rrf_v1.")
        if self.retrieval_method != "lexical_vector_rrf":
            raise ValueError("Hybrid retrieval_method must be lexical_vector_rrf.")
        if self.lexical_method != "weighted_bm25":
            raise ValueError("Hybrid lexical_method must be weighted_bm25.")
        if self.vector_method != "dense_cosine":
            raise ValueError("Hybrid vector_method must be dense_cosine.")
        if self.output_top_k != 5:
            raise ValueError("Hybrid output_top_k must be fixed at 5.")
        if self.synthetic_data is not True:
            raise ValueError("Hybrid synthetic_data must be true.")
        return self


class ReciprocalRankFusionRetriever:
    def __init__(
        self,
        *,
        config: HybridBaselineConfig,
        lexical_retriever: WeightedBM25Retriever,
        vector_retriever: ExactVectorRetriever,
    ) -> None:
        self._config = config
        self._lexical_retriever = lexical_retriever
        self._vector_retriever = vector_retriever
        self._last_retrieval_debug: dict[str, Any] = {
            "filtered_candidate_count": 0,
            "elapsed_ms": 0,
        }

    @property
    def config(self) -> HybridBaselineConfig:
        return self._config

    @property
    def last_retrieval_debug(self) -> dict[str, Any]:
        return dict(self._last_retrieval_debug)

    def retrieve(
        self,
        *,
        query: str,
        filters: dict[str, object],
        top_k: int,
    ) -> list[RetrievalCandidate]:
        started = time.perf_counter()
        lexical_candidates = self._lexical_retriever.retrieve(
            query=query,
            filters=filters,
            top_k=self._config.lexical_candidate_k,
        )
        vector_candidates = self._vector_retriever.retrieve(
            query=query,
            filters=filters,
            top_k=self._config.vector_candidate_k,
        )

        merged: dict[tuple[str, str | None], dict[str, Any]] = {}
        for rank, candidate in enumerate(lexical_candidates, start=1):
            key = (candidate.document_id, candidate.chunk_id)
            merged.setdefault(key, _seed_merged_candidate(candidate))
            merged[key]["lexical_rank"] = rank
            merged[key]["lexical_score"] = candidate.score
            merged[key]["matched_terms"] = list(candidate.matched_terms)

        for rank, candidate in enumerate(vector_candidates, start=1):
            key = (candidate.document_id, candidate.chunk_id)
            merged.setdefault(key, _seed_merged_candidate(candidate))
            merged[key]["vector_rank"] = rank
            merged[key]["vector_score"] = candidate.score

        scored: list[dict[str, Any]] = []
        for value in merged.values():
            lexical_rank = value["lexical_rank"]
            vector_rank = value["vector_rank"]
            rrf_score = 0.0
            if lexical_rank is not None:
                rrf_score += self._config.lexical_weight / (self._config.rrf_k + lexical_rank)
            if vector_rank is not None:
                rrf_score += self._config.vector_weight / (self._config.rrf_k + vector_rank)
            value["rrf_score"] = round(rrf_score, self._config.score_round_digits)
            scored.append(value)

        scored.sort(key=lambda item: (-item["rrf_score"], item["document_id"], item["chunk_id"] or ""))
        elapsed_ms = max(0, int((time.perf_counter() - started) * 1000))
        self._last_retrieval_debug = {
            "filtered_candidate_count": max(
                self._lexical_retriever.last_retrieval_debug.get("filtered_candidate_count", 0),
                self._vector_retriever.last_retrieval_debug.get("filtered_candidate_count", 0),
            ),
            "elapsed_ms": elapsed_ms,
        }
        return [
            RetrievalCandidate(
                rank=rank,
                document_id=item["document_id"],
                chunk_id=item["chunk_id"],
                score=item["rrf_score"],
                retrieval_method=RetrievalMethod.hybrid_v1,
                matched_terms=list(item["matched_terms"]),
                metadata={
                    "lexical_rank": item["lexical_rank"],
                    "vector_rank": item["vector_rank"],
                    "lexical_score": item["lexical_score"],
                    "vector_score": item["vector_score"],
                    "rrf_score": item["rrf_score"],
                    "document_type": item["document_type"],
                },
                citation_label=item["citation_label"],
                solution_ids=list(item["solution_ids"]),
            )
            for rank, item in enumerate(scored[:top_k], start=1)
        ]


def _seed_merged_candidate(candidate: RetrievalCandidate) -> dict[str, Any]:
    return {
        "document_id": candidate.document_id,
        "chunk_id": candidate.chunk_id,
        "citation_label": candidate.citation_label,
        "solution_ids": list(candidate.solution_ids),
        "document_type": candidate.metadata.get("document_type"),
        "matched_terms": [],
        "lexical_rank": None,
        "vector_rank": None,
        "lexical_score": None,
        "vector_score": None,
    }
