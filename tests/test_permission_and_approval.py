from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent.governance import (
    ApprovalManager,
    ApprovalRequest,
    ApprovalStatus,
    PermissionChecker,
    RuntimeRiskLevel,
    TrajectoryEventType,
    TrajectoryRecorder,
    load_tool_permissions,
)
from agent.models import SolutionInsightRequest
from agent.solution_insight_service import SolutionInsightService
from app.main import app


def test_tool_permissions_yaml_loads_expected_tools() -> None:
    policies = load_tool_permissions()

    assert set(policies) == {
        "knowledge_search",
        "crm_read",
        "crm_write",
        "ticket_read",
        "ticket_update",
        "bi_read",
        "email_draft",
        "email_send",
        "delete_record",
    }


def test_read_only_tool_is_allowed() -> None:
    decision = PermissionChecker().check_permission(
        tool_name="knowledge_search",
        action="search",
        requested_scope="knowledge:read",
    )

    assert decision.allowed is True
    assert decision.risk_level is RuntimeRiskLevel.low
    assert decision.requires_human_review is False


def test_unknown_tool_is_denied_by_default() -> None:
    decision = PermissionChecker().check_permission(
        tool_name="unknown_tool",
        action="read",
        requested_scope="unknown:read",
    )

    assert decision.allowed is False
    assert decision.denial_reason == "unknown_tool"
    assert decision.risk_level is RuntimeRiskLevel.high


def test_unknown_action_is_denied_by_default() -> None:
    decision = PermissionChecker().check_permission(
        tool_name="knowledge_search",
        action="write",
        requested_scope="knowledge:read",
    )

    assert decision.allowed is False
    assert decision.denial_reason == "unknown_action"


def test_scope_exceeded_is_denied_by_default() -> None:
    decision = PermissionChecker().check_permission(
        tool_name="crm_read",
        action="read",
        requested_scope="crm:write",
    )

    assert decision.allowed is False
    assert decision.denial_reason == "scope_exceeded"


@pytest.mark.parametrize("tool_name,action,scope", [
    ("crm_write", "write", "crm:write"),
    ("email_send", "send", "email:send"),
    ("delete_record", "delete", "records:delete"),
])
def test_high_risk_tools_require_human_review(tool_name: str, action: str, scope: str) -> None:
    checker = PermissionChecker()

    decision = checker.check_permission(
        tool_name=tool_name,
        action=action,
        requested_scope=scope,
    )

    assert decision.allowed is True
    assert decision.risk_level is RuntimeRiskLevel.high
    assert decision.requires_human_review is True
    assert checker.is_high_risk(tool_name=tool_name, action=action) is True
    assert checker.requires_approval(tool_name=tool_name, action=action) is True


def test_approval_request_serializes() -> None:
    request = ApprovalRequest(
        run_id="run-1",
        trace_id="trace-1",
        request_id="request-1",
        tool_name="crm_write",
        action="write",
        requested_scope="crm:write",
        risk_level=RuntimeRiskLevel.high,
        reason="Requires account owner approval.",
    )

    dumped = request.model_dump(mode="json")

    assert dumped["approval_id"].startswith("approval-")
    assert dumped["status"] == "pending"


def test_create_request_generates_pending_and_can_continue_false() -> None:
    manager = ApprovalManager()

    request = manager.create_request(
        run_id="run-1",
        trace_id="trace-1",
        request_id="request-1",
        tool_name="crm_write",
        action="write",
        requested_scope="crm:write",
        risk_level=RuntimeRiskLevel.high,
        reason="Needs approval.",
    )

    assert request.status is ApprovalStatus.pending
    assert manager.can_continue(request.approval_id) is False


def test_approve_allows_continue() -> None:
    manager = ApprovalManager()
    request = _approval_request(manager)

    approved = manager.approve(request.approval_id, decided_by="local_reviewer", reason="Approved for test.")

    assert approved.status is ApprovalStatus.approved
    assert approved.decided_by == "local_reviewer"
    assert manager.can_continue(request.approval_id) is True


