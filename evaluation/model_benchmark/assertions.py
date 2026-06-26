from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from evaluation.model_benchmark.models import (
    BenchmarkAssertion,
    BenchmarkAssertionResult,
    BenchmarkAssertionType,
    NodeExecutionObservation,
)


_VALID_RECOMMENDED_OWNERS = {
    "sales",
    "presales",
    "customer",
    "it",
    "security",
    "management",
    "unknown",
}

_FORBIDDEN_KEYWORDS = {
    "api_key",
    "authorization",
    "bearer_token",
    "secret",
    "hidden reference pack",
}


@dataclass(frozen=True)
class BenchmarkAssertionContext:
    fixture: dict[str, Any]
    state: dict[str, Any]
    node_output: dict[str, Any] | None
    observation: NodeExecutionObservation


def evaluate_benchmark_assertions(
    assertions: list[BenchmarkAssertion],
    context: BenchmarkAssertionContext,
) -> list[BenchmarkAssertionResult]:
    return [evaluate_benchmark_assertion(assertion, context) for assertion in assertions]


def evaluate_benchmark_assertion(
    assertion: BenchmarkAssertion,
    context: BenchmarkAssertionContext,
) -> BenchmarkAssertionResult:
    actual, passed = _evaluate_assertion(assertion, context)
    return BenchmarkAssertionResult(
        assertion_id=assertion.assertion_id,
        assertion_type=assertion.assertion_type,
        blocking=assertion.blocking,
        passed=passed,
        location=assertion.location,
        failure_reason=None if passed else _build_failure_reason(assertion, actual),
        actual_summary=None if actual is None else _summarize_actual(actual),
    )


def _evaluate_assertion(
    assertion: BenchmarkAssertion,
    context: BenchmarkAssertionContext,
) -> tuple[Any, bool]:
    assertion_type = assertion.assertion_type
    if assertion_type is BenchmarkAssertionType.json_parse_success:
        actual = context.observation.json_parse_success
        return actual, actual is bool(assertion.expected_value)
    if assertion_type is BenchmarkAssertionType.schema_validation_success:
        actual = context.observation.schema_validation_success
        return actual, actual is bool(assertion.expected_value)
    if assertion_type is BenchmarkAssertionType.business_rule_success:
        actual = context.observation.business_rule_success
        return actual, actual is bool(assertion.expected_value)
    if assertion_type is BenchmarkAssertionType.evidence_reference_valid:
        actual = context.observation.evidence_reference_valid
        return actual, actual is bool(assertion.expected_value)
    if assertion_type is BenchmarkAssertionType.candidate_boundary_valid:
        actual = context.observation.candidate_boundary_valid
        return actual, actual is bool(assertion.expected_value)
    if assertion_type is BenchmarkAssertionType.required_value_equals:
        actual = _resolve_required_value(context, assertion.location)
        return actual, _required_value_matches(assertion, actual)
    if assertion_type is BenchmarkAssertionType.forbidden_value_absent:
        actual = _resolve_value(context, assertion.location)
        return actual, _forbidden_value_absent(actual)
    if assertion_type is BenchmarkAssertionType.referenced_id_exists:
        actual = _collect_referenced_ids(context)
        return actual, _referenced_ids_exist(actual, context)
    actual = _resolve_value(context, assertion.location)
    return actual, actual == assertion.expected_value


def _resolve_required_value(
    context: BenchmarkAssertionContext,
    location: str,
) -> Any:
    actual = _resolve_value(context, location)
    if location == "recommended_owner" and actual is None and context.node_output is not None:
        actual = _first_information_gap_owner(context.node_output)
    return actual


def _resolve_value(
    context: BenchmarkAssertionContext,
    location: str,
) -> Any:
    if location in {"response", "output"}:
        return context.node_output
    if location == "fixture":
        return context.fixture
    if location == "state":
        return context.state
    return _lookup_path(context.node_output, location)


