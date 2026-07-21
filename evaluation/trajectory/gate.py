from __future__ import annotations

from agent.governance.models import RuntimeRiskLevel, TrajectoryEvent
from evaluation.trajectory.models import GateDecision, RuleSeverity, TrajectoryEvaluationResult, TrajectoryRuleResult
from evaluation.trajectory.rules import evaluate_rules


class EvaluationGate:
    def evaluate(
        self,
        events: list[TrajectoryEvent],
        *,
        response: object | None = None,
        metrics: object | None = None,
    ) -> TrajectoryEvaluationResult:
        final_status = _final_status(events, metrics)
        rule_results = evaluate_rules(events, final_status=final_status)
        gate_decision = self.decide(rule_results)
        human_review_reasons = [
            result.reason
            for result in rule_results
            if not result.passed and result.recommended_action is GateDecision.human_review
        ]
        event_review_required = any(event.human_review_required for event in events)
        if event_review_required and not human_review_reasons:
            human_review_reasons.append("Trajectory contains human_review_required event or flag.")
        risk_level = _risk_level(rule_results, events)
        return TrajectoryEvaluationResult(
            run_id=events[0].run_id if events else "unknown",
            trace_id=events[0].trace_id if events else "unknown",
            final_status=final_status,
            rule_results=rule_results,
            passed=all(result.passed for result in rule_results),
            gate_decision=GateDecision.human_review if event_review_required and gate_decision is GateDecision.pass_ else gate_decision,
            human_review_required=gate_decision is GateDecision.human_review or event_review_required,
            human_review_reasons=human_review_reasons,
            retry_recommended=gate_decision is GateDecision.retry,
            stop_recommended=gate_decision is GateDecision.stop,
            risk_level=risk_level,
            limitations=[
                "Rule-based local trajectory evaluation only.",
                "No LLM judge is used.",
                "Pending review is not a completed human score.",
            ],
        )

    def decide(self, rule_results: list[TrajectoryRuleResult]) -> GateDecision:
        failed = [result for result in rule_results if not result.passed]
        if any(result.severity is RuleSeverity.critical for result in failed):
            return GateDecision.stop
        if any(result.recommended_action is GateDecision.stop for result in failed):
            return GateDecision.stop
        if any(result.recommended_action is GateDecision.retry for result in failed):
            return GateDecision.retry
        if any(result.recommended_action is GateDecision.human_review for result in failed):
            return GateDecision.human_review
        return GateDecision.pass_

    def should_trigger_human_review(self, result: TrajectoryEvaluationResult) -> bool:
        return result.gate_decision is GateDecision.human_review or result.human_review_required

    def should_stop(self, result: TrajectoryEvaluationResult) -> bool:
        return result.gate_decision is GateDecision.stop or result.stop_recommended

    def should_retry(self, result: TrajectoryEvaluationResult) -> bool:
        return result.gate_decision is GateDecision.retry or result.retry_recommended


def _final_status(events: list[TrajectoryEvent], metrics: object | None) -> str:
    if metrics is not None and getattr(metrics, "final_status", None):
        return str(getattr(metrics, "final_status"))
    event_types = {event.event_type.value for event in events}
    if "stopped_by_policy" in event_types:
        return "stopped_by_policy"
    if "run_failed" in event_types:
        return "failed"
    if "run_completed" in event_types:
        return "completed"
    return "running"


def _risk_level(rule_results: list[TrajectoryRuleResult], events: list[TrajectoryEvent]) -> RuntimeRiskLevel:
    if any(event.risk_level is RuntimeRiskLevel.high for event in events):
        return RuntimeRiskLevel.high
    if any(not result.passed and result.severity in {RuleSeverity.error, RuleSeverity.critical} for result in rule_results):
        return RuntimeRiskLevel.medium
    if any(event.risk_level is RuntimeRiskLevel.medium for event in events):
        return RuntimeRiskLevel.medium
    return RuntimeRiskLevel.low
