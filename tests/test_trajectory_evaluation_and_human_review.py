from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.governance.models import RuntimeEventStatus, RuntimeRiskLevel, TrajectoryEventType
from agent.governance.recorder import TrajectoryRecorder
from agent.models import SolutionInsightRequest
from agent.observability import build_observation_snapshot
from agent.solution_insight_service import SolutionInsightService
from evaluation.trajectory import (
    EvaluationGate,
    GateDecision,
    ReviewQueueItem,
    ReviewQueueManager,
    ReviewStatus,
    TrajectoryEvaluationResult,
    load_trajectory_rules,
)


def test_trajectory_evaluation_result_serializes() -> None:
    result = EvaluationGate().evaluate(_clean_events())

    dumped = result.model_dump(mode="json")

    assert dumped["evaluation_id"].startswith("trajectory-eval-")
    assert dumped["run_id"] == "run-clean"
    TrajectoryEvaluationResult.model_validate(dumped)


def test_rules_config_loads_expected_rules() -> None:
    rules = load_trajectory_rules()

    assert [rule.rule_id for rule in rules] == [
        "no_policy_stop",
        "no_permission_denied",
        "high_risk_requires_review",
        "fallback_requires_explanation",
        "human_review_event_consistency",
        "no_excessive_failures",
        "required_core_nodes_present",
        "shadow_does_not_override_formal",
    ]


def test_clean_completed_run_passes_evaluation_gate() -> None:
    result = EvaluationGate().evaluate(_clean_events())

    assert result.passed is True
    assert result.gate_decision is GateDecision.pass_


def test_stopped_by_policy_triggers_stop_decision() -> None:
    recorder = _clean_recorder()
    recorder.stop_by_policy(reason="step_limit_exceeded")

    result = EvaluationGate().evaluate(recorder.export_events())

    assert result.gate_decision is GateDecision.stop
    assert result.stop_recommended is True
    assert _failed_rule_ids(result) == ["no_policy_stop"]


def test_permission_denied_triggers_human_review() -> None:
    recorder = _clean_recorder(complete=False)
    recorder.record_event(
        event_type=TrajectoryEventType.permission_denied,
        tool_name="crm_write",
        permission_scope="crm:write",
        status=RuntimeEventStatus.failed,
        risk_level=RuntimeRiskLevel.medium,
    )
    _complete_core(recorder)

    result = EvaluationGate().evaluate(recorder.export_events())

    assert result.gate_decision is GateDecision.human_review
    assert "no_permission_denied" in _failed_rule_ids(result)


def test_high_risk_without_review_triggers_human_review() -> None:
    recorder = _clean_recorder(complete=False)
    recorder.record_event(
        event_type=TrajectoryEventType.approval_requested,
        tool_name="email_send",
        permission_scope="email:send",
        status=RuntimeEventStatus.success,
        risk_level=RuntimeRiskLevel.high,
        human_review_required=False,
    )
    _complete_core(recorder)

    result = EvaluationGate().evaluate(recorder.export_events())

    assert result.gate_decision is GateDecision.human_review
    assert "high_risk_requires_review" in _failed_rule_ids(result)


def test_fallback_without_explanation_triggers_human_review() -> None:
    recorder = _clean_recorder(complete=False)
    recorder.record_event(
        event_type=TrajectoryEventType.fallback_assessed,
        fallback_triggered=True,
        output_summary=None,
        status=RuntimeEventStatus.success,
    )
    recorder.record_event(event_type=TrajectoryEventType.generation_completed, status=RuntimeEventStatus.success)
    recorder.complete_run()

    result = EvaluationGate().evaluate(recorder.export_events())

    assert result.gate_decision is GateDecision.human_review
    assert "fallback_requires_explanation" in _failed_rule_ids(result)


def test_excessive_failures_trigger_retry() -> None:
    recorder = _clean_recorder(complete=False)
    for index in range(4):
        recorder.record_event(
            event_type=TrajectoryEventType.skill_failed,
            node_name=f"node_{index}",
            status=RuntimeEventStatus.failed,
        )
    _complete_core(recorder)

    result = EvaluationGate().evaluate(recorder.export_events())

    assert result.gate_decision in {GateDecision.retry, GateDecision.stop}
    assert "no_excessive_failures" in _failed_rule_ids(result)


def test_required_core_nodes_missing_triggers_human_review() -> None:
    recorder = TrajectoryRecorder()
    recorder.start_run(run_id="run-missing", trace_id="trace-missing")
    recorder.complete_run()

    result = EvaluationGate().evaluate(recorder.export_events())

    assert result.gate_decision is GateDecision.human_review
    assert "required_core_nodes_present" in _failed_rule_ids(result)


