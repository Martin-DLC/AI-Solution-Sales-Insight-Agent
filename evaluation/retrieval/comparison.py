from __future__ import annotations

from typing import Literal

from pydantic import Field

from evaluation.retrieval.models import RetrievalMethod
from schemas.common_models import StrictBaseModel


class RetrievalMethodComparisonEntry(StrictBaseModel):
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
    disqualification_reasons: list[str] = Field(default_factory=list)
    failed_case_ids: list[str] = Field(default_factory=list)


class RetrievalMethodComparison(StrictBaseModel):
    entries: list[RetrievalMethodComparisonEntry] = Field(default_factory=list)
    selected_method: RetrievalMethod | None = None
    selection_status: Literal["eligible_method_selected", "no_eligible_method"]


def select_retrieval_method(
    entries: list[RetrievalMethodComparisonEntry],
) -> RetrievalMethodComparison:
    eligible = [entry for entry in entries if entry.eligible_for_rag]
    if not eligible:
        return RetrievalMethodComparison(
            entries=entries,
            selected_method=None,
            selection_status="no_eligible_method",
        )

    ordered = sorted(
        eligible,
        key=lambda entry: (
            -entry.recall_at_5,
            entry.forbidden_hit_rate,
            entry.solution_boundary_violation_rate,
            -entry.mean_reciprocal_rank,
            entry.average_latency_ms,
            entry.retrieval_method.value,
        ),
    )
    return RetrievalMethodComparison(
        entries=entries,
        selected_method=ordered[0].retrieval_method,
        selection_status="eligible_method_selected",
    )
