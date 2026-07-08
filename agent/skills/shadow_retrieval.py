from __future__ import annotations

from typing import Any

from agent.skills.base import BaseSkill, SkillInput


class ShadowRetrievalSkill(BaseSkill):
    name = "shadow_retrieval"

    def __init__(self, *, service: Any) -> None:
        self._service = service

    def run(self, skill_input: SkillInput) -> tuple[str, dict[str, Any], list[str]]:
        request = skill_input.context["request"]
        formal_output = skill_input.previous_outputs["formal_retrieval"]
        shadow_result = formal_output.get("shadow_result")

        if not self._service._should_run_shadow(request):
            return "skipped", {"shadow_retrieval_debug": None, "shadow_result": None}, ["shadow_disabled"]

        if shadow_result is None:
            return "failed", {"shadow_retrieval_debug": None, "shadow_result": None}, []

        shadow_debug = self._service._build_shadow_debug(shadow_result)
        return "success", {"shadow_retrieval_debug": shadow_debug, "shadow_result": shadow_result}, []
