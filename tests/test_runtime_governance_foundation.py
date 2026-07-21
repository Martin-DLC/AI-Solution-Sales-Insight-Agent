from __future__ import annotations

from agent.governance import RuntimeLimits, TrajectoryRecorder
from agent.governance.models import RuntimeEventStatus, TrajectoryEvent, TrajectoryEventType
from agent.models import SolutionInsightRequest
from agent.observability import build_observation_snapshot
from agent.solution_insight_service import SolutionInsightService


def test_trajectory_event_serializes_and_sanitizes_sensitive_summary() -> None:
    event = TrajectoryEvent(
        run_id="run-test",
        trace_id="trace-test",
        step_index=1,
        event_type=TrajectoryEventType.run_started,
        input_summary="sk-secret Traceback (most recent call last) benchmark gold",
        status=RuntimeEventStatus.success,
    )

    dumped = event.model_dump(mode="json")

    assert dumped["run_id"] == "run-test"
    serialized = event.model_dump_json().casefold()
    assert "sk-secret" not in serialized
    assert "traceback (most recent call last)" not in serialized
    assert "benchmark gold" not in serialized


def test_start_run_generates_run_id_and_trace_id() -> None:
    recorder = TrajectoryRecorder()

    state = recorder.start_run(input_summary="query_length=10")

    assert state.run_id.startswith("run-")
    assert state.trace_id == state.run_id
    assert recorder.summary().final_runtime_status == "running"


def test_record_event_step_index_is_monotonic() -> None:
    recorder = TrajectoryRecorder()
    recorder.start_run()
    recorder.record_event(event_type=TrajectoryEventType.retrieval_completed, status=RuntimeEventStatus.success)
    recorder.record_event(event_type=TrajectoryEventType.fallback_assessed, status=RuntimeEventStatus.success)

    assert [event.step_index for event in recorder.export_events()] == [1, 2, 3]


def test_recorder_summary_contains_event_count_and_final_status() -> None:
    recorder = TrajectoryRecorder()
    recorder.start_run()
    recorder.complete_run(output_summary="done")

    summary = recorder.summary()

    assert summary.event_count == 2
    assert summary.final_runtime_status == "completed"
    assert summary.stopped_by_policy is False


def test_max_execution_steps_triggers_stopped_by_policy() -> None:
    recorder = TrajectoryRecorder(limits=RuntimeLimits(max_execution_steps=3))
    recorder.start_run()
    recorder.record_event(event_type=TrajectoryEventType.skill_started, status=RuntimeEventStatus.success)
    recorder.record_event(event_type=TrajectoryEventType.skill_completed, status=RuntimeEventStatus.success)

    summary = recorder.summary()

    assert summary.stopped_by_policy is True
    assert summary.final_runtime_status == "stopped_by_policy"
    assert summary.stop_reason == "step_limit_exceeded"
    assert recorder.export_events()[-1].event_type is TrajectoryEventType.stopped_by_policy


def test_max_consecutive_failures_triggers_stopped_by_policy() -> None:
    recorder = TrajectoryRecorder(limits=RuntimeLimits(max_consecutive_failures=2))
    recorder.start_run()
    recorder.record_event(event_type=TrajectoryEventType.skill_failed, status=RuntimeEventStatus.failed)
    recorder.record_event(event_type=TrajectoryEventType.retrieval_completed, status=RuntimeEventStatus.failed)

    summary = recorder.summary()

    assert summary.stopped_by_policy is True
    assert summary.stop_reason == "consecutive_failure_limit_exceeded"
    assert recorder.export_events()[-1].stop_reason == "consecutive_failure_limit_exceeded"


def test_service_response_includes_governance_trace_without_policy_stop() -> None:
    service = SolutionInsightService.from_defaults(llm_mode="deterministic")

    response = service.generate_insight(
        SolutionInsightRequest(
            user_query="一家中型 SaaS 公司想提升销售线索转化和客户成功效率",
            industry="SaaS",
            llm_mode="deterministic",
        )
    )

    assert response.runtime_trace is not None
    assert response.governance_trace is not None
    assert response.governance_trace.event_count >= 10
    assert response.governance_trace.final_runtime_status == "completed"
    assert response.governance_trace.stopped_by_policy is False
    assert response.trajectory_summary["run_id"] == response.governance_trace.run_id


def test_service_records_fallback_and_human_confirmation_in_summary() -> None:
    service = SolutionInsightService.from_defaults(llm_mode="deterministic")

    response = service.generate_insight(
        SolutionInsightRequest(user_query="希望做一个企业知识问答助手", llm_mode="deterministic")
    )

    assert response.fallback_recommended is True
    assert response.human_confirmation_required is True
    assert response.governance_trace is not None
    assert response.governance_trace.fallback_triggered is True
    assert response.governance_trace.human_review_required is True
    assert any(
        event.event_type is TrajectoryEventType.human_review_required
        for event in response.runtime_trace.events  # type: ignore[union-attr]
    )


def test_governance_events_do_not_record_api_key_traceback_or_gold() -> None:
    recorder = TrajectoryRecorder()
    recorder.start_run(input_summary="sk-test Traceback (most recent call last) hidden reference pack")

    dumped = recorder.runtime_trace().model_dump_json().casefold()

    assert "sk-test" not in dumped
    assert "traceback (most recent call last)" not in dumped
    assert "hidden reference pack" not in dumped
    assert "benchmark gold" not in dumped


def test_observability_snapshot_includes_governance_summary() -> None:
    service = SolutionInsightService.from_defaults(llm_mode="deterministic")
    response = service.generate_insight(
        SolutionInsightRequest(
            user_query="一家中型 SaaS 公司想提升销售线索转化和客户成功效率",
            company_id="demo_saas_001",
            enable_shadow_retrieval=True,
            llm_mode="deterministic",
        )
    )

    snapshot = build_observation_snapshot(response)

    assert snapshot.governance.run_id == response.governance_trace.run_id
    assert snapshot.governance.event_count == response.governance_trace.event_count
    assert snapshot.governance.final_runtime_status == "completed"
    assert snapshot.governance.stopped_by_policy is False
