from __future__ import annotations

from typing import Any

from agent.skills.base import BaseSkill, SkillInput


class FallbackAssessmentSkill(BaseSkill):
    name = "fallback_assessment"

    def __init__(self, *, service: Any) -> None:
        self._service = service

    def run(self, skill_input: SkillInput) -> tuple[str, dict[str, Any], list[str]]:
        formal_output = skill_input.previous_outputs["formal_retrieval"]
        evidence_items = formal_output["evidence_items"]
        retrieval_error = formal_output.get("retrieval_error")
        shadow_result = formal_output.get("shadow_result")

        fallback_reasons = self._service._assess_fallback(
            evidence_items=evidence_items,
            retrieval_error=retrieval_error,
            shadow_result=shadow_result,
        )
        fallback_recommended = bool(fallback_reasons)
        output = {
            "fallback_recommended": fallback_recommended,
            "fallback_reasons": fallback_reasons,
            "human_confirmation_required": fallback_recommended,
            "evidence_completeness": "insufficient" if fallback_recommended else "sufficient_for_human_review",
        }
        return "success", output, []
