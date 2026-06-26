from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent.workflow_c.state import WorkflowNodeName
from evaluation.model_benchmark.models import (
    BenchmarkAssertion,
    BenchmarkAssertionType,
    BenchmarkExecutionMode,
    BenchmarkRunManifest,
    BenchmarkRunStatus,
    ModelBenchmarkConfig,
    ModelBenchmarkConfigCatalog,
    ModelTier,
    NodeBenchmarkCase,
    NodeBenchmarkRunResult,
)


def test_allows_four_benchmark_nodes() -> None:
    for node_name in (
        WorkflowNodeName.fact_extraction,
        WorkflowNodeName.underlying_pain,
        WorkflowNodeName.information_gap,
        WorkflowNodeName.solution_recommendation,
    ):
        case = NodeBenchmarkCase(
            benchmark_case_id=f"bench-{node_name.value}",
            source_case_id="DEV-01",
            node_name=node_name,
            input_fixture="fixtures/dev_01.json",
            assertions=[
                BenchmarkAssertion(
                    assertion_id="a1",
                    assertion_type=BenchmarkAssertionType.json_parse_success,
                    location="root",
                    expected_value=True,
                    description="JSON parse must succeed.",
                    blocking=True,
                )
            ],
            tags=["pilot", "pilot"],
            notes=["keep offline"],
        )
        assert case.tags == ["pilot"]


def test_rejects_non_target_node() -> None:
    with pytest.raises(ValidationError):
        NodeBenchmarkCase(
            benchmark_case_id="bench-1",
            source_case_id="DEV-01",
            node_name=WorkflowNodeName.business_impact,
            input_fixture="fixtures/dev_01.json",
            assertions=[
                BenchmarkAssertion(
                    assertion_id="a1",
                    assertion_type=BenchmarkAssertionType.json_parse_success,
                    location="root",
                    expected_value=True,
                    description="JSON parse must succeed.",
                    blocking=True,
                )
            ],
        )


def test_requires_blocking_assertion() -> None:
    with pytest.raises(ValidationError):
        NodeBenchmarkCase(
            benchmark_case_id="bench-2",
            source_case_id="DEV-01",
            node_name=WorkflowNodeName.fact_extraction,
            input_fixture="fixtures/dev_01.json",
            assertions=[
                BenchmarkAssertion(
                    assertion_id="a1",
                    assertion_type=BenchmarkAssertionType.json_parse_success,
                    location="root",
                    expected_value=True,
                    description="JSON parse must succeed.",
                    blocking=False,
                )
            ],
        )


def test_request_error_fields_are_required_for_failed_runs() -> None:
    with pytest.raises(ValidationError):
        NodeBenchmarkRunResult(
            run_id="run-1",
            benchmark_case_id="bench-1",
            model_config_id="cfg-1",
            node_name=WorkflowNodeName.fact_extraction,
            status=BenchmarkRunStatus.request_error,
            json_parse_success=False,
            schema_validation_success=False,
            business_rule_success=False,
            evidence_reference_valid=False,
            candidate_boundary_valid=False,
            assertion_pass_count=0,
            assertion_fail_count=1,
            blocking_failure_count=1,
            latency_ms=0,
        )


def test_passed_runs_cannot_record_blocking_failures() -> None:
    with pytest.raises(ValidationError):
        NodeBenchmarkRunResult(
            run_id="run-2",
            benchmark_case_id="bench-1",
            model_config_id="cfg-1",
            node_name=WorkflowNodeName.fact_extraction,
            status=BenchmarkRunStatus.passed,
            json_parse_success=True,
            schema_validation_success=True,
            business_rule_success=True,
            evidence_reference_valid=True,
            candidate_boundary_valid=True,
            assertion_pass_count=3,
            assertion_fail_count=0,
            blocking_failure_count=1,
            latency_ms=12,
        )


def test_rates_remain_inside_unit_interval() -> None:
    with pytest.raises(ValidationError):
        ModelBenchmarkConfig(
            config_id="cfg-1",
            provider="replay",
            model="model-x",
            tier=ModelTier.fast,
            temperature=2.5,
            max_tokens=256,
            enabled=True,
        )


