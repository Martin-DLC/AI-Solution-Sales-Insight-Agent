from __future__ import annotations

from typing import Any

from agent.skills.base import BaseSkill, SkillInput


class FormalRetrievalSkill(BaseSkill):
    name = "formal_retrieval"

    def __init__(self, *, service: Any) -> None:
        self._service = service

    def run(self, skill_input: SkillInput) -> tuple[str, dict[str, Any], list[str]]:
        request = skill_input.context["request"]
        requirement_output = skill_input.previous_outputs["requirement_understanding"]
        runtime_context = requirement_output["runtime_context"]
        query = requirement_output["query"]
        filters = self._service._build_filters(runtime_context)
        retrieval_error: str | None = None
        formal_candidates: list[Any] = []

        try:
            if self._service._should_run_shadow(request):
                if self._service._shadow_service is None:
                    self._service._shadow_service = self._service._create_default_shadow_service()
                formal_candidates = self._service._shadow_service.retrieve(
                    query=query,
                    filters=filters,
                    runtime_context=runtime_context,
                    request_id=skill_input.request_id,
                )
                shadow_result = self._service._shadow_service.last_shadow_result
            else:
                formal_candidates = self._service._formal_retriever.retrieve(query=query, filters=filters, top_k=5)
                shadow_result = None
        except Exception as exc:
            retrieval_error = f"{exc.__class__.__name__}: {exc}"
            shadow_result = None

        evidence_items = self._service._build_evidence_items(formal_candidates)
        retrieval_debug = self._service._build_retrieval_debug(
            formal_candidates=formal_candidates,
            evidence_items=evidence_items,
            query_hash=self._service._build_query_hash(query),
        )
        output = {
            "formal_candidates": formal_candidates,
            "evidence_items": evidence_items,
            "retrieval_debug": retrieval_debug,
            "retrieval_error": retrieval_error,
            "shadow_result": shadow_result,
            "query_hash": retrieval_debug.query_hash,
        }
        return "success", output, []
