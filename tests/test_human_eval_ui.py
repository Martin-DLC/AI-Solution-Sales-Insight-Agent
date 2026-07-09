from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def _write_temp_human_eval_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    packet_path = tmp_path / "packet.jsonl"
    template_path = tmp_path / "template.jsonl"
    local_path = tmp_path / "annotations.local.jsonl"
    packet_rows = []
    template_rows = []
    for index in range(1, 13):
        case_id = f"CASE-{index:03d}"
        packet_rows.append(
            {
                "case_id": case_id,
                "user_query_summary": f"query {index}",
                "industry": "SaaS",
                "company_size": "中型",
                "target_goal": "goal",
                "constraints": ["c1"],
                "expected_focus_areas": ["focus"],
                "expected_fallback_behavior": True,
                "response_summary": "response",
                "pain_points": ["pain"],
                "ai_opportunity_points": ["opportunity"],
                "proposed_solution": "solution",
                "evidence_count": 2,
                "evidence_titles": ["e1", "e2"],
                "fallback_recommended": True,
                "fallback_reasons": ["boundary_status_blocked_or_unknown"],
                "human_confirmation_required": True,
                "skill_trace_summary": {"skill_count": 6},
                "provider_trace_summary": {"provider_success_count": 4},
                "observability_available": True,
                "review_instructions": "review",
            }
        )
        template_rows.append(
            {
                "case_id": case_id,
                "reviewer_id": None,
                "reviewed_at": None,
                "business_relevance_score": None,
                "evidence_grounding_score": None,
                "risk_fallback_score": None,
                "actionability_score": None,
                "communication_quality_score": None,
                "product_thinking_score": None,
                "overall_human_score": None,
                "pass_fail": None,
                "strengths": [],
                "weaknesses": [],
                "suggested_improvements": [],
                "reviewer_notes": None,
            }
        )
    packet_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in packet_rows), encoding="utf-8")
    template_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in template_rows), encoding="utf-8")
    return packet_path, template_path, local_path


def test_human_eval_index_returns_twelve_cases(tmp_path: Path, monkeypatch) -> None:
    packet_path, template_path, local_path = _write_temp_human_eval_files(tmp_path)
    monkeypatch.setattr("evaluation.human.storage.PACKET_PATH", packet_path)
    monkeypatch.setattr("evaluation.human.storage.ANNOTATION_TEMPLATE_PATH", template_path)
    monkeypatch.setattr("evaluation.human.storage.LOCAL_ANNOTATIONS_PATH", local_path)

    client = TestClient(app)
    response = client.get("/human-eval")

    assert response.status_code == 200
    assert response.text.count("/human-eval/CASE-") == 12


def test_human_eval_case_returns_200(tmp_path: Path, monkeypatch) -> None:
    packet_path, template_path, local_path = _write_temp_human_eval_files(tmp_path)
    monkeypatch.setattr("evaluation.human.storage.PACKET_PATH", packet_path)
    monkeypatch.setattr("evaluation.human.storage.ANNOTATION_TEMPLATE_PATH", template_path)
    monkeypatch.setattr("evaluation.human.storage.LOCAL_ANNOTATIONS_PATH", local_path)

    client = TestClient(app)
    response = client.get("/human-eval/CASE-001")

    assert response.status_code == 200
    assert "business_relevance_score" in response.text


def test_unknown_case_returns_404(tmp_path: Path, monkeypatch) -> None:
    packet_path, template_path, local_path = _write_temp_human_eval_files(tmp_path)
    monkeypatch.setattr("evaluation.human.storage.PACKET_PATH", packet_path)
    monkeypatch.setattr("evaluation.human.storage.ANNOTATION_TEMPLATE_PATH", template_path)
    monkeypatch.setattr("evaluation.human.storage.LOCAL_ANNOTATIONS_PATH", local_path)

    client = TestClient(app)
    response = client.get("/human-eval/UNKNOWN")

    assert response.status_code == 404


