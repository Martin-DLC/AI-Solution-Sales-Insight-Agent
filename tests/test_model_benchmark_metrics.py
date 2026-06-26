from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from agent.workflow_c.state import WorkflowNodeName
from evaluation.model_benchmark.metrics import summarize_node_model_results
from evaluation.model_benchmark.models import (
    BenchmarkRunStatus,
    NodeBenchmarkRunResult,
)


def _result(
    *,
    node_name: WorkflowNodeName,
    model_config_id: str = "cfg-1",
    status: BenchmarkRunStatus = BenchmarkRunStatus.passed,
    json_parse_success: bool = True,
    schema_validation_success: bool = True,
    business_rule_success: bool = True,
    evidence_reference_valid: bool = True,
    candidate_boundary_valid: bool = True,
    blocking_failure_count: int = 0,
    assertion_pass_count: int = 3,
    assertion_fail_count: int = 0,
    latency_ms: int = 100,
    prompt_tokens: int | None = 10,
    completion_tokens: int | None = 5,
    total_tokens: int | None = 15,
    estimated_cost: Decimal | None = Decimal("0.01"),
    error_type: str | None = None,
    error_message: str | None = None,
) -> NodeBenchmarkRunResult:
    return NodeBenchmarkRunResult(
        run_id=f"run-{node_name.value}-{status.value}",
        benchmark_case_id="bench-1",
        model_config_id=model_config_id,
        node_name=node_name,
        status=status,
        json_parse_success=json_parse_success,
        schema_validation_success=schema_validation_success,
        business_rule_success=business_rule_success,
        evidence_reference_valid=evidence_reference_valid,
        candidate_boundary_valid=candidate_boundary_valid,
        assertion_pass_count=assertion_pass_count,
        assertion_fail_count=assertion_fail_count,
        blocking_failure_count=blocking_failure_count,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost=estimated_cost,
        error_type=error_type,
        error_message=error_message,
    )


def test_summarize_happy_path_for_fact_extraction() -> None:
    results = [
        _result(node_name=WorkflowNodeName.fact_extraction),
        _result(node_name=WorkflowNodeName.fact_extraction, latency_ms=120, total_tokens=20),
    ]
    summary = summarize_node_model_results(results)
    assert summary.node_name is WorkflowNodeName.fact_extraction
    assert summary.model_config_id == "cfg-1"
    assert summary.case_count == 2
    assert summary.passed_count == 2
    assert summary.eligible_for_routing is True
    assert summary.disqualification_reasons == []


def test_rejects_mixed_node_names() -> None:
    with pytest.raises(ValueError):
        summarize_node_model_results(
            [
                _result(node_name=WorkflowNodeName.fact_extraction),
                _result(node_name=WorkflowNodeName.underlying_pain),
            ]
        )


def test_rejects_mixed_model_configs() -> None:
    with pytest.raises(ValueError):
        summarize_node_model_results(
            [
                _result(node_name=WorkflowNodeName.information_gap, model_config_id="cfg-1"),
                _result(node_name=WorkflowNodeName.information_gap, model_config_id="cfg-2"),
            ]
        )


def test_request_error_disqualifies_routing() -> None:
    summary = summarize_node_model_results(
        [
            _result(
                node_name=WorkflowNodeName.fact_extraction,
                status=BenchmarkRunStatus.request_error,
                json_parse_success=False,
                schema_validation_success=False,
                business_rule_success=False,
                evidence_reference_valid=False,
                candidate_boundary_valid=False,
                blocking_failure_count=1,
                error_type="request_error",
                error_message="temporary failure",
            )
        ]
    )
    assert summary.eligible_for_routing is False
    assert "request_error" in summary.disqualification_reasons


def test_json_failure_disqualifies_routing() -> None:
    summary = summarize_node_model_results(
        [
            _result(
                node_name=WorkflowNodeName.underlying_pain,
                status=BenchmarkRunStatus.failed,
                json_parse_success=False,
                schema_validation_success=False,
                error_type="json_parse_failure",
                error_message="bad json",
            )
        ]
    )
    assert summary.eligible_for_routing is False
    assert "json_parse_failure" in summary.disqualification_reasons


