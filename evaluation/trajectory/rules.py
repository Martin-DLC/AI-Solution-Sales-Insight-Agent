from __future__ import annotations

from pathlib import Path

from pydantic import Field

from agent.governance.models import RuntimeEventStatus, RuntimeRiskLevel, TrajectoryEvent, TrajectoryEventType
from evaluation.trajectory.models import GateDecision, RuleSeverity, TrajectoryRuleResult
from schemas.common_models import StrictBaseModel


DEFAULT_RULES_PATH = Path("config/trajectory_evaluation_rules.yaml")


class TrajectoryRuleConfig(StrictBaseModel):
    rule_id: str
    rule_name: str
    severity: RuleSeverity
    recommended_action: GateDecision
    enabled: bool = True
    threshold: int | None = None


def load_trajectory_rules(path: str | Path = DEFAULT_RULES_PATH) -> list[TrajectoryRuleConfig]:
    items = _parse_rule_yaml(Path(path).read_text(encoding="utf-8"))
    return [TrajectoryRuleConfig.model_validate(item) for item in items]


def evaluate_rules(
    events: list[TrajectoryEvent],
    *,
    final_status: str,
    rules: list[TrajectoryRuleConfig] | None = None,
) -> list[TrajectoryRuleResult]:
    configs = [rule for rule in (rules or load_trajectory_rules()) if rule.enabled]
    return [_evaluate_rule(config, events, final_status=final_status) for config in configs]


def _evaluate_rule(
    config: TrajectoryRuleConfig,
    events: list[TrajectoryEvent],
    *,
    final_status: str,
) -> TrajectoryRuleResult:
    if config.rule_id == "no_policy_stop":
        failed = final_status == "stopped_by_policy" or _has_event(events, TrajectoryEventType.stopped_by_policy)
        return _result(config, not failed, "Runtime was stopped by policy." if failed else "No policy stop detected.", events)
    if config.rule_id == "no_permission_denied":
        denied = _events_of_type(events, TrajectoryEventType.permission_denied)
        return _result(config, not denied, "Permission denied event detected." if denied else "No permission denial detected.", denied)
    if config.rule_id == "high_risk_requires_review":
        high_risk = [event for event in events if event.risk_level is RuntimeRiskLevel.high]
        missing = [event for event in high_risk if not event.human_review_required]
        return _result(config, not missing, "High risk event without human review flag." if missing else "High risk events require review or none were present.", missing)
    if config.rule_id == "fallback_requires_explanation":
        fallback_events = [event for event in events if event.fallback_triggered]
        missing = [event for event in fallback_events if not event.output_summary]
        return _result(config, not missing, "Fallback was triggered without an explanation summary." if missing else "Fallback explanations are present or fallback was not triggered.", missing)
    if config.rule_id == "human_review_event_consistency":
        required_events = [event for event in events if event.human_review_required]
        explicit_review_events = _events_of_type(events, TrajectoryEventType.human_review_required)
        failed = bool(required_events) and not explicit_review_events
        return _result(config, not failed, "Human review required without a human_review_required event." if failed else "Human review event consistency is satisfied.", required_events)
    if config.rule_id == "no_excessive_failures":
        threshold = config.threshold or 3
        failed_events = [event for event in events if event.status is RuntimeEventStatus.failed]
        failed = len(failed_events) > threshold
        return _result(config, not failed, f"Failed event count {len(failed_events)} exceeded threshold {threshold}." if failed else "Failed event count is within threshold.", failed_events)
    if config.rule_id == "required_core_nodes_present":
        event_types = {event.event_type for event in events}
        has_terminal = TrajectoryEventType.run_completed in event_types or TrajectoryEventType.run_failed in event_types
        missing = [
            name
            for name, present in {
                "run_started": TrajectoryEventType.run_started in event_types,
                "fallback_assessed": TrajectoryEventType.fallback_assessed in event_types,
                "generation_completed": TrajectoryEventType.generation_completed in event_types,
                "terminal_event": has_terminal,
            }.items()
            if not present
        ]
        return _result(config, not missing, f"Missing core event(s): {', '.join(missing)}." if missing else "Required core events are present.", events[:1])
    if config.rule_id == "shadow_does_not_override_formal":
        bad_shadow = [
            event
            for event in events
            if event.event_type is TrajectoryEventType.shadow_retrieval_completed
            and event.output_summary
            and "formal evidence source" in event.output_summary.casefold()
        ]
        return _result(config, not bad_shadow, "Shadow event appears to override formal evidence." if bad_shadow else "Shadow events do not override formal evidence.", bad_shadow)
    return _result(config, True, "Rule is not implemented and is treated as informational pass.", [])


def _result(
    config: TrajectoryRuleConfig,
    passed: bool,
    reason: str,
    evidence_events: list[TrajectoryEvent],
) -> TrajectoryRuleResult:
    return TrajectoryRuleResult(
        rule_id=config.rule_id,
        rule_name=config.rule_name,
        passed=passed,
        severity=config.severity,
        reason=reason,
        evidence_event_ids=[event.event_id for event in evidence_events[:10]],
        recommended_action=config.recommended_action,
    )


def _events_of_type(events: list[TrajectoryEvent], event_type: TrajectoryEventType) -> list[TrajectoryEvent]:
    return [event for event in events if event.event_type is event_type]


def _has_event(events: list[TrajectoryEvent], event_type: TrajectoryEventType) -> bool:
    return any(event.event_type is event_type for event in events)


def _parse_rule_yaml(content: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line == "rules:":
            continue
        if line.startswith("- "):
            if current is not None:
                items.append(current)
            current = {}
            line = line[2:].strip()
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        current[key.strip()] = _parse_scalar(value.strip())
    if current is not None:
        items.append(current)
    return items


def _parse_scalar(value: str) -> object:
    if value.casefold() == "true":
        return True
    if value.casefold() == "false":
        return False
    if value.isdigit():
        return int(value)
    return value.strip('"').strip("'")
