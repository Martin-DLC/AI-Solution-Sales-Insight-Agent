from __future__ import annotations

from collections import Counter
from statistics import mean

from evaluation.model_benchmark.models import (
    BenchmarkRunStatus,
    NodeModelBenchmarkSummary,
    NodeBenchmarkRunResult,
)
from agent.workflow_c.state import WorkflowNodeName


def _pass_rate(results: list[NodeBenchmarkRunResult], attribute: str) -> float:
    if not results:
        return 0.0
    passed = sum(1 for result in results if getattr(result, attribute))
    return passed / len(results)


def _unique_reasons(reasons: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            result.append(reason)
    return result


def summarize_node_model_results(
    results: list[NodeBenchmarkRunResult],
) -> NodeModelBenchmarkSummary:
    if not results:
        raise ValueError("Benchmark results must include at least one run.")

    node_names = {result.node_name for result in results}
    if len(node_names) != 1:
        raise ValueError("Benchmark results must target exactly one node_name.")

    model_config_ids = {result.model_config_id for result in results}
    if len(model_config_ids) != 1:
        raise ValueError("Benchmark results must target exactly one model_config_id.")

    node_name = results[0].node_name
    model_config_id = results[0].model_config_id

    case_count = len(results)
    passed_count = sum(1 for result in results if result.status is BenchmarkRunStatus.passed)
    request_error_count = sum(
        1 for result in results if result.status is BenchmarkRunStatus.request_error
    )
    json_parse_pass_rate = _pass_rate(results, "json_parse_success")
    schema_pass_rate = _pass_rate(results, "schema_validation_success")
    business_rule_pass_rate = _pass_rate(results, "business_rule_success")
    evidence_reference_pass_rate = _pass_rate(results, "evidence_reference_valid")
    candidate_boundary_pass_rate = _pass_rate(results, "candidate_boundary_valid")

    latency_values = [result.latency_ms for result in results if result.latency_ms is not None]
    average_latency_ms = mean(latency_values) if latency_values else 0.0
    total_tokens = sum(result.total_tokens or 0 for result in results)
    cost_values = [result.estimated_cost for result in results if result.estimated_cost is not None]
    estimated_total_cost = sum(cost_values) if cost_values else None

    disqualification_reasons: list[str] = []
    if request_error_count:
        disqualification_reasons.append("request_error")
    if json_parse_pass_rate < 1.0:
        disqualification_reasons.append("json_parse_failure")
    if schema_pass_rate < 1.0:
        disqualification_reasons.append("schema_validation_failure")
    blocking_failures = sum(1 for result in results if result.blocking_failure_count > 0)
    if blocking_failures:
        disqualification_reasons.append("blocking_assertion_failure")

    if node_name in {
        WorkflowNodeName.fact_extraction,
        WorkflowNodeName.underlying_pain,
    } and evidence_reference_pass_rate < 1.0:
        disqualification_reasons.append("evidence_reference_failure")
    if node_name is WorkflowNodeName.solution_recommendation and candidate_boundary_pass_rate < 1.0:
        disqualification_reasons.append("candidate_boundary_failure")
    if node_name is WorkflowNodeName.information_gap and business_rule_pass_rate < 1.0:
        disqualification_reasons.append("business_rule_failure")

    eligible_for_routing = (
        request_error_count == 0
        and json_parse_pass_rate == 1.0
        and schema_pass_rate == 1.0
        and blocking_failures == 0
        and (
            node_name
            not in {WorkflowNodeName.fact_extraction, WorkflowNodeName.underlying_pain}
            or evidence_reference_pass_rate == 1.0
        )
        and (
            node_name is not WorkflowNodeName.solution_recommendation
            or candidate_boundary_pass_rate == 1.0
        )
        and (
            node_name is not WorkflowNodeName.information_gap
            or business_rule_pass_rate == 1.0
        )
    )

    if eligible_for_routing:
        disqualification_reasons = []
    else:
        disqualification_reasons = _unique_reasons(disqualification_reasons)

    return NodeModelBenchmarkSummary(
        node_name=node_name,
        model_config_id=model_config_id,
        case_count=case_count,
        passed_count=passed_count,
        json_parse_pass_rate=json_parse_pass_rate,
        schema_pass_rate=schema_pass_rate,
        business_rule_pass_rate=business_rule_pass_rate,
        evidence_reference_pass_rate=evidence_reference_pass_rate,
        candidate_boundary_pass_rate=candidate_boundary_pass_rate,
        average_latency_ms=average_latency_ms,
        total_tokens=total_tokens,
        estimated_total_cost=estimated_total_cost,
        eligible_for_routing=eligible_for_routing,
        disqualification_reasons=disqualification_reasons,
    )
