from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from agent.models import SolutionInsightResponse
from evaluation.llm.models import REQUIRED_RESPONSE_SECTIONS, SolutionInsightEvalCase, SolutionInsightEvalCaseResult, SolutionInsightEvalScores


_CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]")
_ROI_PATTERN = re.compile(r"(roi|回报|收益|提升)\s*[:：]?\s*\d+%?", re.IGNORECASE)
_GUARANTEE_PATTERN = re.compile(r"(保证|确保|100%|一定会|必然)", re.IGNORECASE)
_BUZZWORD_PATTERN = re.compile(r"(赋能|抓手|闭环|全链路)")


def evaluate_solution_insight_response(
    case: SolutionInsightEvalCase,
    response_payload: SolutionInsightResponse | dict[str, Any],
    *,
    provider: str,
    model_mode: str,
) -> SolutionInsightEvalCaseResult:
    payload, response, validation_error = _coerce_response_payload(response_payload)
    schema_score, schema_reasons, schema_is_valid = _score_schema_validity(payload, validation_error)
    section_score, section_reasons = _score_section_completeness(case, payload)
    evidence_score, evidence_reasons = _score_evidence_grounding(payload, response)
    hallucination_score, hallucination_reasons, hallucination_detected = _score_hallucination_risk(case, payload)
    fallback_score, fallback_reasons, fallback_alignment_ok = _score_fallback_alignment(case, payload)
    clarity_score, clarity_reasons = _score_chinese_business_clarity(payload)

    overall_score = schema_score + section_score + evidence_score + hallucination_score + fallback_score + clarity_score
    response_snapshot = _build_response_snapshot(payload)

    return SolutionInsightEvalCaseResult(
        case_id=case.case_id,
        provider=provider,
        model_mode=model_mode,
        scores=SolutionInsightEvalScores(
            schema_validity=schema_score,
            section_completeness=section_score,
            evidence_grounding=evidence_score,
            hallucination_risk=hallucination_score,
            fallback_alignment=fallback_score,
            chinese_business_clarity=clarity_score,
            overall_score=overall_score,
        ),
        score_reasons={
            "schema_validity": schema_reasons,
            "section_completeness": section_reasons,
            "evidence_grounding": evidence_reasons,
            "hallucination_risk": hallucination_reasons,
            "fallback_alignment": fallback_reasons,
            "chinese_business_clarity": clarity_reasons,
        },
        schema_is_valid=schema_is_valid,
        hallucination_risk_detected=hallucination_detected,
        fallback_alignment_ok=fallback_alignment_ok,
        response_snapshot=response_snapshot,
    )


def _coerce_response_payload(
    response_payload: SolutionInsightResponse | dict[str, Any],
) -> tuple[dict[str, Any], SolutionInsightResponse | None, ValidationError | None]:
    if isinstance(response_payload, SolutionInsightResponse):
        payload = response_payload.model_dump(mode="json")
        return payload, response_payload, None
    payload = dict(response_payload)
    try:
        response = SolutionInsightResponse.model_validate(payload)
    except ValidationError as exc:
        return payload, None, exc
    return response.model_dump(mode="json"), response, None


def _score_schema_validity(
    payload: dict[str, Any],
    validation_error: ValidationError | None,
) -> tuple[int, list[str], bool]:
    present_required = sum(1 for field in REQUIRED_RESPONSE_SECTIONS if field in payload)
    if validation_error is None and present_required == len(REQUIRED_RESPONSE_SECTIONS):
        return 20, ["All required response fields are present and valid."], True
    reasons = [f"Detected {present_required}/{len(REQUIRED_RESPONSE_SECTIONS)} required top-level fields."]
    if validation_error is not None:
        reasons.extend(_summarize_validation_error(validation_error))
    score = round(20 * (present_required / len(REQUIRED_RESPONSE_SECTIONS)))
    return score, reasons, False


def _score_section_completeness(
    case: SolutionInsightEvalCase,
    payload: dict[str, Any],
) -> tuple[int, list[str]]:
    completed = 0
    reasons: list[str] = []
    for section in case.required_output_sections:
        value = payload.get(section)
        is_complete = _value_is_non_empty(value)
        if is_complete:
            completed += 1
        else:
            reasons.append(f"Section {section!r} is empty or missing.")
    if not reasons:
        reasons.append("All required sections are non-empty.")
    score = round(15 * (completed / max(1, len(case.required_output_sections))))
    return score, reasons


def _score_evidence_grounding(
    payload: dict[str, Any],
    response: SolutionInsightResponse | None,
) -> tuple[int, list[str]]:
    reasons: list[str] = []
    evidence_items = payload.get("evidence_items") or []
    proposed_solution = str(payload.get("proposed_solution") or "")
    shadow_debug = payload.get("shadow_retrieval_debug")
    retrieval_debug = payload.get("retrieval_debug") or {}

    if not evidence_items:
        fallback_recommended = bool(payload.get("fallback_recommended"))
        if fallback_recommended:
            return 20, ["No formal evidence returned and fallback was correctly triggered."]
        return 0, ["No formal evidence returned while fallback was not triggered."]

    title_matches = 0
    for item in evidence_items:
        title = str(item.get("title") or "")
        if title and title in proposed_solution:
            title_matches += 1
    if title_matches:
        reasons.append(f"Proposed solution references {title_matches} formal evidence title(s).")
    else:
        reasons.append("Proposed solution does not explicitly mention any formal evidence title.")

    evidence_count = len(evidence_items)
    debug_count = int(retrieval_debug.get("evidence_count") or 0)
    if evidence_count == debug_count:
        reasons.append("Formal evidence count matches retrieval_debug.evidence_count.")
    else:
        reasons.append("Formal evidence count does not match retrieval_debug.evidence_count.")

    if shadow_debug is not None and "shadow" not in proposed_solution.casefold():
        reasons.append("Shadow debug exists but is not referenced in the formal solution text.")

    score = 0
    if title_matches:
        score += 10
    if evidence_count == debug_count and evidence_count > 0:
        score += 5
    if shadow_debug is None or "shadow" not in proposed_solution.casefold():
        score += 5
    return score, reasons


