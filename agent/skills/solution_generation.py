from __future__ import annotations

from typing import Any

from agent.skills.base import BaseSkill, SkillInput


class SolutionGenerationSkill(BaseSkill):
    name = "solution_generation"

    def __init__(self, *, service: Any) -> None:
        self._service = service

    def run(self, skill_input: SkillInput) -> tuple[str, dict[str, Any], list[str]]:
        request = skill_input.context["request"]
        effective_llm_mode = skill_input.context["effective_llm_mode"]
        formal_output = skill_input.previous_outputs["formal_retrieval"]
        fallback_output = skill_input.previous_outputs["fallback_assessment"]
        evidence_items = formal_output["evidence_items"]
        formal_evidence_payload = [item.model_dump(mode="json") for item in evidence_items]

        generation = self._service._generate_content(
            request=request,
            evidence_items=evidence_items,
            formal_evidence_payload=formal_evidence_payload,
            fallback_recommended=fallback_output["fallback_recommended"],
            llm_mode=effective_llm_mode,
        )
        output = {
            "requirement_summary": generation["requirement_summary"],
            "pain_points": generation["pain_points"],
            "ai_opportunity_points": generation["ai_opportunity_points"],
            "proposed_solution": generation["proposed_solution"],
            "response_note": generation["response_note"],
        }
        return "success", output, []
