from __future__ import annotations

import secrets
from typing import Any

from agent.governance.models import (
    GovernanceTraceSummary,
    RuntimeEventStatus,
    RuntimeRiskLevel,
    RuntimeTrace,
    TrajectoryEvent,
    TrajectoryEventType,
    summarize_value,
)
from agent.governance.runtime_limits import RuntimeLimits, load_runtime_limits
from agent.governance.runtime_state import RuntimeState, RuntimeStatus


class TrajectoryRecorder:
    def __init__(
        self,
        *,
        agent_name: str = "solution_insight_agent",
        limits: RuntimeLimits | None = None,
    ) -> None:
        self.agent_name = agent_name
        self.limits = limits or load_runtime_limits()
        self.state: RuntimeState | None = None
        self._events: list[TrajectoryEvent] = []
        self._next_step_index = 1
        self._consecutive_failures = 0

    @property
    def run_id(self) -> str | None:
        return None if self.state is None else self.state.run_id

    @property
    def trace_id(self) -> str | None:
        return None if self.state is None else self.state.trace_id

    def start_run(
        self,
        *,
        task_id: str | None = None,
        input_summary: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
    ) -> RuntimeState:
        resolved_run_id = run_id or f"run-{secrets.token_hex(8)}"
        resolved_trace_id = trace_id or resolved_run_id
        self.state = RuntimeState(run_id=resolved_run_id, trace_id=resolved_trace_id)
        self.state.transition_to(RuntimeStatus.running)
        self.record_event(
            event_type=TrajectoryEventType.run_started,
            task_id=task_id,
            input_summary=input_summary,
            status=RuntimeEventStatus.success,
            risk_level=RuntimeRiskLevel.low,
        )
        return self.state

    def record_event(
        self,
        *,
        event_type: TrajectoryEventType | str,
        task_id: str | None = None,
        node_name: str | None = None,
        input_summary: str | None = None,
        output_summary: str | None = None,
        tool_name: str | None = None,
        permission_scope: str | None = None,
        risk_level: RuntimeRiskLevel | str = RuntimeRiskLevel.unknown,
        status: RuntimeEventStatus | str = RuntimeEventStatus.success,
        error_type: str | None = None,
        fallback_triggered: bool = False,
        human_review_required: bool = False,
        stop_reason: str | None = None,
    ) -> TrajectoryEvent:
        self._ensure_started()
        assert self.state is not None
        event = TrajectoryEvent(
            run_id=self.state.run_id,
            trace_id=self.state.trace_id,
            task_id=task_id,
            node_name=node_name,
            agent_name=self.agent_name,
            step_index=self._next_step_index,
            event_type=TrajectoryEventType(event_type),
            input_summary=input_summary,
            output_summary=output_summary,
            tool_name=tool_name,
            permission_scope=permission_scope,
            risk_level=RuntimeRiskLevel(risk_level),
            status=RuntimeEventStatus(status),
            error_type=error_type,
            fallback_triggered=fallback_triggered,
            human_review_required=human_review_required,
            stop_reason=stop_reason,
        )
        self._events.append(event)
        self._next_step_index += 1
        self._update_counters(event)
        self._check_limits_after_event()
        return event

    def record_skill_event(
        self,
        *,
        skill_name: str,
        phase: str,
        status: str = "success",
        input_summary: str | None = None,
        output_summary: str | None = None,
        error_type: str | None = None,
    ) -> TrajectoryEvent:
        if phase == "started":
            event_type = TrajectoryEventType.skill_started
            event_status = RuntimeEventStatus.success
        elif status == "failed":
            event_type = TrajectoryEventType.skill_failed
            event_status = RuntimeEventStatus.failed
        else:
            event_type = TrajectoryEventType.skill_completed
            event_status = RuntimeEventStatus(status)
        return self.record_event(
            event_type=event_type,
            node_name=skill_name,
            tool_name=skill_name,
            input_summary=input_summary,
            output_summary=output_summary,
            status=event_status,
            error_type=error_type,
            risk_level=RuntimeRiskLevel.low,
        )

    def record_fallback_event(
        self,
        *,
        fallback_triggered: bool,
        fallback_reasons: list[str],
    ) -> TrajectoryEvent:
        return self.record_event(
            event_type=TrajectoryEventType.fallback_assessed,
            output_summary=summarize_value(
                {
                    "fallback_triggered": fallback_triggered,
                    "fallback_reasons": fallback_reasons,
                }
            ),
            fallback_triggered=fallback_triggered,
            human_review_required=fallback_triggered,
            status=RuntimeEventStatus.success,
            risk_level=RuntimeRiskLevel.medium if fallback_triggered else RuntimeRiskLevel.low,
        )

    def record_human_review_event(self, *, reasons: list[str]) -> TrajectoryEvent:
        if self.state is not None:
            self.state.mark_human_review_required()
        return self.record_event(
            event_type=TrajectoryEventType.human_review_required,
            output_summary=summarize_value({"reasons": reasons}),
            human_review_required=True,
            status=RuntimeEventStatus.success,
            risk_level=RuntimeRiskLevel.medium,
        )

    def stop_by_policy(self, *, reason: str) -> TrajectoryEvent:
        self._ensure_started()
        assert self.state is not None
        if self.state.status is not RuntimeStatus.stopped_by_policy:
            if self.state.status not in {
                RuntimeStatus.completed,
                RuntimeStatus.failed,
                RuntimeStatus.stopped_by_policy,
            }:
                self.state.transition_to(RuntimeStatus.stopped_by_policy, stop_reason=reason)
            else:
                self.state.stop_reason = reason
        return self._append_policy_stop_event(reason)

    def complete_run(self, *, output_summary: str | None = None) -> TrajectoryEvent:
        self._ensure_started()
        assert self.state is not None
        if self.state.status is not RuntimeStatus.stopped_by_policy:
            self.state.transition_to(RuntimeStatus.completed)
            return self.record_event(
                event_type=TrajectoryEventType.run_completed,
                output_summary=output_summary,
                status=RuntimeEventStatus.success,
                risk_level=RuntimeRiskLevel.low,
            )
        return self._events[-1]

    def fail_run(self, *, error_type: str, output_summary: str | None = None) -> TrajectoryEvent:
        self._ensure_started()
        assert self.state is not None
        if self.state.status is not RuntimeStatus.stopped_by_policy:
            self.state.transition_to(RuntimeStatus.failed)
            return self.record_event(
                event_type=TrajectoryEventType.run_failed,
                output_summary=output_summary,
                status=RuntimeEventStatus.failed,
                error_type=error_type,
                risk_level=RuntimeRiskLevel.medium,
            )
        return self._events[-1]

    def export_events(self) -> list[TrajectoryEvent]:
        return list(self._events)

    def summary(self) -> GovernanceTraceSummary:
        self._ensure_started()
        assert self.state is not None
        stopped = self.state.status is RuntimeStatus.stopped_by_policy
        return GovernanceTraceSummary(
            run_id=self.state.run_id,
            trace_id=self.state.trace_id,
            event_count=len(self._events),
            final_runtime_status=self.state.status.value,
            stopped_by_policy=stopped,
            stop_reason=self.state.stop_reason,
            human_review_required=self.state.human_review_required
            or any(event.human_review_required for event in self._events),
            fallback_triggered=any(event.fallback_triggered for event in self._events),
            failed_event_count=sum(1 for event in self._events if event.status is RuntimeEventStatus.failed),
        )

    def runtime_trace(self) -> RuntimeTrace:
        return RuntimeTrace(
            run_id=self.summary().run_id,
            trace_id=self.summary().trace_id,
            events=self.export_events(),
            summary=self.summary(),
        )

    def _ensure_started(self) -> None:
        if self.state is None:
            raise RuntimeError("TrajectoryRecorder.start_run must be called before recording events.")

    def _update_counters(self, event: TrajectoryEvent) -> None:
        if event.status is RuntimeEventStatus.failed:
            self._consecutive_failures += 1
        elif event.event_type is not TrajectoryEventType.stopped_by_policy:
            self._consecutive_failures = 0

    def _check_limits_after_event(self) -> None:
        if self.state is None or self.state.status is RuntimeStatus.stopped_by_policy:
            return
        if len(self._events) >= self.limits.max_execution_steps:
            self.state.transition_to(RuntimeStatus.stopped_by_policy, stop_reason="step_limit_exceeded")
            self._append_policy_stop_event("step_limit_exceeded")
            return
        if self._consecutive_failures >= self.limits.max_consecutive_failures:
            self.state.transition_to(
                RuntimeStatus.stopped_by_policy,
                stop_reason="consecutive_failure_limit_exceeded",
            )
            self._append_policy_stop_event("consecutive_failure_limit_exceeded")

    def _append_policy_stop_event(self, reason: str) -> TrajectoryEvent:
        assert self.state is not None
        if self._events and self._events[-1].event_type is TrajectoryEventType.stopped_by_policy:
            return self._events[-1]
        event = TrajectoryEvent(
            run_id=self.state.run_id,
            trace_id=self.state.trace_id,
            agent_name=self.agent_name,
            step_index=self._next_step_index,
            event_type=TrajectoryEventType.stopped_by_policy,
            output_summary=f"Runtime stopped by policy: {reason}",
            risk_level=RuntimeRiskLevel.medium,
            status=RuntimeEventStatus.stopped,
            stop_reason=reason,
        )
        self._events.append(event)
        self._next_step_index += 1
        return event
