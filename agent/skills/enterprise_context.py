from __future__ import annotations

from typing import Any

from agent.skills.base import BaseSkill, SkillInput


class EnterpriseContextSkill(BaseSkill):
    name = "enterprise_context"

    def __init__(self, *, service: Any) -> None:
        self._service = service

    def run(self, skill_input: SkillInput) -> tuple[str, dict[str, Any], list[str]]:
        request = skill_input.context["request"]
        if not request.company_id:
            return "skipped", {"enterprise_context": None}, ["company_id_missing"]

        record = self._service._enterprise_context_client.get_company_context(request.company_id)
        if record is None:
            return "skipped", {"enterprise_context": None}, ["company_id_not_found"]

        output = {
            "enterprise_context": {
                "company_profile": record.company_profile.model_dump(mode="json"),
                "crm_context": record.crm_context.model_dump(mode="json"),
                "ticket_context": record.ticket_context.model_dump(mode="json"),
                "bi_context": record.bi_context.model_dump(mode="json"),
                "knowledge_context": record.knowledge_context.model_dump(mode="json"),
                "context_source": record.context_source,
                "mock_data": record.mock_data,
            }
        }
        return "success", output, []
