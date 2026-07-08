from __future__ import annotations

import time
from typing import Any

from agent.models import SolutionInsightSkillTrace
from agent.skills.base import BaseSkill, SkillInput


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        if skill.name in self._skills:
            raise ValueError(f"Skill {skill.name!r} is already registered.")
        self._skills[skill.name] = skill

    def get(self, name: str) -> BaseSkill:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise KeyError(f"Unknown skill {name!r}.") from exc

    def list_skills(self) -> list[str]:
        return list(self._skills.keys())

    def execute(self, name: str, skill_input: SkillInput):
        return self.get(name).execute(skill_input)

    def execute_sequence(
        self,
        skill_names: list[str],
        skill_input: SkillInput,
    ) -> tuple[dict[str, dict[str, Any]], list[Any], SolutionInsightSkillTrace]:
        started_at = time.perf_counter()
        previous_outputs = dict(skill_input.previous_outputs)
        outputs = []
        warnings: list[str] = []

        for skill_name in skill_names:
            current_input = SkillInput(
                request_id=skill_input.request_id,
                user_query=skill_input.user_query,
                context=skill_input.context,
                previous_outputs=previous_outputs,
                config=skill_input.config,
            )
            result = self.execute(skill_name, current_input)
            outputs.append(result)
            previous_outputs[skill_name] = dict(result.output)
            warnings.extend(result.warnings)

        trace = SolutionInsightSkillTrace(
            request_id=skill_input.request_id,
            executed_skills=[result.skill_name for result in outputs],
            skill_count=len(outputs),
            failed_skill_count=sum(1 for result in outputs if result.status == "failed"),
            total_elapsed_ms=max(0, int((time.perf_counter() - started_at) * 1000)),
            warnings=_deduplicate(warnings),
        )
        return previous_outputs, outputs, trace


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