def test_config_catalog_rejects_duplicate_config_ids() -> None:
    with pytest.raises(ValidationError):
        ModelBenchmarkConfigCatalog(
            configs=[
                ModelBenchmarkConfig(
                    config_id="cfg-1",
                    provider="replay",
                    model="model-a",
                    tier=ModelTier.fast,
                    temperature=0.2,
                    max_tokens=256,
                    enabled=True,
                ),
                ModelBenchmarkConfig(
                    config_id="cfg-1",
                    provider="replay",
                    model="model-b",
                    tier=ModelTier.balanced,
                    temperature=0.4,
                    max_tokens=512,
                    enabled=False,
                ),
            ]
        )


def test_json_serialization_is_stable() -> None:
    result = NodeBenchmarkRunResult(
        run_id="run-3",
        benchmark_case_id="bench-1",
        model_config_id="cfg-1",
        node_name=WorkflowNodeName.information_gap,
        status=BenchmarkRunStatus.passed,
        json_parse_success=True,
        schema_validation_success=True,
        business_rule_success=True,
        evidence_reference_valid=True,
        candidate_boundary_valid=True,
        assertion_pass_count=2,
        assertion_fail_count=0,
        blocking_failure_count=0,
        latency_ms=10,
        prompt_tokens=10,
        completion_tokens=4,
        total_tokens=14,
        estimated_cost=Decimal("0.01"),
    )
    assert result.model_dump(mode="json")["status"] == "passed"
    assert result.model_dump(mode="json")["node_name"] == "information_gap"


def test_input_fixture_must_be_relative() -> None:
    with pytest.raises(ValidationError):
        NodeBenchmarkCase(
            benchmark_case_id="bench-3",
            source_case_id="DEV-01",
            node_name=WorkflowNodeName.solution_recommendation,
            input_fixture=str(Path("/tmp/abs.json")),
            assertions=[
                BenchmarkAssertion(
                    assertion_id="a1",
                    assertion_type=BenchmarkAssertionType.json_parse_success,
                    location="root",
                    expected_value=True,
                    description="JSON parse must succeed.",
                    blocking=True,
                )
            ],
        )


def test_deepseek_thinking_config_requires_null_temperature() -> None:
    with pytest.raises(ValidationError):
        ModelBenchmarkConfig(
            config_id="cfg-ds",
            provider="deepseek",
            model="deepseek-v4-pro",
            tier=ModelTier.strong_reasoning,
            thinking_mode="enabled",
            reasoning_effort="high",
            temperature=0,
            max_tokens=8192,
            pricing_profile_id="pro-v4-2026-06",
            api_key_env="LLM_API_KEY",
        )


def test_old_replay_config_stays_backward_compatible() -> None:
    config = ModelBenchmarkConfig(
        config_id="cfg-replay",
        provider="replay",
        model="fixture-model",
        tier=ModelTier.fast,
        temperature=0,
        max_tokens=1024,
    )
    assert config.thinking_mode.value == "disabled"
    assert config.api_key_env is None


def test_manifest_rejects_unknown_cost_stop_with_stopped_by_budget_true() -> None:
    with pytest.raises(ValidationError):
        BenchmarkRunManifest(
            run_id="run-1",
            started_at="2026-06-26T00:00:00Z",
            completed_at="2026-06-26T00:00:01Z",
            execution_mode=BenchmarkExecutionMode.live,
            selected_case_count=1,
            selected_model_count=1,
            planned_run_count=1,
            completed_run_count=1,
            passed_count=0,
            failed_count=0,
            request_error_count=1,
            provider_names=["deepseek"],
            pricing_snapshot_ids=["pro-v4-2026-06"],
            unknown_cost_run_count=1,
            stopped_by_budget=True,
            stop_reason="unknown_cost_limit",
            output_directory="data/runtime/model_benchmark_runs/run-1",
        )