def _first_information_gap_owner(node_output: dict[str, Any]) -> Any:
    gaps = node_output.get("information_gaps")
    if isinstance(gaps, list) and gaps:
        first_gap = gaps[0]
        if isinstance(first_gap, dict):
            return first_gap.get("recommended_owner")
    return None


def _required_value_matches(assertion: BenchmarkAssertion, actual: Any) -> bool:
    expected = assertion.expected_value
    if expected == "valid_owner":
        return isinstance(actual, str) and actual in _VALID_RECOMMENDED_OWNERS
    return actual == expected


def _forbidden_value_absent(value: Any) -> bool:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True) if value is not None else ""
    lowered = serialized.casefold()
    return not any(keyword in lowered for keyword in _FORBIDDEN_KEYWORDS)


def _collect_referenced_ids(context: BenchmarkAssertionContext) -> list[str]:
    referenced_ids: list[str] = []
    payload = context.node_output or {}
    if "facts" in payload and isinstance(payload["facts"], list):
        for fact in payload["facts"]:
            if isinstance(fact, dict):
                referenced_ids.extend(_source_ids_from_references(fact.get("evidence")))
    if "underlying_pains" in payload and isinstance(payload["underlying_pains"], list):
        for pain in payload["underlying_pains"]:
            if isinstance(pain, dict):
                referenced_ids.extend(_source_ids_from_references(pain.get("evidence")))
    if "solution_recommendations" in payload and isinstance(payload["solution_recommendations"], list):
        for recommendation in payload["solution_recommendations"]:
            if isinstance(recommendation, dict):
                referenced_ids.extend(_source_ids_from_references(recommendation.get("knowledge_references")))
    referenced_ids.extend(_source_ids_from_references(payload.get("knowledge_references")))
    return referenced_ids


def _source_ids_from_references(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        reference["source_id"]
        for reference in value
        if isinstance(reference, dict) and isinstance(reference.get("source_id"), str)
    ]


def _referenced_ids_exist(
    referenced_ids: list[str],
    context: BenchmarkAssertionContext,
) -> bool:
    if not referenced_ids:
        return False

    source_index = _as_dict(context.state.get("source_index"))
    source_ids = {
        item.get("source_id")
        for item in source_index.get("items", [])
        if isinstance(item, dict)
    }
    retrieved_solutions = _as_dict(context.state.get("retrieved_solutions"))
    candidate_ids = {
        item.get("solution_id")
        for item in retrieved_solutions.get("candidates", [])
        if isinstance(item, dict)
    }
    candidate_source_ids = {
        item.get("source_id")
        for item in retrieved_solutions.get("candidates", [])
        if isinstance(item, dict)
    }
    allowed_ids = {value for value in source_ids if isinstance(value, str)} | {
        value for value in candidate_ids if isinstance(value, str)
    } | {
        value for value in candidate_source_ids if isinstance(value, str)
    }
    return all(reference_id in allowed_ids for reference_id in referenced_ids)


def _lookup_path(payload: Any, path: str) -> Any:
    if payload is None:
        return None
    current: Any = payload
    for part in _split_path(path):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            if index < 0 or index >= len(current):
                return None
            current = current[index]
        else:
            return None
    return current


def _split_path(path: str) -> list[str]:
    parts: list[str] = []
    for chunk in path.replace("[", ".").replace("]", "").split("."):
        chunk = chunk.strip()
        if chunk:
            parts.append(chunk)
    return parts


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    return {}


def _summarize_actual(actual: Any) -> str:
    try:
        summary = json.dumps(actual, ensure_ascii=False, sort_keys=True)
    except TypeError:
        summary = repr(actual)
    if len(summary) > 500:
        return f"{summary[:497]}..."
    return summary


def _build_failure_reason(assertion: BenchmarkAssertion, actual: Any) -> str:
    return (
        f"Assertion {assertion.assertion_id} failed at {assertion.location}; "
        f"expected {assertion.expected_value!r}, got {_summarize_actual(actual)}."
    )
