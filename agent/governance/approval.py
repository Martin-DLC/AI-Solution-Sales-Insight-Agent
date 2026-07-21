from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import Field, model_validator

from agent.governance.models import RuntimeEventStatus, RuntimeRiskLevel, TrajectoryEventType
from schemas.common_models import StrictBaseModel


class ApprovalStatus(str, Enum):
    not_required = "not_required"
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"


_TERMINAL_STATUSES = {
    ApprovalStatus.approved,
    ApprovalStatus.rejected,
    ApprovalStatus.expired,
    ApprovalStatus.not_required,
}


class ApprovalRequest(StrictBaseModel):
    approval_id: str = Field(default_factory=lambda: f"approval-{uuid.uuid4().hex}")
    run_id: str
    trace_id: str
    request_id: str | None = None
    tool_name: str
    action: str
    requested_scope: str
    risk_level: RuntimeRiskLevel
    reason: str
    status: ApprovalStatus = ApprovalStatus.pending
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None
    decided_by: str | None = None
    decision_reason: str | None = None

    @model_validator(mode="after")
    def validate_decision_fields(self) -> "ApprovalRequest":
        if self.status is ApprovalStatus.pending:
            if self.decided_at is not None or self.decided_by is not None:
                raise ValueError("Pending approval requests must not include decision fields.")
        if self.status in _TERMINAL_STATUSES - {ApprovalStatus.not_required}:
            if self.decided_at is None or self.decision_reason is None:
                raise ValueError("Terminal approval requests must include decision time and reason.")
        return self


class ApprovalManager:
    def __init__(self, *, recorder: object | None = None) -> None:
        self.recorder = recorder
        self._requests: dict[str, ApprovalRequest] = {}

    def create_request(
        self,
        *,
        run_id: str,
        trace_id: str,
        request_id: str | None,
        tool_name: str,
        action: str,
        requested_scope: str,
        risk_level: RuntimeRiskLevel | str,
        reason: str,
    ) -> ApprovalRequest:
        request = ApprovalRequest(
            run_id=run_id,
            trace_id=trace_id,
            request_id=request_id,
            tool_name=tool_name,
            action=action,
            requested_scope=requested_scope,
            risk_level=RuntimeRiskLevel(risk_level),
            reason=reason,
            status=ApprovalStatus.pending,
        )
        self._requests[request.approval_id] = request
        self._record(
            request,
            event_type=TrajectoryEventType.approval_requested,
            status=RuntimeEventStatus.success,
            reason=reason,
        )
        return request

    def approve(self, approval_id: str, *, decided_by: str, reason: str) -> ApprovalRequest:
        request = self._decide(
            approval_id,
            status=ApprovalStatus.approved,
            decided_by=decided_by,
            reason=reason,
        )
        self._record(
            request,
            event_type=TrajectoryEventType.approval_approved,
            status=RuntimeEventStatus.success,
            reason=reason,
        )
        return request

    def reject(self, approval_id: str, *, decided_by: str, reason: str) -> ApprovalRequest:
        request = self._decide(
            approval_id,
            status=ApprovalStatus.rejected,
            decided_by=decided_by,
            reason=reason,
        )
        self._record(
            request,
            event_type=TrajectoryEventType.approval_rejected,
            status=RuntimeEventStatus.failed,
            reason=reason,
        )
        return request

    def expire(self, approval_id: str, *, reason: str) -> ApprovalRequest:
        request = self._decide(
            approval_id,
            status=ApprovalStatus.expired,
            decided_by=None,
            reason=reason,
        )
        self._record(
            request,
            event_type=TrajectoryEventType.approval_expired,
            status=RuntimeEventStatus.failed,
            reason=reason,
        )
        return request

    def get_request(self, approval_id: str) -> ApprovalRequest:
        try:
            return self._requests[approval_id]
        except KeyError as exc:
            raise KeyError(f"Unknown approval_id: {approval_id}") from exc

    def list_requests(self, *, run_id: str | None = None) -> list[ApprovalRequest]:
        values = list(self._requests.values())
        if run_id is None:
            return values
        return [request for request in values if request.run_id == run_id]

    def can_continue(self, approval_id: str) -> bool:
        return self.get_request(approval_id).status is ApprovalStatus.approved

    def _decide(
        self,
        approval_id: str,
        *,
        status: ApprovalStatus,
        decided_by: str | None,
        reason: str,
    ) -> ApprovalRequest:
        request = self.get_request(approval_id)
        if request.status in _TERMINAL_STATUSES:
            raise ValueError(f"Approval request is already terminal: {request.status.value}")
        updated = request.model_copy(
            update={
                "status": status,
                "decided_at": datetime.now(UTC),
                "decided_by": decided_by,
                "decision_reason": reason,
            }
        )
        self._requests[approval_id] = updated
        return updated

    def _record(
        self,
        request: ApprovalRequest,
        *,
        event_type: TrajectoryEventType,
        status: RuntimeEventStatus,
        reason: str,
    ) -> None:
        if self.recorder is not None:
            self.recorder.record_approval_event(
                event_type=event_type,
                tool_name=request.tool_name,
                action=request.action,
                requested_scope=request.requested_scope,
                risk_level=request.risk_level,
                approval_id=request.approval_id,
                status=status,
                human_review_required=True,
                reason=reason,
            )
