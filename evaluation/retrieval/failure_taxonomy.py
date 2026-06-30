from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from enum import Enum
from typing import Any


class RetrievalContractVersion(str, Enum):
    V1_LEGACY = "v1_legacy"
    V2_METHOD_AWARE = "v2_method_aware"


class RetrievalFailureReason(str, Enum):
    EMPTY_QUERY = "empty_query"
    NO_RELEVANT_HIT_AT_5 = "no_relevant_hit_at_5"
    INSUFFICIENT_RELEVANT_HITS = "insufficient_relevant_hits"
    FORBIDDEN_DOCUMENT_HIT = "forbidden_document_hit"
    SOLUTION_BOUNDARY_VIOLATION = "solution_boundary_violation"
    OPERATIONAL_FILTER_EXCLUDED_ALL = "operational_filter_excluded_all"
    RETRIEVAL_ERROR = "retrieval_error"
    MISSING_REQUIRED_DEBUG = "missing_required_debug"


class RetrievalDebugField(str, Enum):
    RAW_QUERY_PRESENT = "raw_query_present"
    NORMALIZED_QUERY_PRESENT = "normalized_query_present"
    CANDIDATE_COUNT = "candidate_count"
    RETRIEVAL_METHOD = "retrieval_method"
    LEXICAL_QUERY_TOKENS = "lexical_query_tokens"
    LEXICAL_MATCHED_TERMS = "lexical_matched_terms"
    QUERY_EMBEDDING_GENERATED = "query_embedding_generated"
    EMBEDDING_DIMENSION = "embedding_dimension"
    LEXICAL_CANDIDATE_COUNT = "lexical_candidate_count"
    VECTOR_CANDIDATE_COUNT = "vector_candidate_count"
    FUSED_CANDIDATE_COUNT = "fused_candidate_count"


METHOD_REQUIRED_DEBUG_FIELDS: dict[str, set[str]] = {
    "lexical_v1": {
        RetrievalDebugField.RAW_QUERY_PRESENT.value,
        RetrievalDebugField.NORMALIZED_QUERY_PRESENT.value,
        RetrievalDebugField.CANDIDATE_COUNT.value,
        RetrievalDebugField.RETRIEVAL_METHOD.value,
        RetrievalDebugField.LEXICAL_QUERY_TOKENS.value,
    },
    "vector_v1": {
        RetrievalDebugField.RAW_QUERY_PRESENT.value,
        RetrievalDebugField.NORMALIZED_QUERY_PRESENT.value,
        RetrievalDebugField.CANDIDATE_COUNT.value,
        RetrievalDebugField.RETRIEVAL_METHOD.value,
        RetrievalDebugField.QUERY_EMBEDDING_GENERATED.value,
        RetrievalDebugField.EMBEDDING_DIMENSION.value,
    },
    "hybrid_v1": {
        RetrievalDebugField.RAW_QUERY_PRESENT.value,
        RetrievalDebugField.NORMALIZED_QUERY_PRESENT.value,
        RetrievalDebugField.CANDIDATE_COUNT.value,
        RetrievalDebugField.RETRIEVAL_METHOD.value,
        RetrievalDebugField.LEXICAL_CANDIDATE_COUNT.value,
        RetrievalDebugField.VECTOR_CANDIDATE_COUNT.value,
        RetrievalDebugField.FUSED_CANDIDATE_COUNT.value,
    },
}


