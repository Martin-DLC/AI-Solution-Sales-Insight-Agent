from __future__ import annotations

from pathlib import Path

from pydantic import Field

from agent.recovery.models import ErrorType
from schemas.common_models import StrictBaseModel


DEFAULT_RECOVERY_POLICY_PATH = Path("config/recovery_policies.yaml")


class RecoveryPolicyConfig(StrictBaseModel):
    max_retry_count: int = 2
    retryable_error_types: list[ErrorType] = Field(default_factory=list)
    non_retryable_error_types: list[ErrorType] = Field(default_factory=list)
    backoff_strategy: str = "none"
    fallback_after_retries: bool = True


class RetryPolicy:
    def __init__(self, config: RecoveryPolicyConfig | None = None) -> None:
        self.config = config or load_recovery_policy()

    def can_retry(self, *, error_type: ErrorType | str, current_retry_count: int) -> bool:
        resolved = ErrorType(error_type)
        if resolved in self.config.non_retryable_error_types:
            return False
        if resolved not in self.config.retryable_error_types:
            return False
        return current_retry_count < self.config.max_retry_count

    def next_retry_count(self, current_retry_count: int) -> int:
        return current_retry_count + 1

    def should_fallback_after_retry(self, *, error_type: ErrorType | str, current_retry_count: int) -> bool:
        resolved = ErrorType(error_type)
        return (
            self.config.fallback_after_retries
            and resolved in self.config.retryable_error_types
            and current_retry_count >= self.config.max_retry_count
        )

    def explain(self, *, error_type: ErrorType | str, current_retry_count: int) -> str:
        resolved = ErrorType(error_type)
        if self.can_retry(error_type=resolved, current_retry_count=current_retry_count):
            return f"{resolved.value} is retryable; retry {current_retry_count + 1}/{self.config.max_retry_count}."
        if self.should_fallback_after_retry(error_type=resolved, current_retry_count=current_retry_count):
            return f"{resolved.value} exceeded retry limit; fallback is recommended."
        return f"{resolved.value} is not retryable under the current policy."


def load_recovery_policy(path: str | Path = DEFAULT_RECOVERY_POLICY_PATH) -> RecoveryPolicyConfig:
    payload = _parse_simple_yaml(Path(path).read_text(encoding="utf-8"))
    return RecoveryPolicyConfig.model_validate(payload)


def _parse_simple_yaml(content: str) -> dict[str, object]:
    payload: dict[str, object] = {}
    current_key: str | None = None
    for raw_line in content.splitlines():
        if not raw_line.strip() or raw_line.strip().startswith("#"):
            continue
        if raw_line.startswith("  - ") and current_key:
            payload.setdefault(current_key, [])
            assert isinstance(payload[current_key], list)
            payload[current_key].append(raw_line.strip()[2:].strip())
            continue
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        current_key = key.strip()
        stripped = value.strip()
        if stripped == "":
            payload[current_key] = []
        elif stripped.casefold() == "true":
            payload[current_key] = True
        elif stripped.casefold() == "false":
            payload[current_key] = False
        elif stripped.isdigit():
            payload[current_key] = int(stripped)
        else:
            payload[current_key] = stripped
    return payload
