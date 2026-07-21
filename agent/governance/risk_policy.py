from __future__ import annotations

from agent.governance.models import RuntimeRiskLevel


_HIGH_RISK_ACTION_FRAGMENTS = ("delete", "send", "external_write")
_WRITE_ACTION_FRAGMENTS = ("write", "update", "create", "send", "delete", "external_write")
_READ_ACTION_FRAGMENTS = ("read", "search", "draft")


class RiskPolicy:
    def normalize_risk_level(self, value: str | RuntimeRiskLevel | None) -> RuntimeRiskLevel:
        if value is None:
            return RuntimeRiskLevel.unknown
        try:
            return RuntimeRiskLevel(value)
        except ValueError:
            return RuntimeRiskLevel.unknown

    def infer_risk_level(
        self,
        *,
        tool_name: str,
        action: str,
        configured_risk_level: str | RuntimeRiskLevel | None = None,
    ) -> RuntimeRiskLevel:
        configured = self.normalize_risk_level(configured_risk_level)
        lowered_action = action.casefold()
        lowered_tool = tool_name.casefold()
        if configured is RuntimeRiskLevel.high:
            return RuntimeRiskLevel.high
        if any(fragment in lowered_action or fragment in lowered_tool for fragment in _HIGH_RISK_ACTION_FRAGMENTS):
            return RuntimeRiskLevel.high
        if configured is RuntimeRiskLevel.medium:
            return RuntimeRiskLevel.medium
        if any(fragment in lowered_action for fragment in _WRITE_ACTION_FRAGMENTS):
            return RuntimeRiskLevel.medium
        if configured is RuntimeRiskLevel.low:
            return RuntimeRiskLevel.low
        if any(fragment in lowered_action for fragment in _READ_ACTION_FRAGMENTS):
            return RuntimeRiskLevel.low
        return RuntimeRiskLevel.unknown

    def requires_human_review(
        self,
        *,
        risk_level: RuntimeRiskLevel,
        action: str,
        configured_requires_human_review: bool = False,
    ) -> bool:
        lowered_action = action.casefold()
        return (
            configured_requires_human_review
            or risk_level is RuntimeRiskLevel.high
            or any(fragment in lowered_action for fragment in _HIGH_RISK_ACTION_FRAGMENTS)
        )

    def requires_confirmation(
        self,
        *,
        risk_level: RuntimeRiskLevel,
        action: str,
        configured_requires_confirmation: bool = False,
    ) -> bool:
        lowered_action = action.casefold()
        return (
            configured_requires_confirmation
            or risk_level in {RuntimeRiskLevel.medium, RuntimeRiskLevel.high}
            or any(fragment in lowered_action for fragment in _WRITE_ACTION_FRAGMENTS)
        )
