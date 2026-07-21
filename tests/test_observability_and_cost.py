from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from agent.governance import ApprovalManager, RuntimeRiskLevel, TrajectoryEventType, TrajectoryRecorder
from agent.models import SolutionInsightRequest
from agent.observability import build_observation_snapshot
from agent.observability.cost_tracker import CostTracker, load_model_costs
from agent.observability.metrics import RunMetrics, build_run_metrics, build_run_metrics_from_events
from agent.observability.run_summary import render_cost_summary_report
from agent.solution_insight_service import SolutionInsightService
from scripts import generate_run_summary_report as report_script


def test_model_costs_yaml_loads_expected_providers() -> None:
    policies = load_model_costs()

    assert set(policies) == {"deterministic", "deepseek", "qwen", "glm", "mock"}


def test_deterministic_cost_is_estimated_zero() -> None:
    estimate = CostTracker().estimate_from_usage(
        provider_name="deterministic",
        input_tokens=100,
        output_tokens=200,
    )

    assert estimate.estimated_model_cost == Decimal("0.000000")
    assert estimate.cost_is_estimated is True


def test_unknown_provider_does_not_crash() -> None:
    estimate = CostTracker().estimate_from_usage(
        provider_name="unknown_provider",
        input_tokens=100,
        output_tokens=200,
    )

    assert estimate.estimated_model_cost is None
    assert estimate.warnings == ["unknown_provider:unknown_provider"]


def test_estimate_token_count_is_stable() -> None:
    tracker = CostTracker()

    assert tracker.estimate_token_count("hello world") == tracker.estimate_token_count("hello   world")
    assert tracker.estimate_token_count("一家中型 SaaS 公司") > 0


def test_estimate_from_usage_calculates_mock_cost() -> None:
    policies = load_model_costs()
    mock = policies["mock"].model_copy(
        update={
            "input_cost_per_1k_tokens": Decimal("1"),
            "output_cost_per_1k_tokens": Decimal("2"),
        }
    )
    estimate = CostTracker(policies={"mock": mock}).estimate_from_usage(
        provider_name="mock",
        input_tokens=1000,
        output_tokens=2000,
    )

    assert estimate.estimated_model_cost == Decimal("5.000000")


def test_run_metrics_serializes() -> None:
    response = _response()

    metrics = build_run_metrics(response)
    dumped = metrics.model_dump(mode="json")

    assert dumped["run_id"] == response.governance_trace.run_id
    assert dumped["cost_is_estimated"] is True
    RunMetrics.model_validate(dumped)


def test_build_metrics_from_trajectory_events_counts_governance_events() -> None:
    recorder = TrajectoryRecorder()
    recorder.start_run(run_id="run-1", trace_id="trace-1")
    recorder.record_event(
        event_type=TrajectoryEventType.permission_checked,
        tool_name="crm_read",
        permission_scope="crm:read",
        status="success",
    )
    recorder.record_event(
        event_type=TrajectoryEventType.permission_denied,
        tool_name="crm_write",
        permission_scope="crm:write",
        risk_level=RuntimeRiskLevel.high,
        status="failed",
    )
    manager = ApprovalManager(recorder=recorder)
    manager.create_request(
        run_id="run-1",
        trace_id="trace-1",
        request_id="request-1",
        tool_name="email_send",
        action="send",
        requested_scope="email:send",
        risk_level=RuntimeRiskLevel.high,
        reason="Needs approval.",
    )
    recorder.record_fallback_event(fallback_triggered=True, fallback_reasons=["no_evidence_found"])
    recorder.record_human_review_event(reasons=["no_evidence_found"])
    recorder.complete_run()

    metrics = build_run_metrics_from_events(
        recorder.export_events(),
        final_status=recorder.summary().final_runtime_status,
    )

    assert metrics.permission_check_count == 2
    assert metrics.permission_denied_count == 1
    assert metrics.approval_request_count == 1
    assert metrics.fallback_count == 1
    assert metrics.human_review_count >= 2
    assert metrics.task_success is True


def test_generate_run_summary_report_write_and_check(tmp_path: Path, monkeypatch) -> None:
    summary_path = tmp_path / "latest_run_summary.json"
    report_path = tmp_path / "latest_cost_summary.md"
    monkeypatch.setattr(report_script, "SUMMARY_PATH", summary_path)
    monkeypatch.setattr(report_script, "COST_REPORT_PATH", report_path)

    assert report_script.main(["--write"]) == 0
    assert summary_path.exists()
    assert report_path.exists()
    assert report_script.main(["--check"]) == 0

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")
    assert payload["cost_is_estimated"] is True
    assert "This report is not a production billing report." in report


def test_report_does_not_include_sensitive_fragments() -> None:
    report = render_cost_summary_report(build_run_metrics(_response()))
    lowered = report.casefold()

    assert "api_key" not in lowered
    assert "traceback" not in lowered
    assert "benchmark gold" not in lowered
    assert "hidden reference pack" not in lowered


def test_service_response_and_observability_snapshot_include_metrics() -> None:
    response = _response()
    snapshot = build_observation_snapshot(response)

    assert response.run_metrics["cost_is_estimated"] is True
    assert snapshot.metrics.cost_is_estimated is True
    assert snapshot.metrics.permission_check_count >= 1
    assert snapshot.metrics.fallback_count >= 1


def _response():
    service = SolutionInsightService.from_defaults(
        enable_shadow_retrieval=True,
        llm_mode="deterministic",
    )
    return service.generate_insight(
        SolutionInsightRequest(
            user_query="一家中型 SaaS 公司想提升销售线索转化和客户成功效率",
            industry="SaaS",
            company_size="中型",
            company_id="demo_saas_001",
            enable_shadow_retrieval=True,
            llm_mode="deterministic",
        )
    )
