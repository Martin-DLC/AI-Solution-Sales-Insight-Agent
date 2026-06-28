from __future__ import annotations

import math
from collections import Counter
from enum import Enum
from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from schemas.common_models import StrictBaseModel


class RetrievalQueryType(str, Enum):
    solution_discovery = "solution_discovery"
    capability_check = "capability_check"
    solution_boundary = "solution_boundary"
    implementation_risk = "implementation_risk"
    compliance_requirement = "compliance_requirement"
    integration_requirement = "integration_requirement"
    customer_readiness = "customer_readiness"
    case_study_search = "case_study_search"


class RetrievalMethod(str, Enum):
    lexical_v1 = "lexical_v1"
    vector_v1 = "vector_v1"
    hybrid_v1 = "hybrid_v1"


def _deduplicate_text(values: list[str], field_label: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            raise ValueError(f"{field_label} cannot include empty values.")
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _json_safe(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, bool)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json_safe(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_safe(item) for key, item in value.items())
    return False


class RetrievalEvaluationCase(StrictBaseModel):
    retrieval_case_id: str
    source_case_id: str
    query_type: RetrievalQueryType
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    expected_relevant_document_ids: list[str] = Field(default_factory=list)
    expected_relevant_chunk_ids: list[str] = Field(default_factory=list)
    forbidden_document_ids: list[str] = Field(default_factory=list)
    required_solution_ids: list[str] = Field(default_factory=list)
    forbidden_solution_ids: list[str] = Field(default_factory=list)
    minimum_relevant_hits: int
    tags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator(
        "expected_relevant_document_ids",
        "expected_relevant_chunk_ids",
        "forbidden_document_ids",
        "required_solution_ids",
        "forbidden_solution_ids",
        "tags",
        "notes",
    )
    @classmethod
    def deduplicate_text_lists(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Retrieval evaluation list field")

    @field_validator("filters")
    @classmethod
    def filters_must_be_json_safe(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not _json_safe(value):
            raise ValueError("Retrieval evaluation filters must be JSON-safe.")
        return value

    @field_validator("minimum_relevant_hits")
    @classmethod
    def minimum_relevant_hits_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Retrieval evaluation minimum_relevant_hits must be greater than 0.")
        return value

    @model_validator(mode="after")
    def validate_case(self) -> Self:
        if not (self.expected_relevant_document_ids or self.expected_relevant_chunk_ids):
            raise ValueError("Retrieval evaluation case must define at least one expected relevant document or chunk ID.")

        expected_ids = set(self.expected_relevant_document_ids) | set(self.expected_relevant_chunk_ids)
        forbidden_ids = set(self.forbidden_document_ids)
        overlap = expected_ids & forbidden_ids
        if overlap:
            raise ValueError("Retrieval evaluation expected and forbidden IDs must not overlap.")

        if set(self.required_solution_ids) & set(self.forbidden_solution_ids):
            raise ValueError("Retrieval evaluation required_solution_ids and forbidden_solution_ids must not overlap.")

        lowered_query = self.query.casefold()
        if "hidden reference" in lowered_query or "reference pack" in lowered_query:
            raise ValueError("Retrieval evaluation query must not mention hidden reference material.")
        return self


class RetrievalCandidate(StrictBaseModel):
    rank: int
    document_id: str
    chunk_id: str | None = None
    score: float
    retrieval_method: RetrievalMethod
    matched_terms: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    citation_label: str
    solution_ids: list[str] = Field(default_factory=list)

    @field_validator("rank")
    @classmethod
    def rank_must_start_at_one(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Retrieval candidate rank must be greater than or equal to 1.")
        return value

    @field_validator("score")
    @classmethod
    def score_must_be_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Retrieval candidate score must be finite.")
        return value

    @field_validator("matched_terms", "solution_ids")
    @classmethod
    def deduplicate_candidate_lists(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Retrieval candidate list field")

    @field_validator("metadata")
    @classmethod
    def metadata_must_be_json_safe(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not _json_safe(value):
            raise ValueError("Retrieval candidate metadata must be JSON-safe.")
        return value


class RetrievalRunResult(StrictBaseModel):
    retrieval_case_id: str
    retrieval_method: RetrievalMethod
    retrieved_candidates: list[RetrievalCandidate] = Field(default_factory=list)
    latency_ms: int
    error_type: str | None = None
    error_message: str | None = None

    @field_validator("latency_ms")
    @classmethod
    def latency_must_be_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Retrieval run latency_ms must be zero or greater.")
        return value

    @model_validator(mode="after")
    def validate_run(self) -> Self:
        methods = {candidate.retrieval_method for candidate in self.retrieved_candidates}
        if methods and methods != {self.retrieval_method}:
            raise ValueError("Retrieval run candidates must all use the same retrieval_method.")

        ranks = [candidate.rank for candidate in self.retrieved_candidates]
        if ranks and ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("Retrieval run candidate ranks must be continuous from 1.")
        return self


class RetrievalCaseScore(StrictBaseModel):
    retrieval_case_id: str
    retrieval_method: RetrievalMethod
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    precision_at_3: float
    precision_at_5: float
    reciprocal_rank: float
    forbidden_hit: bool
    solution_boundary_violation: bool
    request_error: bool
    latency_ms: int
    eligible_for_rag: bool
    disqualification_reasons: list[str] = Field(default_factory=list)

    @field_validator(
        "recall_at_1",
        "recall_at_3",
        "recall_at_5",
        "precision_at_3",
        "precision_at_5",
        "reciprocal_rank",
    )
    @classmethod
    def ratios_must_be_valid(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("Retrieval case score ratios must be between 0 and 1.")
        return value

    @field_validator("latency_ms")
    @classmethod
    def latency_must_be_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Retrieval case score latency_ms must be zero or greater.")
        return value

    @field_validator("disqualification_reasons")
    @classmethod
    def deduplicate_reasons(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Retrieval disqualification reasons")


class RetrievalEvaluationSummary(StrictBaseModel):
    retrieval_method: RetrievalMethod
    case_count: int
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    precision_at_3: float
    precision_at_5: float
    mean_reciprocal_rank: float
    forbidden_hit_rate: float
    solution_boundary_violation_rate: float
    average_latency_ms: float
    eligible_for_rag: bool
    request_error_count: int = 0
    disqualification_reasons: list[str] = Field(default_factory=list)

    @field_validator(
        "recall_at_1",
        "recall_at_3",
        "recall_at_5",
        "precision_at_3",
        "precision_at_5",
        "mean_reciprocal_rank",
        "forbidden_hit_rate",
        "solution_boundary_violation_rate",
    )
    @classmethod
    def ratios_must_be_valid(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("Retrieval summary ratios must be between 0 and 1.")
        return value

    @field_validator("case_count", "request_error_count")
    @classmethod
    def counts_must_be_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Retrieval summary counts must be zero or greater.")
        return value

    @field_validator("average_latency_ms")
    @classmethod
    def average_latency_must_be_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Retrieval summary average_latency_ms must be zero or greater.")
        return value

    @field_validator("disqualification_reasons")
    @classmethod
    def deduplicate_reasons(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Retrieval summary disqualification reasons")


class RetrievalEvaluationDataset(StrictBaseModel):
    cases: list[RetrievalEvaluationCase] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dataset(self) -> Self:
        case_ids = [case.retrieval_case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Retrieval evaluation case IDs must be unique.")
        return self


def summarize_case_mix(cases: list[RetrievalEvaluationCase]) -> dict[str, int]:
    counts = Counter(case.query_type.value for case in cases)
    return dict(sorted(counts.items()))