def test_reject_blocks_continue() -> None:
    manager = ApprovalManager()
    request = _approval_request(manager)

    rejected = manager.reject(request.approval_id, decided_by="local_reviewer", reason="Too risky.")

    assert rejected.status is ApprovalStatus.rejected
    assert manager.can_continue(request.approval_id) is False


def test_expire_blocks_continue() -> None:
    manager = ApprovalManager()
    request = _approval_request(manager)

    expired = manager.expire(request.approval_id, reason="Timed out.")

    assert expired.status is ApprovalStatus.expired
    assert manager.can_continue(request.approval_id) is False


def test_terminal_approval_cannot_be_decided_again() -> None:
    manager = ApprovalManager()
    request = _approval_request(manager)
    manager.approve(request.approval_id, decided_by="local_reviewer", reason="Approved.")

    with pytest.raises(ValueError):
        manager.reject(request.approval_id, decided_by="local_reviewer", reason="Changed mind.")


def test_permission_denied_event_is_written_to_trajectory_recorder() -> None:
    recorder = TrajectoryRecorder()
    recorder.start_run(run_id="run-1", trace_id="trace-1")
    checker = PermissionChecker(recorder=recorder)

    checker.check_permission(
        tool_name="unknown_tool",
        action="read",
        requested_scope="unknown:read",
    )

    event = recorder.export_events()[-1]
    assert event.event_type is TrajectoryEventType.permission_denied
    assert event.status.value == "failed"
    assert event.tool_name == "unknown_tool"


def test_approval_requested_event_is_written_to_trajectory_recorder() -> None:
    recorder = TrajectoryRecorder()
    recorder.start_run(run_id="run-1", trace_id="trace-1")
    manager = ApprovalManager(recorder=recorder)

    request = manager.create_request(
        run_id="run-1",
        trace_id="trace-1",
        request_id="request-1",
        tool_name="email_send",
        action="send",
        requested_scope="email:send",
        risk_level=RuntimeRiskLevel.high,
        reason="Outbound customer communication.",
    )

    event = recorder.export_events()[-1]
    assert request.status is ApprovalStatus.pending
    assert event.event_type is TrajectoryEventType.approval_requested
    assert event.human_review_required is True
    assert event.risk_level is RuntimeRiskLevel.high


def test_service_normal_call_is_not_blocked_by_permission_system() -> None:
    service = SolutionInsightService.from_defaults(llm_mode="deterministic")

    response = service.generate_insight(
        SolutionInsightRequest(
            user_query="一家中型 SaaS 公司想提升销售线索转化和客户成功效率",
            company_id="demo_saas_001",
            industry="SaaS",
            llm_mode="deterministic",
        )
    )

    assert response.requirement_summary
    assert response.governance_trace is not None
    assert response.governance_trace.stopped_by_policy is False
    assert any(
        event.event_type is TrajectoryEventType.permission_checked
        and event.tool_name == "crm_read"
        for event in response.runtime_trace.events  # type: ignore[union-attr]
    )


def test_solution_insight_api_still_passes() -> None:
    client = TestClient(app)

    response = client.post(
        "/solution-insight",
        json={
            "user_query": "一家中型 SaaS 公司想提升销售线索转化和客户成功效率",
            "industry": "SaaS",
            "llm_mode": "deterministic",
        },
    )

    assert response.status_code == 200
    assert response.json()["governance_trace"]["stopped_by_policy"] is False


def _approval_request(manager: ApprovalManager):
    return manager.create_request(
        run_id="run-1",
        trace_id="trace-1",
        request_id="request-1",
        tool_name="crm_write",
        action="write",
        requested_scope="crm:write",
        risk_level=RuntimeRiskLevel.high,
        reason="Needs approval.",
    )
