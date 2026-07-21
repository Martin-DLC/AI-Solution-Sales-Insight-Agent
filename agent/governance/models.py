from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import Field, field_validator, model_validator

from schemas.common_models import StrictBaseModel


_API_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]+", re.IGNORECASE)
_TRACEBACK_PATTERN = re.compile(r"traceback\s+\(most recent call last\)", re.IGNORECASE)
_SENSITIVE_WORD_PATTERN = re.compile(r"(benchmark gold|gold answer|hidden reference pack)", re.IGNORECASE)


class TrajectoryEventType(str, Enum):
    run_started = "run_started"
    run_completed = "run_completed"
    run_failed = "run_failed"
    skill_started = "skill_started"
    skill_completed = "skill_completed"
    skill_failed = "skill_failed"
    retrieval_started = "retrieval_started"
    retrieval_completed = "retrieval_completed"
    shadow_retrieval_completed = "shadow_retrieval_completed"
    provider_context_completed = "provider_context_completed"
    fallback_assessed = "fallback_assessed"
    human_review_required = "human_review_required"
    generation_completed = "generation_completed"
    stopped_by_policy = "stopped_by_policy"
    permission_checked = "permission_checked"
    permission_denied = "permission_denied"
    approval_requested = "approval_requested"
    approval_approved = "approval_approved"
    approval_rejected = "approval_rejected"
    approval_expired = "approval_expired"
    recovery_decision_made = "recovery_decision_made"
    retry_recommended = "retry_recommended"
    fallback_selected = "fallback_selected"
    compensation_planned = "compensation_planned"
    model_provider_selected = "model_provider_selected"
    model_fallback_selected = "model_fallback_selected"


class RuntimeRiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    unknown = "unknown"


class RuntimeEventStatus(str, Enum):
    success = "success"
    skipped = "skipped"
    failed = "failed"
    stopped = "stopped"


class TrajectoryEvent(StrictBaseModel):
    event_id: str = Field(default_factory=lambda: f"event-{uuid.uuid4().hex}")
    run_id: str
    trace_id: str
    task_id: str | None = None
    node_name: str | None = None
    agent_name: str = "solution_insight_agent"
    step_index: int
    event_type: TrajectoryEventType
    input_summary: str | None = None
    output_summary: str | None = None
    tool_name: str | None = None
    permission_scope: str | None = None
    risk_level: RuntimeRiskLevel = RuntimeRiskLevel.unknown
    status: RuntimeEventStatus
    error_type: str | None = None
    fallback_triggered: bool = False
    human_review_required: bool = False
    stop_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("step_index")
    @classmethod
    def step_index_must_start_at_one(cls, value: int) -> int:
        if value < 1:
            raise ValueError("step_index must be greater than or equal to 1.")
        return value

    @field_validator(
        "input_summary",
        "output_summary",
        "tool_name",
        "permission_scope",
        "error_type",
        "stop_reason",
    )
    @classmethod
    def sanitize_text_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        sanitized = _sanitize_text(value, limit=500)
        return sanitized or None

    @model_validator(mode="after")
    def validate_event_safety(self) -> "TrajectoryEvent":
        dumped = str(self.model_dump(mode="json"))
        lowered = dumped.casefold()
        if "traceback (most recent call last)" in lowered:
            raise ValueError("Trajectory events must not contain tracebacks.")
        if "hidden reference pack" in lowered or "benchmark gold" in lowered:
            raise ValueError("Trajectory events must not contain benchmark gold data.")
        if _API_KEY_PATTERN.search(dumped):
            raise ValueError("Trajectory events must not contain API keys.")
        return self


class GovernanceTraceSummary(StrictBaseModel):
    run_id: str
    trace_id: str
    event_count: int
    final_runtime_status: str
    stopped_by_policy: bool = False
    stop_reason: str | None = None
    human_review_required: bool = False
    fallback_triggered: bool = False
    failed_event_count: int = 0


class RuntimeTrace(StrictBaseModel):
    run_id: str
    trace_id: str
    events: list[TrajectoryEvent] = Field(default_factory=list)
    summary: GovernanceTraceSummary


def summarize_value(value: object, *, limit: int = 240) -> str:
    if value is None:
        return "none"
    if isinstance(value, dict):
        fragments = [f"{key}={_short_repr(item)}" for key, item in list(value.items())[:8]]
        return _sanitize_text("; ".join(fragments), limit=limit)
    if isinstance(value, list):
        return _sanitize_text(f"list_count={len(value)}", limit=limit)
    return _sanitize_text(str(value), limit=limit)


def _short_repr(value: object) -> str:
    if isinstance(value, list):
        return f"list_count:{len(value)}"
    if isinstance(value, dict):
        return f"dict_keys:{','.join(list(value)[:5])}"
    return str(value)[:80]


def _sanitize_text(value: str, *, limit: int) -> str:
    normalized = " ".join(str(value).split())
    normalized = _API_KEY_PATTERN.sub("[REDACTED_API_KEY]", normalized)
    normalized = _TRACEBACK_PATTERN.sub("[REDACTED_TRACEBACK]", normalized)
    normalized = _SENSITIVE_WORD_PATTERN.sub("[REDACTED_BENCHMARK_REFERENCE]", normalized)
    return normalized[:limit]
