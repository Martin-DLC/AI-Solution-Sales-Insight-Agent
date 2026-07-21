from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import Field, field_validator

from agent.governance.models import RuntimeEventStatus, TrajectoryEvent, TrajectoryEventType
from agent.observability.cost_tracker import CostTracker
from schemas.common_models import StrictBaseModel


class RunMetrics(StrictBaseModel):
    run_id: str
    trace_id: str
    final_status: str
    model_call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_model_cost: Decimal | None = None
    tool_call_count: int = 0
    tool_success_count: int = 0
    tool_failure_count: int = 0
    permission_check_count: int = 0
    permission_denied_count: int = 0
    approval_request_count: int = 0
    fallback_count: int = 0
    human_review_count: int = 0
    execution_steps: int = 0
    total_latency_ms: int = 0
    slowest_node_name: str | None = None
    slowest_node_latency_ms: int = 0
    task_success: bool = False
    created_at: datetime
    completed_at: datetime
    cost_is_estimated: bool = True

    @field_validator(
        "model_call_count",
        "input_tokens",
        "output_tokens",
        "tool_call_count",
        "tool_success_count",
        "tool_failure_count",
        "permission_check_count",
        "permission_denied_count",
        "approval_request_count",
        "fallback_count",
        "human_review_count",
        "execution_steps",
        "total_latency_ms",
        "slowest_node_latency_ms",
    )
    @classmethod
    def counts_must_not_be_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Run metric counts must not be negative.")
        return value


def build_run_metrics_from_events(
    events: list[TrajectoryEvent],
    *,
    final_status: str | None = None,
    provider_name: str = "deterministic",
    input_text: str | None = None,
    output_text: str | None = None,
    cost_tracker: CostTracker | None = None,
) -> RunMetrics:
    if not events:
        now = datetime.now(UTC)
        estimate = (cost_tracker or CostTracker()).estimate_model_cost(
            provider_name=provider_name,
            input_text=input_text,
            output_text=output_text,
        )
        return RunMetrics(
            run_id="unknown",
            trace_id="unknown",
            final_status=final_status or "unknown",
            input_tokens=estimate.input_tokens,
            output_tokens=estimate.output_tokens,
            estimated_model_cost=estimate.estimated_model_cost,
            created_at=now,
            completed_at=now,
        )

    tracker = cost_tracker or CostTracker()
    created_at = min(event.created_at for event in events)
    completed_at = max(event.created_at for event in events)
    total_latency_ms = max(0, int((completed_at - created_at).total_seconds() * 1000))
    model_call_count = sum(1 for event in events if event.event_type is TrajectoryEventType.generation_completed)
    tool_events = [
        event
        for event in events
        if event.tool_name
        and event.event_type
        in {
            TrajectoryEventType.skill_completed,
            TrajectoryEventType.skill_failed,
            TrajectoryEventType.retrieval_completed,
            TrajectoryEventType.shadow_retrieval_completed,
            TrajectoryEventType.provider_context_completed,
            TrajectoryEventType.permission_checked,
            TrajectoryEventType.permission_denied,
        }
    ]
    permission_check_count = sum(
        1
        for event in events
        if event.event_type in {TrajectoryEventType.permission_checked, TrajectoryEventType.permission_denied}
    )
    permission_denied_count = sum(1 for event in events if event.event_type is TrajectoryEventType.permission_denied)
    approval_request_count = sum(1 for event in events if event.event_type is TrajectoryEventType.approval_requested)
    fallback_count = sum(1 for event in events if event.fallback_triggered)
    human_review_count = sum(1 for event in events if event.human_review_required)
    estimate = tracker.estimate_model_cost(
        provider_name=provider_name,
        input_text=input_text,
        output_text=output_text,
    )
    resolved_final_status = final_status or _final_status_from_events(events)
    return RunMetrics(
        run_id=events[0].run_id,
        trace_id=events[0].trace_id,
        final_status=resolved_final_status,
        model_call_count=model_call_count,
        input_tokens=estimate.input_tokens,
        output_tokens=estimate.output_tokens,
        estimated_model_cost=estimate.estimated_model_cost,
        tool_call_count=len(tool_events),
        tool_success_count=sum(1 for event in tool_events if event.status is RuntimeEventStatus.success),
        tool_failure_count=sum(1 for event in tool_events if event.status is RuntimeEventStatus.failed),
        permission_check_count=permission_check_count,
        permission_denied_count=permission_denied_count,
        approval_request_count=approval_request_count,
        fallback_count=fallback_count,
        human_review_count=human_review_count,
        execution_steps=len(events),
        total_latency_ms=total_latency_ms,
        slowest_node_name=_slowest_node_name(events),
        slowest_node_latency_ms=0,
        task_success=resolved_final_status == "completed"
        and not any(event.event_type is TrajectoryEventType.stopped_by_policy for event in events),
        created_at=created_at,
        completed_at=completed_at,
        cost_is_estimated=True,
    )


def build_run_metrics(response: object) -> RunMetrics:
    runtime_trace = getattr(response, "runtime_trace", None)
    events = [] if runtime_trace is None else list(runtime_trace.events)
    final_status = None if runtime_trace is None else runtime_trace.summary.final_runtime_status
    output_text = " ".join(
        [
            str(getattr(response, "requirement_summary", "")),
            " ".join(getattr(response, "pain_points", []) or []),
            " ".join(getattr(response, "ai_opportunity_points", []) or []),
            str(getattr(response, "proposed_solution", "")),
        ]
    )
    return build_run_metrics_from_events(
        events,
        final_status=final_status,
        provider_name=str(getattr(response, "llm_mode", "deterministic")),
        input_text=str(getattr(response, "requirement_summary", "")),
        output_text=output_text,
    )


def _final_status_from_events(events: list[TrajectoryEvent]) -> str:
    if any(event.event_type is TrajectoryEventType.stopped_by_policy for event in events):
        return "stopped_by_policy"
    if any(event.event_type is TrajectoryEventType.run_failed for event in events):
        return "failed"
    if any(event.event_type is TrajectoryEventType.run_completed for event in events):
        return "completed"
    return "running"


def _slowest_node_name(events: list[TrajectoryEvent]) -> str | None:
    node_events = [event for event in events if event.node_name]
    if not node_events:
        return None
    return node_events[-1].node_name
