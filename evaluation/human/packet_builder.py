from __future__ import annotations

import json
from pathlib import Path

from agent import SolutionInsightRequest, SolutionInsightService
from agent.observability import build_observation_snapshot
from evaluation.human.models import SolutionInsightHumanAnnotation, SolutionInsightHumanEvalPacket
from evaluation.llm.runner import load_eval_cases


EVALUATION_VERSION = "solution_insight_human_eval_v1"
PACKET_PATH = Path("data/evaluation/human/solution_insight_human_eval_packet.v1.jsonl")
ANNOTATION_TEMPLATE_PATH = Path("data/evaluation/human/solution_insight_human_eval_annotation_template.v1.jsonl")


def build_review_packets() -> list[SolutionInsightHumanEvalPacket]:
    cases = load_eval_cases()
    service = SolutionInsightService.from_defaults(enable_shadow_retrieval=True, llm_mode="deterministic")
    packets: list[SolutionInsightHumanEvalPacket] = []
    for case in cases:
        request = SolutionInsightRequest(
            user_query=case.user_query,
            industry=case.industry,
            company_size=case.company_size,
            current_systems=list(case.current_systems),
            target_goal=case.target_goal,
            constraints=list(case.constraints),
            enable_shadow_retrieval=True,
            llm_mode="deterministic",
        )
        response = service.generate_insight(request)
        snapshot = build_observation_snapshot(response)
        packets.append(
            SolutionInsightHumanEvalPacket(
                case_id=case.case_id,
                user_query_summary=_preview(case.user_query, limit=120),
                industry=case.industry,
                company_size=case.company_size,
                target_goal=case.target_goal,
                constraints=list(case.constraints),
                expected_focus_areas=list(case.expected_focus_areas),
                expected_fallback_behavior=case.expected_fallback_behavior,
                response_summary=snapshot.output_summary.requirement_summary,
                pain_points=list(response.pain_points),
                ai_opportunity_points=list(response.ai_opportunity_points),
                proposed_solution=_preview(response.proposed_solution, limit=240),
                evidence_count=len(response.evidence_items),
                evidence_titles=[item.title for item in response.evidence_items],
                fallback_recommended=response.fallback_recommended,
                fallback_reasons=list(response.fallback_reasons),
                human_confirmation_required=response.human_confirmation_required,
                skill_trace_summary={
                    "executed_skills": list(snapshot.skills.executed_skills),
                    "skill_count": snapshot.skills.skill_count,
                    "failed_skill_count": snapshot.skills.failed_skill_count,
                    "warnings": list(snapshot.skills.warnings),
                },
                provider_trace_summary={
                    "provider_names": list(snapshot.providers.provider_names),
                    "provider_success_count": snapshot.providers.provider_success_count,
                    "provider_failed_count": snapshot.providers.provider_failed_count,
                    "provider_skipped_count": snapshot.providers.provider_skipped_count,
                    "provider_warnings": list(snapshot.providers.provider_warnings),
                    "mock_data": snapshot.providers.mock_data,
                },
                observability_available=True,
                review_instructions=(
                    "请仅根据 formal evidence、fallback 表现和业务表达质量评分；"
                    "不要把 shadow debug 当作正式证据，也不要补充外部假设。"
                ),
            )
        )
    return packets


def build_annotation_template() -> list[SolutionInsightHumanAnnotation]:
    return [
        SolutionInsightHumanAnnotation(case_id=case.case_id)
        for case in load_eval_cases()
    ]


def packet_payload_text() -> str:
    return _serialize_jsonl([item.model_dump(mode="json") for item in build_review_packets()])


def annotation_template_text() -> str:
    return _serialize_jsonl([item.model_dump(mode="json") for item in build_annotation_template()])


def write_packet_outputs() -> dict[str, int]:
    PACKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    PACKET_PATH.write_text(packet_payload_text(), encoding="utf-8")
    ANNOTATION_TEMPLATE_PATH.write_text(annotation_template_text(), encoding="utf-8")
    return {
        "packet_case_count": len(build_review_packets()),
        "annotation_case_count": len(build_annotation_template()),
    }


def check_packet_outputs() -> tuple[bool, dict[str, object]]:
    expected_packet = packet_payload_text()
    expected_annotation = annotation_template_text()
    if not PACKET_PATH.exists() or not ANNOTATION_TEMPLATE_PATH.exists():
        return False, {"reason": "missing_outputs"}
    actual_packet = PACKET_PATH.read_text(encoding="utf-8")
    actual_annotation = ANNOTATION_TEMPLATE_PATH.read_text(encoding="utf-8")
    if actual_packet != expected_packet or actual_annotation != expected_annotation:
        return False, {"reason": "outputs_mismatch"}
    return True, {"reason": "outputs_match"}


def _serialize_jsonl(items: list[dict[str, object]]) -> str:
    return "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in items)


def _preview(value: str, *, limit: int) -> str:
    return " ".join(value.split())[:limit]
