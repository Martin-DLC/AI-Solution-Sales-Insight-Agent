from __future__ import annotations

from pydantic import Field

from evaluation.retrieval.comparison import RetrievalMethodComparisonEntry, select_retrieval_method
from schemas.common_models import StrictBaseModel


class RetrievalMethodComparisonV2(StrictBaseModel):
    entries: list[RetrievalMethodComparisonEntry] = Field(default_factory=list)
    selected_method: str | None = None
    selection_status: str
    selection_reasons: list[str] = Field(default_factory=list)
    rejected_methods: list[str] = Field(default_factory=list)
    comparison_limitations: list[str] = Field(default_factory=list)
    benchmark_config_hash: str
    method_config_hashes: dict[str, str]
    retrieval_contract_version: str
    failure_taxonomy_version: str
    boundary_contract_version: str


def select_retrieval_method_v2(
    *,
    entries: list[RetrievalMethodComparisonEntry],
    benchmark_config_hash: str,
    method_config_hashes: dict[str, str],
    retrieval_contract_version: str,
    failure_taxonomy_version: str,
    boundary_contract_version: str,
) -> RetrievalMethodComparisonV2:
    comparison = select_retrieval_method(entries)
    return RetrievalMethodComparisonV2(
        entries=entries,
        selected_method=comparison.selected_method.value if comparison.selected_method else None,
        selection_status=comparison.selection_status,
        selection_reasons=list(comparison.selection_reasons),
        rejected_methods=list(comparison.rejected_methods),
        comparison_limitations=list(comparison.comparison_limitations),
        benchmark_config_hash=benchmark_config_hash,
        method_config_hashes=dict(method_config_hashes),
        retrieval_contract_version=retrieval_contract_version,
        failure_taxonomy_version=failure_taxonomy_version,
        boundary_contract_version=boundary_contract_version,
    )
