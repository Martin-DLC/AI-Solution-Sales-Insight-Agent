from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from agent.models import SolutionInsightSkillOutput


@dataclass
class SkillInput:
    request_id: str
    user_query: str
    context: dict[str, Any] = field(default_factory=dict)
    previous_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)


class BaseSkill(ABC):
    name: str
    version: str = "v0.2"

    def execute(self, skill_input: SkillInput) -> SolutionInsightSkillOutput:
        started_at = time.perf_counter()
        try:
            status, output, warnings = self.run(skill_input)
            elapsed_ms = max(0, int((time.perf_counter() - started_at) * 1000))
            return SolutionInsightSkillOutput(
                skill_name=self.name,
                status=status,
                output=output,
                warnings=warnings,
                elapsed_ms=elapsed_ms,
            )
        except Exception as exc:  # pragma: no cover - registry-level behavior is covered too
            elapsed_ms = max(0, int((time.perf_counter() - started_at) * 1000))
            return SolutionInsightSkillOutput(
                skill_name=self.name,
                status="failed",
                output={},
                warnings=[],
                error_summary=_safe_error_summary(exc),
                elapsed_ms=elapsed_ms,
            )

    @abstractmethod
    def run(self, skill_input: SkillInput) -> tuple[str, dict[str, Any], list[str]]:
        raise NotImplementedError


def _safe_error_summary(error: Exception) -> str:
    message = str(error).strip() or error.__class__.__name__
    return f"{error.__class__.__name__}: {message.splitlines()[0][:240]}"
