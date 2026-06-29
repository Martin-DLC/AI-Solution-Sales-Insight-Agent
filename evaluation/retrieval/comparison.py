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
    implementation_complexity: str = "moderate"
    runtime_dependencies: list[str] = Field(default_factory=list)


class RetrievalMethodComparison(StrictBaseModel):
    entries: list[RetrievalMethodComparisonEntry] = Field(default_factory=list)
    selected_method: RetrievalMethod | None = None
    selection_status: Literal["eligible_method_selected", "no_eligible_method"]
    selection_reasons: list[str] = Field(default_factory=list)
    rejected_methods: list[str] = Field(default_factory=list)
    comparison_limitations: list[str] = Field(default_factory=list)


def select_retrieval_method(
    entries: list[RetrievalMethodComparisonEntry],
) -> RetrievalMethodComparison:
    eligible = [entry for entry in entries if entry.eligible_for_rag]
    if not eligible:
        return RetrievalMethodComparison(
            entries=entries,
            selected_method=None,
            selection_status="no_eligible_method",
            selection_reasons=["No retrieval method passed the frozen blocking gate."],
            rejected_methods=[entry.retrieval_method.value for entry in entries],
            comparison_limitations=["Selection is limited to the current 16 synthetic retrieval cases."],
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
        selection_reasons=[
            "Selected method passed the frozen blocking gate.",
            "Selection followed the fixed ordering: recall_at_5, forbidden_hit_rate, solution_boundary_violation_rate, mean_reciprocal_rank, average_latency_ms.",
        ],
        rejected_methods=[entry.retrieval_method.value for entry in entries if entry.retrieval_method != ordered[0].retrieval_method],
        comparison_limitations=["Selection is limited to the current 16 synthetic retrieval cases."],
    )