def test_post_valid_review_saves_local_annotation(tmp_path: Path, monkeypatch) -> None:
    packet_path, template_path, local_path = _write_temp_human_eval_files(tmp_path)
    monkeypatch.setattr("evaluation.human.storage.PACKET_PATH", packet_path)
    monkeypatch.setattr("evaluation.human.storage.ANNOTATION_TEMPLATE_PATH", template_path)
    monkeypatch.setattr("evaluation.human.storage.LOCAL_ANNOTATIONS_PATH", local_path)

    client = TestClient(app)
    response = client.post(
        "/human-eval/CASE-001",
        data={
            "reviewer_id": "reviewer-1",
            "business_relevance_score": "4",
            "evidence_grounding_score": "5",
            "risk_fallback_score": "4",
            "actionability_score": "3",
            "communication_quality_score": "4",
            "product_thinking_score": "5",
            "pass_fail": "pass",
            "strengths": "good evidence",
            "weaknesses": "could be more specific",
            "suggested_improvements": "add next steps",
            "reviewer_notes": "solid",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert local_path.exists()
    content = local_path.read_text(encoding="utf-8")
    assert "reviewer-1" in content
    assert "83.33" in content


def test_post_invalid_score_returns_422(tmp_path: Path, monkeypatch) -> None:
    packet_path, template_path, local_path = _write_temp_human_eval_files(tmp_path)
    monkeypatch.setattr("evaluation.human.storage.PACKET_PATH", packet_path)
    monkeypatch.setattr("evaluation.human.storage.ANNOTATION_TEMPLATE_PATH", template_path)
    monkeypatch.setattr("evaluation.human.storage.LOCAL_ANNOTATIONS_PATH", local_path)

    client = TestClient(app)
    response = client.post(
        "/human-eval/CASE-001",
        data={
            "reviewer_id": "reviewer-1",
            "business_relevance_score": "6",
            "evidence_grounding_score": "5",
            "risk_fallback_score": "4",
            "actionability_score": "3",
            "communication_quality_score": "4",
            "product_thinking_score": "5",
            "pass_fail": "pass",
        },
    )

    assert response.status_code == 422


def test_summary_counts_completed_reviews(tmp_path: Path, monkeypatch) -> None:
    packet_path, template_path, local_path = _write_temp_human_eval_files(tmp_path)
    monkeypatch.setattr("evaluation.human.storage.PACKET_PATH", packet_path)
    monkeypatch.setattr("evaluation.human.storage.ANNOTATION_TEMPLATE_PATH", template_path)
    monkeypatch.setattr("evaluation.human.storage.LOCAL_ANNOTATIONS_PATH", local_path)
    monkeypatch.setattr("evaluation.human.aggregator.PACKET_PATH", packet_path)

    local_path.write_text(
        json.dumps(
            {
                "case_id": "CASE-001",
                "reviewer_id": "reviewer-1",
                "reviewed_at": "2026-07-09T00:00:00+00:00",
                "business_relevance_score": 4,
                "evidence_grounding_score": 5,
                "risk_fallback_score": 4,
                "actionability_score": 3,
                "communication_quality_score": 4,
                "product_thinking_score": 5,
                "overall_human_score": 83.33,
                "pass_fail": "pass",
                "strengths": [],
                "weaknesses": [],
                "suggested_improvements": [],
                "reviewer_notes": None,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.get("/human-eval/summary")

    assert response.status_code == 200
    assert "completed reviews: 1" in response.text


def test_local_annotations_do_not_modify_template(tmp_path: Path, monkeypatch) -> None:
    packet_path, template_path, local_path = _write_temp_human_eval_files(tmp_path)
    before = template_path.read_text(encoding="utf-8")
    monkeypatch.setattr("evaluation.human.storage.PACKET_PATH", packet_path)
    monkeypatch.setattr("evaluation.human.storage.ANNOTATION_TEMPLATE_PATH", template_path)
    monkeypatch.setattr("evaluation.human.storage.LOCAL_ANNOTATIONS_PATH", local_path)

    client = TestClient(app)
    client.post(
        "/human-eval/CASE-001",
        data={
            "reviewer_id": "reviewer-1",
            "business_relevance_score": "4",
            "evidence_grounding_score": "5",
            "risk_fallback_score": "4",
            "actionability_score": "3",
            "communication_quality_score": "4",
            "product_thinking_score": "5",
            "pass_fail": "pass",
        },
    )

    assert template_path.read_text(encoding="utf-8") == before
