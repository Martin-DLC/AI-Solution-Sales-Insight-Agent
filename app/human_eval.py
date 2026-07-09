from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from html import escape
from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from evaluation.human import storage as human_storage
from evaluation.human.aggregator import build_summary
from evaluation.human.models import SolutionInsightHumanAnnotation
from evaluation.human.storage import (
    load_effective_annotations,
    load_packet_map,
    load_packets,
    save_local_annotation,
)


router = APIRouter()


@router.get("/human-eval", response_class=HTMLResponse)
def human_eval_index() -> HTMLResponse:
    packets = load_packets()
    effective_annotations = load_effective_annotations()
    rows = []
    for packet in packets:
        annotation = effective_annotations.get(packet.case_id)
        completed = annotation is not None and annotation.reviewer_id is not None
        rows.append(
            "<tr>"
            f"<td><a href='/human-eval/{escape(packet.case_id)}'>{escape(packet.case_id)}</a></td>"
            f"<td>{escape(packet.industry or '-')}</td>"
            f"<td>{escape(packet.target_goal or '-')}</td>"
            f"<td>{'yes' if packet.expected_fallback_behavior else 'no'}</td>"
            f"<td>{'completed' if completed else 'pending'}</td>"
            "</tr>"
        )
    body = _page_wrapper(
        title="Human Review Cases",
        content=(
            "<p><strong>This is a local portfolio review tool. Do not expose it publicly.</strong></p>"
            "<p><a href='/human-eval/summary'>View local review summary</a></p>"
            "<table border='1' cellpadding='6' cellspacing='0'>"
            "<thead><tr><th>case_id</th><th>industry</th><th>target_goal</th><th>fallback expected</th><th>review_status</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        ),
    )
    return HTMLResponse(body)


@router.get("/human-eval/summary", response_class=HTMLResponse)
def human_eval_summary() -> HTMLResponse:
    summary = build_summary(annotations_path=human_storage.LOCAL_ANNOTATIONS_PATH)
    pending = summary.annotation_case_count - summary.completed_review_count
    aggregate_html = "<p>No completed local reviews yet.</p>"
    if summary.aggregate_scores is not None:
        aggregate_html = (
            "<ul>"
            f"<li>business_relevance_score: {summary.aggregate_scores.business_relevance_score}</li>"
            f"<li>evidence_grounding_score: {summary.aggregate_scores.evidence_grounding_score}</li>"
            f"<li>risk_fallback_score: {summary.aggregate_scores.risk_fallback_score}</li>"
            f"<li>actionability_score: {summary.aggregate_scores.actionability_score}</li>"
            f"<li>communication_quality_score: {summary.aggregate_scores.communication_quality_score}</li>"
            f"<li>product_thinking_score: {summary.aggregate_scores.product_thinking_score}</li>"
            f"<li>overall_human_score: {summary.aggregate_scores.overall_human_score}</li>"
            "</ul>"
        )
    body = _page_wrapper(
        title="Human Review Summary",
        content=(
            "<p><strong>This is a local portfolio review tool. Do not expose it publicly.</strong></p>"
            f"<p>local annotation file: <code>{escape(str(human_storage.LOCAL_ANNOTATIONS_PATH))}</code></p>"
            f"<p>human_review_status: <strong>{escape(summary.human_review_status)}</strong></p>"
            f"<p>total cases: {summary.annotation_case_count}</p>"
            f"<p>completed reviews: {summary.completed_review_count}</p>"
            f"<p>pending reviews: {pending}</p>"
            f"<p>pass_rate: {summary.pass_rate if summary.pass_rate is not None else 'n/a'}</p>"
            f"{aggregate_html}"
            "<p>This summary is based on local reviewer data, not the official benchmark artifact.</p>"
            "<p><a href='/human-eval'>Back to case list</a></p>"
        ),
    )
    return HTMLResponse(body)


@router.get("/human-eval/{case_id}", response_class=HTMLResponse)
def human_eval_case(case_id: str) -> HTMLResponse:
    packet = _require_packet(case_id)
    annotation = load_effective_annotations().get(case_id) or SolutionInsightHumanAnnotation(case_id=case_id)
    body = _page_wrapper(
        title=f"Human Review - {case_id}",
        content=_render_case_page(packet, annotation),
    )
    return HTMLResponse(body)


@router.post("/human-eval/{case_id}", response_class=HTMLResponse)
async def submit_human_eval(case_id: str, request: Request) -> HTMLResponse:
    _require_packet(case_id)
    form = await _read_form_fields(request)
    try:
        annotation = SolutionInsightHumanAnnotation(
            case_id=case_id,
            reviewer_id=_normalize_reviewer_id(form.get("reviewer_id")),
            reviewed_at=datetime.now(UTC).isoformat(),
            business_relevance_score=_score_value(form.get("business_relevance_score"), "business_relevance_score"),
            evidence_grounding_score=_score_value(form.get("evidence_grounding_score"), "evidence_grounding_score"),
            risk_fallback_score=_score_value(form.get("risk_fallback_score"), "risk_fallback_score"),
            actionability_score=_score_value(form.get("actionability_score"), "actionability_score"),
            communication_quality_score=_score_value(form.get("communication_quality_score"), "communication_quality_score"),
            product_thinking_score=_score_value(form.get("product_thinking_score"), "product_thinking_score"),
            pass_fail=_pass_fail_value(form.get("pass_fail")),
            strengths=_split_list_field(form.get("strengths")),
            weaknesses=_split_list_field(form.get("weaknesses")),
            suggested_improvements=_split_list_field(form.get("suggested_improvements")),
            reviewer_notes=_optional_text(form.get("reviewer_notes")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    save_local_annotation(annotation)
    return RedirectResponse(url=f"/human-eval/{escape(case_id)}?saved=1", status_code=status.HTTP_303_SEE_OTHER)


def _render_case_page(packet: Any, annotation: SolutionInsightHumanAnnotation) -> str:
    reviewer_value = annotation.reviewer_id or ""
    saved_note = "<p><em>Saved to local annotations file.</em></p>" if annotation.reviewer_id else ""
    return (
        "<p><strong>This is a local portfolio review tool. Do not expose it publicly.</strong></p>"
        "<p><a href='/human-eval'>Back to case list</a> | <a href='/human-eval/summary'>View summary</a></p>"
        f"{saved_note}"
        f"<h2>{escape(packet.case_id)}</h2>"
        "<h3>Case</h3>"
        f"<p>industry: {escape(packet.industry or '-')}</p>"
        f"<p>company_size: {escape(packet.company_size or '-')}</p>"
        f"<p>target_goal: {escape(packet.target_goal or '-')}</p>"
        f"<p>constraints: {escape(', '.join(packet.constraints) if packet.constraints else '-')}</p>"
        f"<p>expected_focus_areas: {escape(', '.join(packet.expected_focus_areas) if packet.expected_focus_areas else '-')}</p>"
        "<h3>Agent Output</h3>"
        f"<p>response_summary: {escape(packet.response_summary)}</p>"
        f"<p>pain_points: {escape(' | '.join(packet.pain_points) if packet.pain_points else '-')}</p>"
        f"<p>ai_opportunity_points: {escape(' | '.join(packet.ai_opportunity_points) if packet.ai_opportunity_points else '-')}</p>"
        f"<p>proposed_solution: {escape(packet.proposed_solution)}</p>"
        f"<p>evidence_titles: {escape(' | '.join(packet.evidence_titles) if packet.evidence_titles else '-')}</p>"
        f"<p>fallback_recommended: {packet.fallback_recommended}</p>"
        f"<p>fallback_reasons: {escape(' | '.join(packet.fallback_reasons) if packet.fallback_reasons else '-')}</p>"
        f"<p>skill_trace_summary: {escape(str(packet.skill_trace_summary))}</p>"
        f"<p>provider_trace_summary: {escape(str(packet.provider_trace_summary))}</p>"
        "<h3>Review Form</h3>"
        "<form method='post'>"
        f"{_input_row('reviewer_id', reviewer_value)}"
        f"{_score_row('business_relevance_score', annotation.business_relevance_score)}"
        f"{_score_row('evidence_grounding_score', annotation.evidence_grounding_score)}"
        f"{_score_row('risk_fallback_score', annotation.risk_fallback_score)}"
        f"{_score_row('actionability_score', annotation.actionability_score)}"
        f"{_score_row('communication_quality_score', annotation.communication_quality_score)}"
        f"{_score_row('product_thinking_score', annotation.product_thinking_score)}"
        f"{_pass_fail_row(annotation.pass_fail)}"
        f"{_textarea_row('strengths', annotation.strengths)}"
        f"{_textarea_row('weaknesses', annotation.weaknesses)}"
        f"{_textarea_row('suggested_improvements', annotation.suggested_improvements)}"
        f"{_textarea_row('reviewer_notes', annotation.reviewer_notes or '')}"
        "<button type='submit'>Save local annotation</button>"
        "</form>"
    )


def _page_wrapper(*, title: str, content: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{escape(title)}</title>"
        "<style>body{font-family:Arial,sans-serif;max-width:960px;margin:24px auto;padding:0 16px;line-height:1.5}"
        "table{width:100%;border-collapse:collapse}th,td{text-align:left}input,textarea,select{width:100%;max-width:760px;padding:6px;margin:4px 0}"
        "textarea{min-height:72px}label{font-weight:600;display:block;margin-top:10px}</style>"
        "</head><body>"
        f"<h1>{escape(title)}</h1>{content}</body></html>"
    )


def _input_row(name: str, value: str) -> str:
    return f"<label>{escape(name)}<input name='{escape(name)}' value='{escape(value)}'></label>"


def _score_row(name: str, value: int | None) -> str:
    current = "" if value is None else str(value)
    return (
        f"<label>{escape(name)}"
        f"<input type='number' min='1' max='5' name='{escape(name)}' value='{escape(current)}' required>"
        "</label>"
    )


def _pass_fail_row(value: str | None) -> str:
    selected_pass = " selected" if value == "pass" else ""
    selected_fail = " selected" if value == "fail" else ""
    return (
        "<label>pass_fail<select name='pass_fail' required>"
        "<option value=''>Select</option>"
        f"<option value='pass'{selected_pass}>pass</option>"
        f"<option value='fail'{selected_fail}>fail</option>"
        "</select></label>"
    )


def _textarea_row(name: str, value: list[str] | str) -> str:
    text = "\n".join(value) if isinstance(value, list) else value
    return f"<label>{escape(name)}<textarea name='{escape(name)}'>{escape(text)}</textarea></label>"


def _require_packet(case_id: str) -> Any:
    packet = load_packet_map().get(case_id)
    if packet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="human eval case not found")
    return packet


def _normalize_reviewer_id(value: Any) -> str:
    normalized = "" if value is None else str(value).strip()
    return normalized or "anonymous_reviewer"


async def _read_form_fields(request: Request) -> Mapping[str, str]:
    body = await request.body()
    text = body.decode("utf-8") if body else ""
    parsed = parse_qs(text, keep_blank_values=True, encoding="utf-8")
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _score_value(raw_value: Any, field_name: str) -> int:
    if raw_value is None or str(raw_value).strip() == "":
        raise ValueError(f"{field_name} is required.")
    value = int(str(raw_value).strip())
    if value < 1 or value > 5:
        raise ValueError(f"{field_name} must be between 1 and 5.")
    return value


def _pass_fail_value(raw_value: Any) -> str:
    value = "" if raw_value is None else str(raw_value).strip().casefold()
    if value not in {"pass", "fail"}:
        raise ValueError("pass_fail must be pass or fail.")
    return value


def _split_list_field(raw_value: Any) -> list[str]:
    if raw_value is None:
        return []
    text = str(raw_value).replace(",", "\n")
    values = [item.strip() for item in text.splitlines() if item.strip()]
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _optional_text(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    normalized = str(raw_value).strip()
    return normalized or None
