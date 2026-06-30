from __future__ import annotations

from evaluation.retrieval.failure_taxonomy import (
    classify_retrieval_failures_v1_legacy,
    classify_retrieval_failures_v2,
    missing_required_debug_fields_v2,
)


def test_raw_empty_query_triggers_empty_query() -> None:
    reasons = classify_retrieval_failures_v2(
        query="",
        retrieval_method="vector_v1",
        result={},
        metrics={"recall_at_5": 1.0, "relevant_hit_count": 1},
        debug={
            "raw_query_present": False,
            "normalized_query_present": False,
            "candidate_count": 1,
            "retrieval_method": "vector_v1",
            "query_embedding_generated": True,
            "embedding_dimension": 384,
        },
    )
    assert "empty_query" in reasons


def test_whitespace_query_triggers_empty_query() -> None:
    reasons = classify_retrieval_failures_v2(
        query=" \n\t ",
        retrieval_method="lexical_v1",
        result={},
        metrics={"recall_at_5": 1.0, "relevant_hit_count": 1},
        debug={
            "raw_query_present": True,
            "normalized_query_present": False,
            "candidate_count": 1,
            "retrieval_method": "lexical_v1",
            "lexical_query_tokens": ["x"],
        },
    )
    assert "empty_query" in reasons


def test_non_empty_vector_query_does_not_trigger_empty_query() -> None:
    reasons = classify_retrieval_failures_v2(
        query="需要查询工单协同方案",
        retrieval_method="vector_v1",
        result={},
        metrics={"recall_at_5": 1.0, "relevant_hit_count": 1},
        debug={
            "raw_query_present": True,
            "normalized_query_present": True,
            "candidate_count": 1,
            "retrieval_method": "vector_v1",
            "query_embedding_generated": True,
            "embedding_dimension": 384,
        },
    )
    assert "empty_query" not in reasons


def test_query_tokens_missing_is_not_empty_query() -> None:
    reasons = classify_retrieval_failures_v2(
        query="查询知识库",
        retrieval_method="vector_v1",
        result={},
        metrics={"recall_at_5": 1.0, "relevant_hit_count": 1},
        debug={
            "raw_query_present": True,
            "normalized_query_present": True,
            "candidate_count": 1,
            "retrieval_method": "vector_v1",
            "query_embedding_generated": True,
            "embedding_dimension": 384,
        },
    )
    assert "empty_query" not in reasons


def test_matched_terms_empty_is_not_empty_query() -> None:
    reasons = classify_retrieval_failures_v2(
        query="查询知识库",
        retrieval_method="hybrid_v1",
        result={},
        metrics={"recall_at_5": 1.0, "relevant_hit_count": 1},
        debug={
            "raw_query_present": True,
            "normalized_query_present": True,
            "candidate_count": 1,
            "retrieval_method": "hybrid_v1",
            "lexical_candidate_count": 0,
            "vector_candidate_count": 1,
            "fused_candidate_count": 1,
            "lexical_matched_terms": [],
        },
    )
    assert "empty_query" not in reasons


def test_lexical_missing_required_debug_is_identified() -> None:
    missing = missing_required_debug_fields_v2(
        retrieval_method="lexical_v1",
        debug={
            "raw_query_present": True,
            "normalized_query_present": True,
            "candidate_count": 1,
            "retrieval_method": "lexical_v1",
        },
    )
    assert missing == ["lexical_query_tokens"]


def test_vector_missing_required_debug_is_identified() -> None:
    missing = missing_required_debug_fields_v2(
        retrieval_method="vector_v1",
        debug={
            "raw_query_present": True,
            "normalized_query_present": True,
            "candidate_count": 1,
            "retrieval_method": "vector_v1",
        },
    )
    assert missing == ["embedding_dimension", "query_embedding_generated"]


def test_v1_legacy_behavior_kept_for_missing_query_tokens() -> None:
    reasons = classify_retrieval_failures_v1_legacy(
        query="查询知识库",
        result={},
        metrics={"recall_at_5": 1.0, "relevant_hit_count": 1},
        debug={"filtered_candidate_count": 3},
    )
    assert "empty_query_tokens" in reasons
