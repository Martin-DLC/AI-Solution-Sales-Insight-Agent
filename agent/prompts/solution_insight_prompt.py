from __future__ import annotations

import json

from agent.models import SolutionInsightRequest
from agent.workflow_c.failures import redact_secrets
from llm import LLMMessage, LLMRole


def build_solution_insight_messages(
    *,
    request: SolutionInsightRequest,
    formal_evidence_payload: list[dict[str, str]],
) -> list[LLMMessage]:
    system_prompt = (
        "You are an AI solution sales insight assistant. "
        "Return only a valid JSON object. "
        "Use only the formal evidence items provided. "
        "Do not use shadow retrieval diagnostics as evidence. "
        "Do not invent customer facts, ROI numbers, or unsupported implementation claims. "
        "If the evidence is insufficient, say so explicitly and recommend human confirmation."
    )
    user_payload = {
        "request": {
            "user_query": request.user_query,
            "industry": request.industry,
            "company_size": request.company_size,
            "current_systems": request.current_systems,
            "target_goal": request.target_goal,
            "constraints": request.constraints,
        },
        "required_output_fields": [
            "requirement_summary",
            "pain_points",
            "ai_opportunity_points",
            "proposed_solution",
            "response_note",
        ],
        "formal_evidence_items": formal_evidence_payload,
        "rules": [
            "Do not mention or cite shadow retrieval diagnostics.",
            "If evidence is insufficient, say the evidence is insufficient.",
            "Do not fabricate missing business details.",
        ],
    }
    return [
        LLMMessage(role=LLMRole.system, content=system_prompt),
        LLMMessage(
            role=LLMRole.user,
            content=json.dumps(user_payload, ensure_ascii=False, indent=2),
        ),
    ]


def sanitize_prompt_text(value: str) -> str:
    return redact_secrets(value)
