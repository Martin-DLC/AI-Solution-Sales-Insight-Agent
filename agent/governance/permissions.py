from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator, model_validator

from agent.governance.models import RuntimeRiskLevel
from agent.governance.risk_policy import RiskPolicy
from schemas.common_models import StrictBaseModel


DEFAULT_TOOL_PERMISSIONS_PATH = Path("config/tool_permissions.yaml")


class ToolPermissionPolicy(StrictBaseModel):
    tool_name: str
    allowed_actions: list[str]
    permission_scope: str
    risk_level: RuntimeRiskLevel = RuntimeRiskLevel.unknown
    requires_confirmation: bool = False
    requires_human_review: bool = False
    idempotent: bool = False
    reversible: bool = False
    description: str

    @field_validator("allowed_actions")
    @classmethod
    def allowed_actions_must_not_be_empty(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("allowed_actions must include at least one action.")
        return _deduplicate(values)

    @model_validator(mode="after")
    def validate_high_risk_review(self) -> "ToolPermissionPolicy":
        if self.risk_level is RuntimeRiskLevel.high and not self.requires_human_review:
            raise ValueError("High risk tools must require human review.")
        return self


class PermissionDecision(StrictBaseModel):
    allowed: bool
    tool_name: str
    action: str
    requested_scope: str
    granted_scope: str | None = None
    risk_level: RuntimeRiskLevel = RuntimeRiskLevel.unknown
    requires_confirmation: bool = False
    requires_human_review: bool = False
    denial_reason: str | None = None
    policy_source: str


class PermissionChecker:
    def __init__(
        self,
        *,
        policies: dict[str, ToolPermissionPolicy] | None = None,
        policy_source: str | Path = DEFAULT_TOOL_PERMISSIONS_PATH,
        risk_policy: RiskPolicy | None = None,
        recorder: object | None = None,
    ) -> None:
        self.policy_source = str(policy_source)
        self.risk_policy = risk_policy or RiskPolicy()
        self.recorder = recorder
        self._policies = policies or load_tool_permissions(policy_source)

    def get_tool_policy(self, tool_name: str) -> ToolPermissionPolicy | None:
        return self._policies.get(tool_name)

    def check_permission(
        self,
        *,
        tool_name: str,
        action: str,
        requested_scope: str,
    ) -> PermissionDecision:
        policy = self.get_tool_policy(tool_name)
        if policy is None:
            decision = self._deny(
                tool_name=tool_name,
                action=action,
                requested_scope=requested_scope,
                risk_level=RuntimeRiskLevel.high,
                reason="unknown_tool",
            )
            self._record(decision)
            return decision
        risk_level = self.risk_policy.infer_risk_level(
            tool_name=tool_name,
            action=action,
            configured_risk_level=policy.risk_level,
        )
        requires_human_review = self.risk_policy.requires_human_review(
            risk_level=risk_level,
            action=action,
            configured_requires_human_review=policy.requires_human_review,
        )
        requires_confirmation = self.risk_policy.requires_confirmation(
            risk_level=risk_level,
            action=action,
            configured_requires_confirmation=policy.requires_confirmation,
        )
        if action not in policy.allowed_actions:
            decision = self._deny(
                tool_name=tool_name,
                action=action,
                requested_scope=requested_scope,
                risk_level=risk_level,
                reason="unknown_action",
                policy=policy,
                requires_confirmation=requires_confirmation,
                requires_human_review=requires_human_review,
            )
            self._record(decision)
            return decision
        if not _scope_allows(policy.permission_scope, requested_scope):
            decision = self._deny(
                tool_name=tool_name,
                action=action,
                requested_scope=requested_scope,
                risk_level=risk_level,
                reason="scope_exceeded",
                policy=policy,
                requires_confirmation=requires_confirmation,
                requires_human_review=requires_human_review,
            )
            self._record(decision)
            return decision
        decision = PermissionDecision(
            allowed=True,
            tool_name=tool_name,
            action=action,
            requested_scope=requested_scope,
            granted_scope=policy.permission_scope,
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            requires_human_review=requires_human_review,
            denial_reason=None,
            policy_source=self.policy_source,
        )
        self._record(decision)
        return decision

    def is_high_risk(self, *, tool_name: str, action: str) -> bool:
        policy = self.get_tool_policy(tool_name)
        if policy is None:
            return True
        return (
            self.risk_policy.infer_risk_level(
                tool_name=tool_name,
                action=action,
                configured_risk_level=policy.risk_level,
            )
            is RuntimeRiskLevel.high
        )

    def requires_approval(self, *, tool_name: str, action: str) -> bool:
        policy = self.get_tool_policy(tool_name)
        if policy is None:
            return True
        risk_level = self.risk_policy.infer_risk_level(
            tool_name=tool_name,
            action=action,
            configured_risk_level=policy.risk_level,
        )
        return self.risk_policy.requires_human_review(
            risk_level=risk_level,
            action=action,
            configured_requires_human_review=policy.requires_human_review,
        )

    def explain_denial(self, *, tool_name: str, action: str, requested_scope: str) -> str | None:
        decision = self.check_permission(
            tool_name=tool_name,
            action=action,
            requested_scope=requested_scope,
        )
        return decision.denial_reason

    def _deny(
        self,
        *,
        tool_name: str,
        action: str,
        requested_scope: str,
        risk_level: RuntimeRiskLevel,
        reason: str,
        policy: ToolPermissionPolicy | None = None,
        requires_confirmation: bool = False,
        requires_human_review: bool = False,
    ) -> PermissionDecision:
        return PermissionDecision(
            allowed=False,
            tool_name=tool_name,
            action=action,
            requested_scope=requested_scope,
            granted_scope=None if policy is None else policy.permission_scope,
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            requires_human_review=requires_human_review or risk_level is RuntimeRiskLevel.high,
            denial_reason=reason,
            policy_source=self.policy_source,
        )

    def _record(self, decision: PermissionDecision) -> None:
        if self.recorder is not None:
            self.recorder.record_permission_event(decision)


def load_tool_permissions(path: str | Path = DEFAULT_TOOL_PERMISSIONS_PATH) -> dict[str, ToolPermissionPolicy]:
    resolved = Path(path)
    items = _parse_tool_permission_yaml(resolved.read_text(encoding="utf-8"))
    policies = [ToolPermissionPolicy.model_validate(item) for item in items]
    return {policy.tool_name: policy for policy in policies}


def _parse_tool_permission_yaml(content: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line == "tools:":
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
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"').strip("'") for item in inner.split(",")]
    if value.casefold() == "true":
        return True
    if value.casefold() == "false":
        return False
    return value.strip('"').strip("'")


def _scope_allows(granted_scope: str, requested_scope: str) -> bool:
    if granted_scope == "*":
        return True
    return requested_scope == granted_scope or requested_scope.startswith(f"{granted_scope}:")


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
