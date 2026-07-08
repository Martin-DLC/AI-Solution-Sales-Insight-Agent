from __future__ import annotations

from typing import Any

from agent.context_providers import ProviderInput
from agent.skills.base import BaseSkill, SkillInput


class EnterpriseContextSkill(BaseSkill):
    name = "enterprise_context"

    def __init__(self, *, service: Any) -> None:
        self._service = service

    def run(self, skill_input: SkillInput) -> tuple[str, dict[str, Any], list[str]]:
        request = skill_input.context["request"]
        provider_input = ProviderInput(
            company_id=request.company_id,
            industry=getattr(request, "industry", None),
            current_systems=list(getattr(request, "current_systems", [])),
            request_id=skill_input.request_id,
        )
        provider_results = self._service._context_provider_registry.fetch_all(provider_input)
        provider_warnings = _deduplicate_warnings(
            warning for result in provider_results for warning in result.warnings
        )
        provider_payloads = {
            result.provider_name: result.data or {}
            for result in provider_results
            if result.status == "success"
        }
        provider_success_count = sum(1 for result in provider_results if result.status == "success")
        provider_failed_count = sum(1 for result in provider_results if result.status == "failed")
        provider_skipped_count = sum(1 for result in provider_results if result.status == "skipped")

        if not request.company_id:
            return "skipped", {"enterprise_context": None}, provider_warnings or ["company_id_missing"]

        record = self._service._enterprise_context_client.get_company_context(request.company_id)
        if record is None:
            return "skipped", {"enterprise_context": None}, provider_warnings or ["company_id_not_found"]

        output = {
            "enterprise_context": {
                "company_profile": record.company_profile.model_dump(mode="json"),
                "crm_context": provider_payloads.get("crm_context", {}),
                "ticket_context": provider_payloads.get("ticket_context", {}),
                "bi_context": provider_payloads.get("bi_context", {}),
                "knowledge_context": provider_payloads.get("knowledge_context", {}),
                "context_source": record.context_source,
                "mock_data": record.mock_data,
                "provider_results": [result.model_dump(mode="json") for result in provider_results],
                "provider_success_count": provider_success_count,
                "provider_failed_count": provider_failed_count,
                "provider_skipped_count": provider_skipped_count,
                "provider_warnings": provider_warnings,
            }
        }
        return "success", output, provider_warnings


def _deduplicate_warnings(warnings: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for warning in warnings:
        if warning not in seen:
            seen.add(warning)
            result.append(warning)
    return result
