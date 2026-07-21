from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import Field, field_validator, model_validator

from agent.governance.models import RuntimeRiskLevel
from schemas.common_models import StrictBaseModel


_FORBIDDEN_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_-]+|traceback\s+\(most recent call last\)|benchmark gold|hidden reference pack)",
    re.IGNORECASE,
)


class RuleSeverity(str, Enum):
    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"


class GateDecision(str, Enum):
    pass_ = "pass"
    retry = "retry"
    human_review = "human_review"
    stop = "stop"


class TrajectoryRuleResult(StrictBaseModel):
    rule_id: str
    rule_name: str
    passed: bool
    severity: RuleSeverity
    reason: str
    evidence_event_ids: list[str] = Field(default_factory=list)
    recommended_action: GateDecision

    @field_validator("reason")
    @classmethod
    def reason_must_be_safe_summary(cls, value: str) -> str:
        sanitized = " ".join(value.split())[:500]
        if _FORBIDDEN_PATTERN.search(sanitized):
            raise ValueError("Rule result reason contains forbidden sensitive content.")
        return sanitized


class TrajectoryEvaluationResult(StrictBaseModel):
    evaluation_id: str = Field(default_factory=lambda: f"trajectory-eval-{uuid.uuid4().hex}")
    run_id: str
    trace_id: str
    final_status: str
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    rule_results: list[TrajectoryRuleResult]
    passed: bool
    gate_decision: GateDecision
    human_review_required: bool
    human_review_reasons: list[str] = Field(default_factory=list)
    retry_recommended: bool = False
    stop_recommended: bool = False
    risk_level: RuntimeRiskLevel = RuntimeRiskLevel.unknown
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evaluation_safety(self) -> "TrajectoryEvaluationResult":
        dumped = str(self.model_dump(mode="json"))
        if _FORBIDDEN_PATTERN.search(dumped):
            raise ValueError("Trajectory evaluation must not contain sensitive content.")
        return self
