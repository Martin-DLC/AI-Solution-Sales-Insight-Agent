from __future__ import annotations

from typing import Any

from agent.skills.base import BaseSkill, SkillInput


class RequirementUnderstandingSkill(BaseSkill):
    name = "requirement_understanding"

    def __init__(self, *, service: Any) -> None:
        self._service = service

    def run(self, skill_input: SkillInput) -> tuple[str, dict[str, Any], list[str]]:
        request = skill_input.context["request"]
        detected_goals: list[str] = []
        if request.target_goal:
            detected_goals.append(request.target_goal)
        text = request.user_query.casefold()
        if "转化" in text:
            detected_goals.append("提升转化")
        if any(keyword in text for keyword in ["客服", "成功", "支持", "服务"]):
            detected_goals.append("提升客户服务效率")

        output = {
            "requirement_summary": self._service._default_requirement_summary(request),
            "normalized_industry": request.industry.casefold() if request.industry else None,
            "detected_goals": _deduplicate(detected_goals),
            "detected_constraints": list(request.constraints),
            "query": self._service._build_query(request),
            "runtime_context": self._service._build_runtime_context(request),
        }
        return "success", output, []


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
