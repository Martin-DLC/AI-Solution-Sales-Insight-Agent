from __future__ import annotations

import json

import pytest

from evaluation.retrieval.models import (
    RetrievalCandidate,
    RetrievalEvaluationCase,
    RetrievalEvaluationDataset,
    RetrievalMethod,
    RetrievalQueryType,
    RetrievalRunResult,
)


def sample_case(**overrides):
    payload = {
        "retrieval_case_id": "RET-001",
        "source_case_id": "DEV-01",
        "query_type": RetrievalQueryType.solution_discovery,
        "query": "客户希望改善续约风险识别与服务运营可视化。",
        "filters": {"industries": ["field_services"], "document_types": ["solution"]},
        "expected_relevant_document_ids": ["KB-SOL-001"],
        "expected_relevant_chunk_ids": [],
        "forbidden_document_ids": ["KB-SOL-999"],
        "required_solution_ids": ["service-risk-dashboard"],
        "forbidden_solution_ids": ["finance-copilot"],
        "minimum_relevant_hits": 1,
        "tags": ["dev", "service"],
        "notes": ["synthetic-case"],
    }
    payload.update(overrides)
    return RetrievalEvaluationCase.model_validate(payload)


def sample_candidate(**overrides):
    payload = {
        "rank": 1,
        "document_id": "KB-SOL-001",
        "chunk_id": "KB-SOL-001#chunk-001",
        "score": 0.92,
        "retrieval_method": RetrievalMethod.lexical_v1,
        "matched_terms": ["续约风险", "服务运营"],
        "metadata": {"document_type": "solution"},
        "citation_label": "KB-SOL-001 §overview",
        "solution_ids": ["service-risk-dashboard"],
    }
    payload.update(overrides)
    return RetrievalCandidate.model_validate(payload)


def test_expected_and_forbidden_ids_cannot_overlap() -> None:
    with pytest.raises(ValueError, match="must not overlap"):
        sample_case(
            expected_relevant_document_ids=["KB-SOL-001"],
            forbidden_document_ids=["KB-SOL-001"],
        )


def test_minimum_relevant_hits_must_be_positive() -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        sample_case(minimum_relevant_hits=0)


def test_query_type_enum_is_supported() -> None:
    case = sample_case(query_type=RetrievalQueryType.integration_requirement)

    assert case.query_type is RetrievalQueryType.integration_requirement


def test_case_requires_at_least_one_expected_id() -> None:
    with pytest.raises(ValueError, match="at least one expected relevant"):
        sample_case(
            expected_relevant_document_ids=[],
            expected_relevant_chunk_ids=[],
        )


def test_filters_must_be_json_safe() -> None:
    with pytest.raises(ValueError, match="JSON-safe"):
        sample_case(filters={"bad": {1, 2}})


def test_candidate_deduplicates_solution_ids_and_terms() -> None:
    candidate = sample_candidate(
        matched_terms=["续约风险", "续约风险"],
        solution_ids=["service-risk-dashboard", "service-risk-dashboard"],
    )

    assert candidate.matched_terms == ["续约风险"]
    assert candidate.solution_ids == ["service-risk-dashboard"]


def test_run_rejects_mixed_retrieval_methods() -> None:
    with pytest.raises(ValueError, match="same retrieval_method"):
        RetrievalRunResult.model_validate(
            {
                "retrieval_case_id": "RET-001",
                "retrieval_method": "lexical_v1",
                "retrieved_candidates": [
                    sample_candidate().model_dump(mode="json"),
                    sample_candidate(
                        rank=2,
                        document_id="KB-SOL-002",
                        chunk_id="KB-SOL-002#chunk-001",
                        retrieval_method=RetrievalMethod.vector_v1,
                    ).model_dump(mode="json"),
                ],
                "latency_ms": 12,
            }
        )


def test_run_result_json_serialization_is_stable() -> None:
    run = RetrievalRunResult(
        retrieval_case_id="RET-001",
        retrieval_method=RetrievalMethod.lexical_v1,
        retrieved_candidates=[sample_candidate()],
        latency_ms=15,
    )

    dumped_once = json.dumps(run.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    dumped_twice = json.dumps(run.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)

    assert dumped_once == dumped_twice


def test_dataset_rejects_duplicate_case_ids() -> None:
    case = sample_case()

    with pytest.raises(ValueError, match="case IDs must be unique"):
        RetrievalEvaluationDataset(cases=[case, case])