def classify_retrieval_failures_v1_legacy(
    *,
    query: str,
    result: Any,
    metrics: Any,
    debug: Mapping[str, object],
    minimum_relevant_hits: int = 1,
) -> list[str]:
    reasons: list[str] = []
    relevant_hits = _extract_relevant_hit_count(metrics)

    if _extract(result, "error_type") not in (None, ""):
        reasons.append(RetrievalFailureReason.RETRIEVAL_ERROR.value)
    if not debug.get("query_tokens"):
        reasons.append("empty_query_tokens")
    elif int(debug.get("filtered_candidate_count", 0) or 0) == 0:
        reasons.append(RetrievalFailureReason.OPERATIONAL_FILTER_EXCLUDED_ALL.value)
    if relevant_hits == 0:
        reasons.append(RetrievalFailureReason.NO_RELEVANT_HIT_AT_5.value)
    if relevant_hits < minimum_relevant_hits:
        reasons.append(RetrievalFailureReason.INSUFFICIENT_RELEVANT_HITS.value)
    if bool(_extract(metrics, "forbidden_hit")):
        reasons.append(RetrievalFailureReason.FORBIDDEN_DOCUMENT_HIT.value)
    if bool(_extract(metrics, "solution_boundary_violation")):
        reasons.append(RetrievalFailureReason.SOLUTION_BOUNDARY_VIOLATION.value)
    return _deduplicate(reasons)


def classify_retrieval_failures_v2(
    *,
    query: str,
    retrieval_method: str,
    result: Any,
    metrics: object,
    debug: Mapping[str, object],
    minimum_relevant_hits: int = 1,
) -> list[str]:
    reasons: list[str] = []
    missing_debug_fields = missing_required_debug_fields_v2(
        retrieval_method=retrieval_method,
        debug=debug,
    )
    normalized_query = normalize_query_text(query)
    relevant_hits = _extract_relevant_hit_count(metrics)

    if not normalized_query:
        reasons.append(RetrievalFailureReason.EMPTY_QUERY.value)
    if missing_debug_fields:
        reasons.append(RetrievalFailureReason.MISSING_REQUIRED_DEBUG.value)
    if bool(_extract(result, "error_type")):
        reasons.append(RetrievalFailureReason.RETRIEVAL_ERROR.value)
    if bool(debug.get("operational_filter_excluded_all")):
        reasons.append(RetrievalFailureReason.OPERATIONAL_FILTER_EXCLUDED_ALL.value)
    if _extract_ratio(metrics, "recall_at_5") == 0:
        reasons.append(RetrievalFailureReason.NO_RELEVANT_HIT_AT_5.value)
    if relevant_hits < minimum_relevant_hits:
        reasons.append(RetrievalFailureReason.INSUFFICIENT_RELEVANT_HITS.value)
    if bool(_extract(metrics, "forbidden_hit")):
        reasons.append(RetrievalFailureReason.FORBIDDEN_DOCUMENT_HIT.value)
    if bool(_extract(metrics, "solution_boundary_violation")):
        reasons.append(RetrievalFailureReason.SOLUTION_BOUNDARY_VIOLATION.value)
    return _deduplicate(reasons)


def normalize_query_text(query: str) -> str:
    normalized = unicodedata.normalize("NFKC", query)
    return "".join(normalized.split())


def missing_required_debug_fields_v2(
    *,
    retrieval_method: str,
    debug: Mapping[str, object],
) -> list[str]:
    required = METHOD_REQUIRED_DEBUG_FIELDS.get(retrieval_method, set())
    missing = [
        field_name
        for field_name in sorted(required)
        if field_name not in debug or debug[field_name] is None
    ]
    return missing


def _extract(value: Any, field_name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(field_name)
    return getattr(value, field_name, None)


def _extract_ratio(value: Any, field_name: str) -> float:
    raw = _extract(value, field_name)
    if raw is None:
        return 0.0
    return float(raw)


def _extract_relevant_hit_count(metrics: Any) -> int:
    explicit = _extract(metrics, "relevant_hit_count")
    if explicit is not None:
        return int(explicit)
    recall_at_5 = _extract(metrics, "recall_at_5")
    minimum_relevant_hits = _extract(metrics, "minimum_relevant_hits")
    if recall_at_5 is None or minimum_relevant_hits in (None, 0):
        return 0
    if float(recall_at_5) <= 0:
        return 0
    estimated = round(float(recall_at_5) * int(minimum_relevant_hits))
    return max(0, estimated)


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