def test_schema_failure_disqualifies_routing() -> None:
    summary = summarize_node_model_results(
        [
            _result(
                node_name=WorkflowNodeName.information_gap,
                status=BenchmarkRunStatus.failed,
                schema_validation_success=False,
                error_type="schema_validation_failure",
                error_message="schema issue",
            )
        ]
    )
    assert summary.eligible_for_routing is False
    assert "schema_validation_failure" in summary.disqualification_reasons


def test_blocking_assertion_failure_disqualifies_routing() -> None:
    summary = summarize_node_model_results(
        [
            _result(
                node_name=WorkflowNodeName.solution_recommendation,
                status=BenchmarkRunStatus.failed,
                blocking_failure_count=1,
                assertion_fail_count=1,
                error_type="blocking_assertion_failure",
                error_message="blocked",
            )
        ]
    )
    assert summary.eligible_for_routing is False
    assert "blocking_assertion_failure" in summary.disqualification_reasons


def test_fact_extraction_requires_perfect_evidence_rate() -> None:
    summary = summarize_node_model_results(
        [
            _result(
                node_name=WorkflowNodeName.fact_extraction,
                status=BenchmarkRunStatus.failed,
                evidence_reference_valid=False,
                error_type="evidence_reference_failure",
                error_message="evidence issue",
            )
        ]
    )
    assert summary.eligible_for_routing is False
    assert "evidence_reference_failure" in summary.disqualification_reasons


def test_underlying_pain_requires_perfect_evidence_rate() -> None:
    summary = summarize_node_model_results(
        [
            _result(
                node_name=WorkflowNodeName.underlying_pain,
                status=BenchmarkRunStatus.failed,
                evidence_reference_valid=False,
                error_type="evidence_reference_failure",
                error_message="evidence issue",
            )
        ]
    )
    assert summary.eligible_for_routing is False
    assert "evidence_reference_failure" in summary.disqualification_reasons


def test_information_gap_requires_perfect_business_rule_rate() -> None:
    summary = summarize_node_model_results(
        [
            _result(
                node_name=WorkflowNodeName.information_gap,
                status=BenchmarkRunStatus.failed,
                business_rule_success=False,
                error_type="business_rule_failure",
                error_message="business rule issue",
            )
        ]
    )
    assert summary.eligible_for_routing is False
    assert "business_rule_failure" in summary.disqualification_reasons


def test_solution_recommendation_requires_perfect_candidate_boundary_rate() -> None:
    summary = summarize_node_model_results(
        [
            _result(
                node_name=WorkflowNodeName.solution_recommendation,
                status=BenchmarkRunStatus.failed,
                candidate_boundary_valid=False,
                error_type="candidate_boundary_failure",
                error_message="candidate issue",
            )
        ]
    )
    assert summary.eligible_for_routing is False
    assert "candidate_boundary_failure" in summary.disqualification_reasons


def test_token_and_latency_aggregation() -> None:
    results = [
        _result(node_name=WorkflowNodeName.fact_extraction, latency_ms=100, total_tokens=20),
        _result(node_name=WorkflowNodeName.fact_extraction, latency_ms=200, total_tokens=30),
    ]
    summary = summarize_node_model_results(results)
    assert summary.total_tokens == 50
    assert summary.average_latency_ms == pytest.approx(150.0)


def test_disqualification_reasons_are_stable() -> None:
    summary = summarize_node_model_results(
        [
            _result(
                node_name=WorkflowNodeName.solution_recommendation,
                status=BenchmarkRunStatus.failed,
                json_parse_success=False,
                schema_validation_success=False,
                candidate_boundary_valid=False,
                blocking_failure_count=1,
                assertion_fail_count=1,
                error_type="candidate_boundary_failure",
                error_message="candidate issue",
            )
        ]
    )
    assert summary.disqualification_reasons == [
        "json_parse_failure",
        "schema_validation_failure",
        "blocking_assertion_failure",
        "candidate_boundary_failure",
    ]
