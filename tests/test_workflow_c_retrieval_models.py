from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.workflow_c.retrieval_models import (
    RetrievedSolutionCandidate,
    SolutionRetrievalResult,
)


def candidate(**overrides) -> RetrievedSolutionCandidate:
    payload = {
        "solution_id": "客服辅助回复方案",
        "source_id": "SOLUTION-04",
        "source_type": "solution_library",
        "content": "客服辅助回复方案",
        "score": 0.5,
        "rank": 1,
        "matched_terms": ["客服", "回复"],
    }
    payload.update(overrides)
    return RetrievedSolutionCandidate.model_validate(payload)


def test_candidate_accepts_solution_library_source() -> None:
    item = candidate()

    assert item.source_id == "SOLUTION-04"


def test_candidate_rejects_non_solution_library_source() -> None:
    with pytest.raises(ValidationError):
        candidate(source_type="meeting_transcript")


def test_candidate_rejects_zero_score() -> None:
    with pytest.raises(ValidationError):
        candidate(score=0)


def test_candidate_deduplicates_matched_terms() -> None:
    item = candidate(matched_terms=["客服", "客服", "回复"])

    assert item.matched_terms == ["客服", "回复"]


def test_result_accepts_empty_candidates() -> None:
    result = SolutionRetrievalResult.model_validate(
        {
            "query_text": "NO_ELIGIBLE_AI_OPPORTUNITY",
            "eligible_opportunity_ids": [],
            "top_k": 5,
            "candidate_count": 0,
            "candidates": [],
        }
    )

    assert result.candidate_count == 0


def test_result_candidate_count_must_match() -> None:
    with pytest.raises(ValidationError):
        SolutionRetrievalResult.model_validate(
            {
                "query_text": "客服 回复",
                "eligible_opportunity_ids": ["OPP-01"],
                "top_k": 5,
                "candidate_count": 2,
                "candidates": [candidate().model_dump(mode="json")],
            }
        )


def test_result_rejects_duplicate_solution_ids() -> None:
    first = candidate().model_dump(mode="json")
    second = candidate(source_id="SOLUTION-05", rank=2, score=0.4).model_dump(mode="json")
    with pytest.raises(ValidationError):
        SolutionRetrievalResult.model_validate(
            {
                "query_text": "客服 回复",
                "eligible_opportunity_ids": ["OPP-01"],
                "top_k": 5,
                "candidate_count": 2,
                "candidates": [first, second],
            }
        )


def test_result_rejects_non_continuous_ranks() -> None:
    with pytest.raises(ValidationError):
        SolutionRetrievalResult.model_validate(
            {
                "query_text": "客服 回复",
                "eligible_opportunity_ids": ["OPP-01"],
                "top_k": 5,
                "candidate_count": 1,
                "candidates": [candidate(rank=2).model_dump(mode="json")],
            }
        )


def test_result_rejects_scores_not_descending() -> None:
    first = candidate(score=0.3).model_dump(mode="json")
    second = candidate(
        solution_id="RAG企业知识库方案",
        source_id="SOLUTION-02",
        rank=2,
        score=0.5,
    ).model_dump(mode="json")
    with pytest.raises(ValidationError):
        SolutionRetrievalResult.model_validate(
            {
                "query_text": "客服 回复",
                "eligible_opportunity_ids": ["OPP-01"],
                "top_k": 5,
                "candidate_count": 2,
                "candidates": [first, second],
            }
        )


def test_result_deduplicates_eligible_opportunity_ids() -> None:
    result = SolutionRetrievalResult.model_validate(
        {
            "query_text": "客服 回复",
            "eligible_opportunity_ids": ["OPP-01", "OPP-01"],
            "top_k": 5,
            "candidate_count": 0,
            "candidates": [],
        }
    )

    assert result.eligible_opportunity_ids == ["OPP-01"]
