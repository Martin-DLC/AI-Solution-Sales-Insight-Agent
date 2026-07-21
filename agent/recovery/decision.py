from __future__ import annotations

from agent.governance.models import RuntimeRiskLevel
from agent.recovery.models import (
    ErrorType,
    FallbackType,
    RecoveryAction,
    RecoveryDecision,
    categorize_error,
)
from agent.recovery.policy import RetryPolicy


class RecoveryDecisionEngine:
    def __init__(self, retry_policy: RetryPolicy | None = None) -> None:
        self.retry_policy = retry_policy or RetryPolicy()

    def decide(
        self,
        *,
        error_type: ErrorType | str,
        current_retry_count: int = 0,
        tool_policy: object | None = None,
        trajectory_evaluation: object | None = None,
        runtime_status: str | None = None,
    ) -> RecoveryDecision:
        resolved = ErrorType(error_type)
        category = categorize_error(resolved)
        if self.retry_policy.can_retry(error_type=resolved, current_retry_count=current_retry_count):
            return RecoveryDecision(
                error_type=resolved,
                error_category=category,
                decision=RecoveryAction.retry,
                retry_recommended=True,
                reason=self.retry_policy.explain(error_type=resolved, current_retry_count=current_retry_count),
                safe_to_continue=False,
            )
        if self.retry_policy.should_fallback_after_retry(error_type=resolved, current_retry_count=current_retry_count):
            return RecoveryDecision(
                error_type=resolved,
                error_category=category,
                decision=RecoveryAction.fallback,
                fallback_type=FallbackType.model_fallback if category.value == "model_error" else FallbackType.tool_fallback,
                reason=self.retry_policy.explain(error_type=resolved, current_retry_count=current_retry_count),
                safe_to_continue=True,
            )
        if resolved is ErrorType.model_schema_invalid:
            return self._fallback(resolved, FallbackType.model_fallback, "Model output schema was invalid; use fallback or human review.")
        if resolved is ErrorType.permission_denied:
            return RecoveryDecision(
                error_type=resolved,
                error_category=category,
                decision=RecoveryAction.human_review,
                human_review_required=True,
                stop_recommended=True,
                reason="Permission was denied; do not continue automatically.",
                safe_to_continue=False,
            )
        if resolved is ErrorType.retrieval_empty:
            return self._fallback(resolved, FallbackType.retrieval_fallback, "No retrieval evidence found; use safe response fallback and human confirmation.")
        if resolved is ErrorType.retrieval_boundary_failed:
            return self._fallback(
                resolved,
                FallbackType.safe_response_fallback,
                "Retrieval boundary failed; require human review before relying on result.",
                human_review_required=True,
            )
        if resolved is ErrorType.evaluation_gate_failed:
            stop = bool(getattr(trajectory_evaluation, "stop_recommended", False))
            return RecoveryDecision(
                error_type=resolved,
                error_category=category,
                decision=RecoveryAction.stop if stop else RecoveryAction.human_review,
                human_review_required=not stop,
                stop_recommended=stop,
                reason="Trajectory evaluation gate failed.",
                safe_to_continue=False,
            )
        if resolved in {ErrorType.step_limit_exceeded, ErrorType.consecutive_failure_limit_exceeded}:
            return RecoveryDecision(
                error_type=resolved,
                error_category=category,
                decision=RecoveryAction.stop,
                stop_recommended=True,
                reason="Runtime policy limit was exceeded.",
                safe_to_continue=False,
            )
        if tool_policy is not None and getattr(tool_policy, "risk_level", None) is RuntimeRiskLevel.high:
            return RecoveryDecision(
                error_type=resolved,
                error_category=category,
                decision=RecoveryAction.human_review,
                human_review_required=True,
                reason="High risk tool failure requires human review.",
                safe_to_continue=False,
            )
        return RecoveryDecision(
            error_type=resolved,
            error_category=category,
            decision=RecoveryAction.human_review,
            human_review_required=True,
            reason="Unknown or non-retryable error requires human review.",
            safe_to_continue=False,
        )

    def _fallback(
        self,
        error_type: ErrorType,
        fallback_type: FallbackType,
        reason: str,
        *,
        human_review_required: bool = False,
    ) -> RecoveryDecision:
        return RecoveryDecision(
            error_type=error_type,
            error_category=categorize_error(error_type),
            decision=RecoveryAction.fallback,
            fallback_type=fallback_type,
            human_review_required=human_review_required,
            reason=reason,
            safe_to_continue=not human_review_required,
        )