def test_review_queue_item_defaults_to_pending() -> None:
    item = ReviewQueueItem(
        run_id="run-1",
        trace_id="trace-1",
        evaluation_id="eval-1",
        trigger_reason="needs review",
    )

    assert item.status is ReviewStatus.pending
    assert item.reviewed_at is None


def test_review_queue_status_transitions() -> None:
    manager = ReviewQueueManager()
    item = manager.create_item(
        run_id="run-1",
        trace_id="trace-1",
        evaluation_id="eval-1",
        trigger_reason="needs review",
    )

    in_review = manager.mark_in_review(item.review_item_id, assigned_to="local_reviewer")
    assert in_review.status is ReviewStatus.in_review
    approved = manager.approve(item.review_item_id, reviewer_notes="Looks acceptable.")
    assert approved.status is ReviewStatus.approved
    assert approved.reviewed_at is not None

    rejected_item = manager.create_item(
        run_id="run-2",
        trace_id="trace-2",
        evaluation_id="eval-2",
        trigger_reason="needs review",
    )
    assert manager.reject(rejected_item.review_item_id, reviewer_notes="Reject.").status is ReviewStatus.rejected

    expired_item = manager.create_item(
        run_id="run-3",
        trace_id="trace-3",
        evaluation_id="eval-3",
        trigger_reason="needs review",
    )
    assert manager.expire(expired_item.review_item_id, reviewer_notes="Expired.").status is ReviewStatus.expired


def test_pending_review_is_not_completed() -> None:
    item = ReviewQueueManager().create_item(
        run_id="run-1",
        trace_id="trace-1",
        evaluation_id="eval-1",
        trigger_reason="needs review",
    )

    assert item.status is ReviewStatus.pending
    assert item.decision is None
    assert item.reviewed_at is None


def test_terminal_review_cannot_transition_again() -> None:
    manager = ReviewQueueManager()
    item = manager.create_item(
        run_id="run-1",
        trace_id="trace-1",
        evaluation_id="eval-1",
        trigger_reason="needs review",
    )
    manager.approve(item.review_item_id)

    with pytest.raises(ValueError):
        manager.reject(item.review_item_id, reviewer_notes="Too late.")


def test_service_generates_trajectory_evaluation_summary_without_changing_output() -> None:
    service = SolutionInsightService.from_defaults(llm_mode="deterministic")
    request = SolutionInsightRequest(
        user_query="一家中型 SaaS 公司想提升销售线索转化和客户成功效率",
        company_id="demo_saas_001",
        industry="SaaS",
        llm_mode="deterministic",
    )

    response = service.generate_insight(request)

    assert response.requirement_summary
    assert response.trajectory_evaluation["evaluation_id"].startswith("trajectory-eval-")
    assert response.evaluation_gate_summary["gate_decision"] in {"pass", "human_review"}
    assert response.review_queue_item is not None
    assert response.review_queue_item["status"] == "pending"
    assert response.review_queue_item["decision"] is None


def test_observability_snapshot_includes_trajectory_evaluation_summary() -> None:
    response = SolutionInsightService.from_defaults(llm_mode="deterministic").generate_insight(
        SolutionInsightRequest(
            user_query="一家中型 SaaS 公司想提升销售线索转化和客户成功效率",
            company_id="demo_saas_001",
            industry="SaaS",
            llm_mode="deterministic",
        )
    )

    snapshot = build_observation_snapshot(response)

    assert snapshot.trajectory_evaluation.gate_decision in {"pass", "human_review"}
    assert snapshot.trajectory_evaluation.review_queue_status == "pending"


def test_human_eval_summary_artifact_remains_not_started() -> None:
    payload = json.loads(Path("data/evaluation/human/solution_insight_human_eval_summary.v1.json").read_text(encoding="utf-8"))

    assert payload["human_review_status"] == "not_started"


def _clean_recorder(*, complete: bool = True) -> TrajectoryRecorder:
    recorder = TrajectoryRecorder()
    recorder.start_run(run_id="run-clean", trace_id="trace-clean")
    recorder.record_event(event_type=TrajectoryEventType.fallback_assessed, output_summary="fallback_triggered=False", status=RuntimeEventStatus.success)
    recorder.record_event(event_type=TrajectoryEventType.generation_completed, status=RuntimeEventStatus.success)
    if complete:
        recorder.complete_run()
    return recorder


def _complete_core(recorder: TrajectoryRecorder) -> None:
    recorder.record_event(event_type=TrajectoryEventType.fallback_assessed, output_summary="fallback_triggered=False", status=RuntimeEventStatus.success)
    recorder.record_event(event_type=TrajectoryEventType.generation_completed, status=RuntimeEventStatus.success)
    recorder.complete_run()


def _clean_events():
    return _clean_recorder().export_events()


def _failed_rule_ids(result):
    return [rule.rule_id for rule in result.rule_results if not rule.passed]
