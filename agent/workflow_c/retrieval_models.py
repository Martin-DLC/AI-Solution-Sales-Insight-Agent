from __future__ import annotations

from enum import Enum
from typing import Self

from pydantic import Field, field_validator, model_validator

from schemas.common_models import EvidenceSourceType, StrictBaseModel


class SolutionRetrievalMethod(str, Enum):
    lexical_v1 = "lexical_v1"


def _deduplicate(values: list[str], field_label: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            raise ValueError(f"{field_label} cannot include empty values.")
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


class RetrievedSolutionCandidate(StrictBaseModel):
    solution_id: str
    source_id: str
    source_type: EvidenceSourceType
    content: str
    score: float
    rank: int
    matched_terms: list[str] = Field(default_factory=list)

    @field_validator("score")
    @classmethod
    def score_must_be_positive_relevance(cls, value: float) -> float:
        if value <= 0 or value > 1:
            raise ValueError("Retrieved solution score must be greater than 0 and at most 1.")
        return value

    @field_validator("rank")
    @classmethod
    def rank_must_start_at_one(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Retrieved solution rank must be greater than or equal to 1.")
        return value

    @field_validator("matched_terms")
    @classmethod
    def matched_terms_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate(values, "Matched terms")

    @model_validator(mode="after")
    def validate_candidate(self) -> Self:
        if self.source_type is not EvidenceSourceType.solution_library:
            raise ValueError("Retrieved solution candidates must come from solution_library.")
        return self


class SolutionRetrievalResult(StrictBaseModel):
    retrieval_method: SolutionRetrievalMethod = SolutionRetrievalMethod.lexical_v1
    query_text: str
    eligible_opportunity_ids: list[str] = Field(default_factory=list)
    top_k: int
    candidate_count: int
    candidates: list[RetrievedSolutionCandidate] = Field(default_factory=list)

    @field_validator("eligible_opportunity_ids")
    @classmethod
    def eligible_opportunity_ids_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate(values, "Eligible opportunity IDs")

    @field_validator("top_k")
    @classmethod
    def top_k_must_be_reasonable(cls, value: int) -> int:
        if value < 1 or value > 20:
            raise ValueError("Solution retrieval top_k must be between 1 and 20.")
        return value

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.candidate_count != len(self.candidates):
            raise ValueError("Candidate count must equal the number of retrieved candidates.")

        solution_ids = [candidate.solution_id for candidate in self.candidates]
        if len(solution_ids) != len(set(solution_ids)):
            raise ValueError("Retrieved solution IDs must not be duplicated.")

        source_ids = [candidate.source_id for candidate in self.candidates]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Retrieved solution source IDs must not be duplicated.")

        ranks = [candidate.rank for candidate in self.candidates]
        if ranks != list(range(1, len(self.candidates) + 1)):
            raise ValueError("Retrieved solution ranks must be continuous from 1.")

        scores = [candidate.score for candidate in self.candidates]
        if scores != sorted(scores, reverse=True):
            raise ValueError("Retrieved solutions must be sorted by score descending.")
        return self
