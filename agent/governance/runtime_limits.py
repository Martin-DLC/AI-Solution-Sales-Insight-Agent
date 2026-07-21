from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator

from schemas.common_models import StrictBaseModel


DEFAULT_RUNTIME_LIMITS_PATH = Path("config/runtime_limits.yaml")


class RuntimeLimits(StrictBaseModel):
    max_execution_steps: int = 50
    max_consecutive_failures: int = 3
    max_tool_failures: int = 3
    max_task_duration_seconds: int = 120

    @field_validator("*")
    @classmethod
    def limits_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Runtime limits must be positive integers.")
        return value


def load_runtime_limits(path: str | Path = DEFAULT_RUNTIME_LIMITS_PATH) -> RuntimeLimits:
    resolved = Path(path)
    if not resolved.exists():
        return RuntimeLimits()
    payload: dict[str, int] = {}
    for raw_line in resolved.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        payload[key] = int(value)
    return RuntimeLimits.model_validate(payload)
