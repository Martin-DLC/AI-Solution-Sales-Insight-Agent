from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError

from agent.workflow_c.contracts import NodeFailurePolicy, WorkflowNode
from agent.workflow_c.failures import (
    MissingNodeDependencyError,
    NodeBusinessRuleError,
    NodeContractViolationError,
    NodeJSONParseError,
    redact_secrets,
    validation_issues_from_error,
)
from agent.workflow_c.services import WorkflowServices
from agent.workflow_c.state import (
    ArchitectureCGraphState,
    FailureCategory,
    NodeExecutionRecord,
    NodeStatus,
    WorkflowFailure,
    WorkflowNodeName,
    WorkflowStatus,
)
from llm.errors import LLMRequestError, LLMResponseError
from llm.models import LLMUsage


def execute_node(
    node: WorkflowNode,
    state: ArchitectureCGraphState,
    services: WorkflowServices,
) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    started_perf = time.perf_counter()
    try:
        _ensure_dependencies(node, state)
        raw_patch = node.run(dict(state), services)
        if not isinstance(raw_patch, dict):
            raise NodeContractViolationError(message="Node output must be a dictionary.")
        _ensure_produced_fields(node, raw_patch)
        output = node.contract.output_model.model_validate(raw_patch)
        business_patch = {
            field: getattr(output, field)
            for field in node.contract.produced_state_fields
        }
        completed_at = datetime.now(UTC)
        completed_at, latency_ms = _normalize_record_timestamps(
            started_at=started_at,
            completed_at=completed_at,
            started_perf=started_perf,
        )
        record = _record(
            node_name=node.contract.name,
            status=NodeStatus.succeeded,
            started_at=started_at,
            completed_at=completed_at,
            latency_ms=latency_ms,
            prompt_version=node.contract.prompt_version,
            output_model=node.contract.output_model.__name__,
        )
        return {
            **business_patch,
            "current_node": node.contract.name,
            "workflow_status": business_patch.get("workflow_status", WorkflowStatus.running),
            "node_records": [record],
        }
    except Exception as exc:
        completed_at = datetime.now(UTC)
        completed_at, latency_ms = _normalize_record_timestamps(
            started_at=started_at,
            completed_at=completed_at,
            started_perf=started_perf,
        )
        return _failure_patch(node, exc, started_at, completed_at, latency_ms)


def _ensure_dependencies(node: WorkflowNode, state: ArchitectureCGraphState) -> None:
    missing = [
        field
        for field in node.contract.required_state_fields
        if field not in state or state.get(field) is None
    ]
    if missing:
        raise MissingNodeDependencyError(node.contract.name, missing)


def _ensure_produced_fields(node: WorkflowNode, patch: dict[str, Any]) -> None:
    expected = set(node.contract.produced_state_fields)
    actual = set(patch)
    missing = expected - actual
    extra = actual - expected
    if missing or extra:
        raise NodeContractViolationError(
            message=(
                f"Node {node.contract.name.value} returned invalid fields. "
                f"Missing={sorted(missing)}; extra={sorted(extra)}."
            ),
            unauthorized_fields=extra,
            missing_fields=missing,
        )


def _failure_patch(
    node: WorkflowNode,
    error: Exception,
    started_at: datetime,
    completed_at: datetime,
    latency_ms: int,
) -> dict[str, Any]:
    failure_id = f"failure-{uuid.uuid4().hex}"
    category = _failure_category(node.contract.name, error)
    retryable = isinstance(error, LLMRequestError)
    if isinstance(error, NodeBusinessRuleError):
        issues = list(error.issues)
    elif isinstance(error, ValidationError):
        issues = validation_issues_from_error(error)
    else:
        issues = []
    failure = WorkflowFailure(
        failure_id=failure_id,
        node_name=node.contract.name,
        failure_category=category,
        message=_safe_error_message(error),
        retryable=retryable,
        attempt=1,
        occurred_at=completed_at,
        validation_issues=issues,
        raw_artifact_path=None,
    )
    record = _record(
        node_name=node.contract.name,
        status=NodeStatus.failed,
        started_at=started_at,
        completed_at=completed_at,
        latency_ms=latency_ms,
        prompt_version=node.contract.prompt_version,
        output_model=node.contract.output_model.__name__,
        failure_id=failure_id,
    )
    status = (
        WorkflowStatus.failed
        if node.contract.failure_policy is NodeFailurePolicy.fail_workflow
        else WorkflowStatus.awaiting_human_review
    )
    patch: dict[str, Any] = {
        "current_node": node.contract.name,
        "workflow_status": status,
        "failures": [failure],
        "node_records": [record],
    }
    if status is WorkflowStatus.awaiting_human_review:
        patch["human_review_required"] = True
        patch["human_review_reasons"] = [_safe_error_message(error)]
    return patch


def _failure_category(node_name: WorkflowNodeName, error: Exception) -> FailureCategory:
    if isinstance(error, MissingNodeDependencyError):
        return FailureCategory.missing_dependency
    if isinstance(error, LLMRequestError):
        return FailureCategory.llm_request
    if isinstance(error, NodeJSONParseError) or isinstance(error, json.JSONDecodeError):
        return FailureCategory.json_parse
    if isinstance(error, ValidationError):
        if node_name is WorkflowNodeName.input_validation:
            return FailureCategory.input_validation
        return FailureCategory.schema_validation
    if isinstance(error, NodeBusinessRuleError):
        return FailureCategory.schema_validation
    if isinstance(error, LLMResponseError):
        return FailureCategory.llm_response
    return FailureCategory.internal_error


def _record(
    *,
    node_name: WorkflowNodeName,
    status: NodeStatus,
    started_at: datetime,
    completed_at: datetime,
    latency_ms: int,
    prompt_version: str | None,
    output_model: str,
    failure_id: str | None = None,
) -> NodeExecutionRecord:
    return NodeExecutionRecord(
        node_name=node_name,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        latency_ms=latency_ms,
        prompt_version=prompt_version,
        model_name=None,
        usage=LLMUsage(),
        output_model=output_model,
        artifact_paths=[],
        failure_id=failure_id,
    )


def _safe_error_message(error: Exception) -> str:
    return redact_secrets(str(error) or error.__class__.__name__)


def _normalize_record_timestamps(
    *,
    started_at: datetime,
    completed_at: datetime,
    started_perf: float,
) -> tuple[datetime, int]:
    elapsed_ms = max(0, int((time.perf_counter() - started_perf) * 1000))
    monotonic_completed_at = started_at + timedelta(milliseconds=elapsed_ms)
    safe_completed_at = max(completed_at, monotonic_completed_at)
    latency_ms = max(0, int((safe_completed_at - started_at).total_seconds() * 1000))
    return safe_completed_at, latency_ms