def _score_hallucination_risk(
    case: SolutionInsightEvalCase,
    payload: dict[str, Any],
) -> tuple[int, list[str], bool]:
    text = _build_generated_claim_text(payload)
    reasons: list[str] = []
    violations: list[str] = []

    for claim in case.forbidden_claims:
        if claim.casefold() in text.casefold():
            violations.append(claim)

    if _ROI_PATTERN.search(text):
        violations.append("roi_or_numeric_gain_claim")
    if _GUARANTEE_PATTERN.search(text):
        violations.append("guaranteed_outcome_claim")

    if violations:
        reasons.append(f"Detected forbidden or risky claims: {', '.join(sorted(set(violations)))}.")
        return 0, reasons, True

    reasons.append("No forbidden claims or deterministic hallucination patterns detected.")
    return 20, reasons, False


def _score_fallback_alignment(
    case: SolutionInsightEvalCase,
    payload: dict[str, Any],
) -> tuple[int, list[str], bool]:
    fallback_recommended = bool(payload.get("fallback_recommended"))
    human_confirmation_required = bool(payload.get("human_confirmation_required"))
    fallback_reasons = payload.get("fallback_reasons") or []
    reasons: list[str] = []

    if case.expected_fallback_behavior:
        score = 0
        if fallback_recommended:
            score += 10
            reasons.append("Fallback recommendation matches expected behavior.")
        else:
            reasons.append("Expected fallback_recommended=true but response returned false.")
        if human_confirmation_required:
            score += 3
            reasons.append("Human confirmation is correctly required.")
        else:
            reasons.append("Expected human_confirmation_required=true for fallback case.")
        if fallback_reasons:
            score += 2
            reasons.append("Fallback reasons are present.")
        else:
            reasons.append("Fallback reasons are missing.")
        return score, reasons, score == 15

    if fallback_recommended:
        return 0, ["Expected fallback_recommended=false but response returned true."], False
    return 15, ["Fallback stayed off as expected."], True


def _score_chinese_business_clarity(payload: dict[str, Any]) -> tuple[int, list[str]]:
    text = _build_response_text(payload)
    pain_points = payload.get("pain_points") or []
    ai_opportunity_points = payload.get("ai_opportunity_points") or []
    proposed_solution = str(payload.get("proposed_solution") or "")
    reasons: list[str] = []
    score = 0

    if _CHINESE_PATTERN.search(text):
        score += 3
        reasons.append("Response includes Chinese business phrasing.")
    else:
        reasons.append("Response does not contain enough Chinese content.")

    if pain_points and ai_opportunity_points:
        score += 4
        reasons.append("Pain points and AI opportunity points are both present.")
    else:
        reasons.append("Pain points or AI opportunity points are incomplete.")

    if 20 <= len(proposed_solution) <= 240:
        score += 2
        reasons.append("Proposed solution length is concise and readable.")
    else:
        reasons.append("Proposed solution length is outside the preferred range.")

    if len(_BUZZWORD_PATTERN.findall(text)) <= 2:
        score += 1
        reasons.append("Response avoids excessive generic buzzwords.")
    else:
        reasons.append("Response uses too many generic buzzwords.")

    return score, reasons


def _build_response_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    evidence_items = payload.get("evidence_items") or []
    shadow_debug = payload.get("shadow_retrieval_debug")
    retrieval_debug = payload.get("retrieval_debug") or {}
    return {
        "requirement_summary": payload.get("requirement_summary"),
        "pain_points": payload.get("pain_points") or [],
        "ai_opportunity_points": payload.get("ai_opportunity_points") or [],
        "proposed_solution": payload.get("proposed_solution"),
        "evidence_titles": [item.get("title") for item in evidence_items],
        "evidence_count": len(evidence_items),
        "evidence_completeness": payload.get("evidence_completeness"),
        "fallback_recommended": payload.get("fallback_recommended"),
        "fallback_reasons": payload.get("fallback_reasons") or [],
        "human_confirmation_required": payload.get("human_confirmation_required"),
        "formal_candidate_count": retrieval_debug.get("formal_candidate_count"),
        "shadow_debug_present": shadow_debug is not None,
    }


def _value_is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _build_response_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("requirement_summary", "proposed_solution", "response_note"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value)
    for list_key in ("pain_points", "ai_opportunity_points", "fallback_reasons"):
        value = payload.get(list_key) or []
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    return "\n".join(parts)


def _build_generated_claim_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("proposed_solution", "response_note"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value)
    for list_key in ("pain_points", "ai_opportunity_points"):
        value = payload.get(list_key) or []
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    return "\n".join(parts)


def _summarize_validation_error(validation_error: ValidationError) -> list[str]:
    reasons: list[str] = []
    for item in validation_error.errors():
        location = ".".join(str(part) for part in item.get("loc", ()))
        message = item.get("msg", "validation error")
        reasons.append(f"{location}: {message}" if location else message)
    return reasons
