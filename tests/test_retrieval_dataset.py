from __future__ import annotations

from collections import Counter

from dataio.runtime_cases import load_runtime_cases
from evaluation.retrieval.dataset import (
    load_retrieval_evaluation_cases,
    validate_retrieval_evaluation_dataset,
)
from evaluation.retrieval.models import RetrievalQueryType
from knowledge_base.chunking import build_knowledge_chunks
from knowledge_base.dataset import load_demo_solution_scope, load_knowledge_documents


def test_retrieval_dataset_contains_exactly_16_cases() -> None:
    cases = load_retrieval_evaluation_cases("data/evaluation/retrieval/retrieval_cases.v1.jsonl")

    assert len(cases) == 16


def test_each_query_type_has_exactly_two_cases() -> None:
    cases = load_retrieval_evaluation_cases("data/evaluation/retrieval/retrieval_cases.v1.jsonl")
    counts = Counter(case.query_type for case in cases)

    assert counts == {query_type: 2 for query_type in RetrievalQueryType}


def test_retrieval_dataset_covers_at_least_8_source_cases() -> None:
    cases = load_retrieval_evaluation_cases("data/evaluation/retrieval/retrieval_cases.v1.jsonl")

    assert len({case.source_case_id for case in cases}) >= 8


def test_expected_chunks_belong_to_expected_documents() -> None:
    cases = load_retrieval_evaluation_cases("data/evaluation/retrieval/retrieval_cases.v1.jsonl")
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")
    chunks = build_knowledge_chunks(documents)
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}

    for case in cases:
        expected_docs = set(case.expected_relevant_document_ids)
        for chunk_id in case.expected_relevant_chunk_ids:
            assert chunks_by_id[chunk_id].document_id in expected_docs


def test_required_and_forbidden_solution_ids_stay_inside_demo_scope() -> None:
    cases = load_retrieval_evaluation_cases("data/evaluation/retrieval/retrieval_cases.v1.jsonl")
    selected = set(load_demo_solution_scope("data/knowledge_base/demo_solution_scope.v1.json").selected_solution_ids)

    for case in cases:
        assert set(case.required_solution_ids).issubset(selected)
        assert set(case.forbidden_solution_ids).issubset(selected)


def test_validate_retrieval_dataset_passes_for_tracked_files() -> None:
    cases = load_retrieval_evaluation_cases("data/evaluation/retrieval/retrieval_cases.v1.jsonl")
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")
    chunks = build_knowledge_chunks(documents)
    scope = load_demo_solution_scope("data/knowledge_base/demo_solution_scope.v1.json")
    development_case_ids = {case.case_id for case in load_runtime_cases("data/evaluation/development_cases.jsonl")}

    validate_retrieval_evaluation_dataset(
        cases=cases,
        documents=documents,
        chunks=chunks,
        development_case_ids=development_case_ids,
        solution_ids=set(scope.selected_solution_ids) | set(scope.excluded_solution_ids),
        demo_scope=scope,
    )
