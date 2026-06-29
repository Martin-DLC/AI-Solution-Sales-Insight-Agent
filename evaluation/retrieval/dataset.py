from __future__ import annotations

import json
from pathlib import Path

from dataio.jsonl_loader import load_jsonl_models
from evaluation.retrieval.models import RetrievalEvaluationCase, RetrievalQueryType
from knowledge_base.dataset import DemoSolutionScope
from knowledge_base.models import KnowledgeDocument, KnowledgeChunk


DEFAULT_RETRIEVAL_CASES_PATH = Path("data/evaluation/retrieval/retrieval_cases.v1.jsonl")

_SECRET_MARKERS = ("api_key", "authorization", "bearer", "secret", "sk-")
_ABSOLUTE_PATH_PREFIXES = ("/Users/", "/home/", "C:\\", "D:\\")
_RUNTIME_MARKERS = ("data/runtime/", ".env")


def load_retrieval_evaluation_cases(
    path: str | Path = DEFAULT_RETRIEVAL_CASES_PATH,
) -> list[RetrievalEvaluationCase]:
    return load_jsonl_models(path, RetrievalEvaluationCase)


def validate_retrieval_evaluation_dataset(
    *,
    cases: list[RetrievalEvaluationCase],
    documents: list[KnowledgeDocument],
    chunks: list[KnowledgeChunk],
    development_case_ids: set[str],
    solution_ids: set[str],
    demo_scope: DemoSolutionScope,
) -> None:
    if len(cases) != 16:
        raise ValueError(f"Retrieval evaluation dataset must contain exactly 16 cases; got {len(cases)}.")

    case_ids = [case.retrieval_case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Retrieval evaluation case IDs must be unique.")

    type_counts: dict[RetrievalQueryType, int] = {query_type: 0 for query_type in RetrievalQueryType}
    source_case_ids: list[str] = []
    documents_by_id = {document.document_id: document for document in documents}
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    selected_solution_ids = set(demo_scope.selected_solution_ids)
    covered_selected_solution_ids: set[str] = set()
    forbidden_solution_case_count = 0
    forbidden_document_case_count = 0
    boundary_or_unsupported_count = 0
    risk_and_readiness_count = 0

    for case in cases:
        _ensure_safe_values(case.retrieval_case_id, case.source_case_id, case.query, *case.tags, *case.notes)
        type_counts[case.query_type] += 1
        if case.source_case_id not in source_case_ids:
            source_case_ids.append(case.source_case_id)
        if case.source_case_id not in development_case_ids:
            raise ValueError(f"Retrieval case {case.retrieval_case_id} uses unknown source_case_id.")

        if case.forbidden_document_ids:
            forbidden_document_case_count += 1
        if case.forbidden_solution_ids:
            forbidden_solution_case_count += 1
        if case.query_type is RetrievalQueryType.solution_boundary or any(
            marker in case.tags for marker in ("boundary", "unsupported")
        ):
            boundary_or_unsupported_count += 1
        if case.query_type in {
            RetrievalQueryType.implementation_risk,
            RetrievalQueryType.compliance_requirement,
            RetrievalQueryType.integration_requirement,
            RetrievalQueryType.customer_readiness,
        }:
            risk_and_readiness_count += 1

        if case.minimum_relevant_hits > (
            len(case.expected_relevant_document_ids) + len(case.expected_relevant_chunk_ids)
        ):
            raise ValueError(f"Retrieval case {case.retrieval_case_id} has an impossible minimum_relevant_hits setting.")

        for solution_id in case.required_solution_ids + case.forbidden_solution_ids:
            if solution_id not in solution_ids:
                raise ValueError(f"Retrieval case {case.retrieval_case_id} references an unknown solution_id.")
            if solution_id not in selected_solution_ids:
                raise ValueError(f"Retrieval case {case.retrieval_case_id} must stay inside the demo solution scope.")
            covered_selected_solution_ids.add(solution_id)

        for document_id in case.expected_relevant_document_ids + case.forbidden_document_ids:
            document = documents_by_id.get(document_id)
            if document is None:
                raise ValueError(f"Retrieval case {case.retrieval_case_id} references an unknown document_id.")
            if not set(document.solution_ids).issubset(selected_solution_ids):
                raise ValueError(f"Retrieval case {case.retrieval_case_id} references a document outside the demo scope.")
            covered_selected_solution_ids.update(document.solution_ids)

        expected_document_ids = set(case.expected_relevant_document_ids)
        for chunk_id in case.expected_relevant_chunk_ids:
            chunk = chunks_by_id.get(chunk_id)
            if chunk is None:
                raise ValueError(f"Retrieval case {case.retrieval_case_id} references an unknown chunk_id.")
            if chunk.document_id not in documents_by_id:
                raise ValueError(f"Retrieval case {case.retrieval_case_id} chunk {chunk_id} has no backing document.")
            if expected_document_ids and chunk.document_id not in expected_document_ids:
                raise ValueError(
                    f"Retrieval case {case.retrieval_case_id} expected chunk {chunk_id} must belong to an expected document."
                )
            covered_selected_solution_ids.update(chunk.solution_ids)

    if any(count != 2 for count in type_counts.values()):
        raise ValueError("Retrieval evaluation dataset must contain exactly 2 cases for each query type.")
    if len(source_case_ids) < 8:
        raise ValueError("Retrieval evaluation dataset must cover at least 8 distinct source cases.")
    if covered_selected_solution_ids != selected_solution_ids:
        raise ValueError("Retrieval evaluation dataset must collectively cover all 6 selected demo solutions.")
    if forbidden_document_case_count < 4:
        raise ValueError("Retrieval evaluation dataset must contain at least 4 cases with forbidden_document_ids.")
    if forbidden_solution_case_count < 4:
        raise ValueError("Retrieval evaluation dataset must contain at least 4 cases with forbidden_solution_ids.")
    if boundary_or_unsupported_count < 4:
        raise ValueError("Retrieval evaluation dataset must contain at least 4 boundary-oriented cases.")
    if risk_and_readiness_count < 4:
        raise ValueError("Retrieval evaluation dataset must contain at least 4 risk or readiness-oriented cases.")


def _ensure_safe_values(*values: str) -> None:
    for value in values:
        lowered = value.casefold()
        if any(marker in lowered for marker in _SECRET_MARKERS):
            raise ValueError("Retrieval evaluation dataset must not contain secret-like values.")
        if any(value.startswith(prefix) for prefix in _ABSOLUTE_PATH_PREFIXES):
            raise ValueError("Retrieval evaluation dataset must not contain absolute local paths.")
        if any(marker.casefold() in lowered for marker in _RUNTIME_MARKERS):
            raise ValueError("Retrieval evaluation dataset must not contain runtime paths or env references.")
