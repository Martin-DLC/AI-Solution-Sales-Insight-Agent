from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import Field

from schemas.common_models import StrictBaseModel


class RuntimeStatus(str, Enum):
    created = "created"
    running = "running"
    completed = "completed"
    failed = "failed"
    stopped_by_policy = "stopped_by_policy"
    waiting_for_human = "waiting_for_human"
    paused = "paused"
    resumed = "resumed"
    cancelled = "cancelled"


_ALLOWED_TRANSITIONS: dict[RuntimeStatus, set[RuntimeStatus]] = {
    RuntimeStatus.created: {RuntimeStatus.running, RuntimeStatus.failed},
    RuntimeStatus.running: {
        RuntimeStatus.completed,
        RuntimeStatus.failed,
        RuntimeStatus.stopped_by_policy,
        RuntimeStatus.waiting_for_human,
        RuntimeStatus.paused,
    },
    RuntimeStatus.waiting_for_human: {
        RuntimeStatus.completed,
        RuntimeStatus.failed,
        RuntimeStatus.stopped_by_policy,
        RuntimeStatus.running,
    },
    RuntimeStatus.paused: {RuntimeStatus.resumed, RuntimeStatus.cancelled, RuntimeStatus.failed},
    RuntimeStatus.resumed: {RuntimeStatus.running, RuntimeStatus.completed, RuntimeStatus.failed},
    RuntimeStatus.completed: set(),
    RuntimeStatus.failed: set(),
    RuntimeStatus.stopped_by_policy: set(),
    RuntimeStatus.cancelled: set(),
}


class RuntimeState(StrictBaseModel):
    run_id: str
    trace_id: str
    status: RuntimeStatus = RuntimeStatus.created
    human_review_required: bool = False
    stop_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def transition_to(self, next_status: RuntimeStatus, *, stop_reason: str | None = None) -> None:
        allowed = _ALLOWED_TRANSITIONS[self.status]
        if next_status not in allowed and next_status is not self.status:
            raise ValueError(f"Invalid runtime status transition: {self.status.value} -> {next_status.value}")
        self.status = next_status
        if stop_reason is not None:
            self.stop_reason = stop_reason
        self.updated_at = datetime.now(UTC)

    def mark_human_review_required(self) -> None:
        self.human_review_required = True
        self.updated_at = datetime.now(UTC)
