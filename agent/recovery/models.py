from __future__ import annotations

from enum import Enum

from pydantic import Field

from schemas.common_models import StrictBaseModel


class ErrorCategory(str, Enum):
    model_error = "model_error"
    tool_error = "tool_error"
    permission_error = "permission_error"
    retrieval_error = "retrieval_error"
    evaluation_error = "evaluation_error"
    human_review_error = "human_review_error"
    runtime_error = "runtime_error"
    unknown = "unknown"


class ErrorType(str, Enum):
    model_timeout = "model_timeout"
    model_schema_invalid = "model_schema_invalid"
    model_unavailable = "model_unavailable"
    tool_timeout = "tool_timeout"
    tool_failed = "tool_failed"
    permission_denied = "permission_denied"
    retrieval_empty = "retrieval_empty"
    retrieval_boundary_failed = "retrieval_boundary_failed"
    evaluation_gate_failed = "evaluation_gate_failed"
    human_review_timeout = "human_review_timeout"
    step_limit_exceeded = "step_limit_exceeded"
    consecutive_failure_limit_exceeded = "consecutive_failure_limit_exceeded"
    unknown_error = "unknown_error"


class FallbackType(str, Enum):
    retrieval_fallback = "retrieval_fallback"
    model_fallback = "model_fallback"
    tool_fallback = "tool_fallback"
    workflow_fallback = "workflow_fallback"
    human_fallback = "human_fallback"
    safe_response_fallback = "safe_response_fallback"


class RecoveryAction(str, Enum):
    retry = "retry"
    fallback = "fallback"
    human_review = "human_review"
    stop = "stop"
    continue_ = "continue"
    compensate = "compensate"


class FallbackPolicy(StrictBaseModel):
    fallback_type: FallbackType
    trigger_error_types: list[ErrorType]
    default_action: RecoveryAction
    retryable: bool
    requires_human_review: bool
    safe_to_continue: bool
    notes: str


class RecoveryDecision(StrictBaseModel):
    error_type: ErrorType
    error_category: ErrorCategory
    decision: RecoveryAction
    fallback_type: FallbackType | None = None
    retry_recommended: bool = False
    stop_recommended: bool = False
    human_review_required: bool = False
    compensation_required: bool = False
    idempotency_required: bool = False
    reason: str
    safe_to_continue: bool = False
    warnings: list[str] = Field(default_factory=list)


def categorize_error(error_type: ErrorType | str) -> ErrorCategory:
    resolved = ErrorType(error_type)
    if resolved in {ErrorType.model_timeout, ErrorType.model_schema_invalid, ErrorType.model_unavailable}:
        return ErrorCategory.model_error
    if resolved in {ErrorType.tool_timeout, ErrorType.tool_failed}:
        return ErrorCategory.tool_error
    if resolved is ErrorType.permission_denied:
        return ErrorCategory.permission_error
    if resolved in {ErrorType.retrieval_empty, ErrorType.retrieval_boundary_failed}:
        return ErrorCategory.retrieval_error
    if resolved is ErrorType.evaluation_gate_failed:
        return ErrorCategory.evaluation_error
    if resolved is ErrorType.human_review_timeout:
        return ErrorCategory.human_review_error
    if resolved in {ErrorType.step_limit_exceeded, ErrorType.consecutive_failure_limit_exceeded}:
        return ErrorCategory.runtime_error
    return ErrorCategory.unknown
