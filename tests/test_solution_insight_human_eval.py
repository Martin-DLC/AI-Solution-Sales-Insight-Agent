from __future__ import annotations

import json
from pathlib import Path

from dataio.jsonl_loader import load_jsonl_models
from evaluation.human import (
    ANNOTATION_TEMPLATE_PATH,
    PACKET_PATH,
    SUMMARY_PATH,
    SolutionInsightHumanAnnotation,
    build_review_packets,
    build_summary,
    check_packet_outputs,
    check_summary,
    write_packet_outputs,
    write_summary,
)


def test_human_eval_packet_has_twelve_cases() -> None:
    assert len(build_review_packets()) == 12


def test_annotation_template_has_twelve_cases() -> None:
    from evaluation.human import build_annotation_template

    assert len(build_annotation_template()) == 12


def test_case_ids_are_unique_and_match_between_packet_and_template() -> None:
    from evaluation.human import build_annotation_template

    packet_ids = [item.case_id for item in build_review_packets()]
    annotation_ids = [item.case_id for item in build_annotation_template()]

    assert len(set(packet_ids)) == 12
    assert packet_ids == annotation_ids


def test_annotation_template_defaults_to_empty_human_fields() -> None:
    from evaluation.human import build_annotation_template

    sample = build_annotation_template()[0]

    assert sample.reviewer_id is None
    assert sample.reviewed_at is None
    assert sample.business_relevance_score is None
    assert sample.overall_human_score is None
    assert sample.pass_fail is None
    assert sample.strengths == []


def test_packet_does_not_contain_api_key_traceback_or_gold() -> None:
    dumped = json.dumps([item.model_dump(mode="json") for item in build_review_packets()], ensure_ascii=False)

    assert "api_key" not in dumped.casefold()
    assert "traceback" not in dumped.casefold()
    assert "gold" not in dumped.casefold()


def test_human_evaluation_guide_exists_and_mentions_six_dimensions() -> None:
    guide = Path("docs/HUMAN_EVALUATION_GUIDE.md").read_text(encoding="utf-8")

    assert "Business Relevance" in guide
    assert "Evidence Grounding" in guide
    assert "Risk & Fallback Appropriateness" in guide
    assert "Actionability" in guide
    assert "Communication Quality" in guide
    assert "Product Thinking" in guide


def test_write_and_check_packet_outputs(tmp_path: Path, monkeypatch) -> None:
    packet_path = tmp_path / "packet.jsonl"
    annotation_path = tmp_path / "annotation.jsonl"
    monkeypatch.setattr("evaluation.human.packet_builder.PACKET_PATH", packet_path)
    monkeypatch.setattr("evaluation.human.packet_builder.ANNOTATION_TEMPLATE_PATH", annotation_path)

    payload = write_packet_outputs()
    matches, details = check_packet_outputs()

    assert payload["packet_case_count"] == 12
    assert packet_path.exists()
    assert annotation_path.exists()
    assert matches is True
    assert details["reason"] == "outputs_match"


def test_summarize_empty_annotations_does_not_fabricate_scores(tmp_path: Path, monkeypatch) -> None:
    packet_path = tmp_path / "packet.jsonl"
    annotation_path = tmp_path / "annotation.jsonl"
    summary_path = tmp_path / "summary.json"
    monkeypatch.setattr("evaluation.human.packet_builder.PACKET_PATH", packet_path)
    monkeypatch.setattr("evaluation.human.packet_builder.ANNOTATION_TEMPLATE_PATH", annotation_path)
    monkeypatch.setattr("evaluation.human.aggregator.PACKET_PATH", packet_path)
    monkeypatch.setattr("evaluation.human.aggregator.ANNOTATION_TEMPLATE_PATH", annotation_path)
    monkeypatch.setattr("evaluation.human.aggregator.SUMMARY_PATH", summary_path)

    write_packet_outputs()
    summary = write_summary()
    matches, details = check_summary()

    assert summary.human_review_status == "not_started"
    assert summary.completed_review_count == 0
    assert summary.aggregate_scores is None
    assert summary.pass_rate is None
    assert matches is True
    assert details["reason"] == "summary_matches"


def test_aggregator_computes_means_for_scored_annotations(tmp_path: Path, monkeypatch) -> None:
    packet_path = tmp_path / "packet.jsonl"
    annotation_path = tmp_path / "annotation.jsonl"
    summary_path = tmp_path / "summary.json"
    monkeypatch.setattr("evaluation.human.packet_builder.PACKET_PATH", packet_path)
    monkeypatch.setattr("evaluation.human.packet_builder.ANNOTATION_TEMPLATE_PATH", annotation_path)
    monkeypatch.setattr("evaluation.human.aggregator.PACKET_PATH", packet_path)
    monkeypatch.setattr("evaluation.human.aggregator.ANNOTATION_TEMPLATE_PATH", annotation_path)
    monkeypatch.setattr("evaluation.human.aggregator.SUMMARY_PATH", summary_path)

    write_packet_outputs()
    annotations = load_jsonl_models(annotation_path, SolutionInsightHumanAnnotation)
    scored = [
        annotation.model_copy(
            update={
                "reviewer_id": "reviewer-1",
                "reviewed_at": "2026-07-08T00:00:00Z",
                "business_relevance_score": 4,
                "evidence_grounding_score": 5,
                "risk_fallback_score": 4,
                "actionability_score": 3,
                "communication_quality_score": 4,
                "product_thinking_score": 5,
                "pass_fail": "pass",
                "strengths": ["evidence grounding"],
                "weaknesses": ["actionability"],
                "suggested_improvements": ["add clearer next step"],
            }
        )
        for annotation in annotations
    ]
    annotation_path.write_text(
        "".join(json.dumps(item.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n" for item in scored),
        encoding="utf-8",
    )

    summary = build_summary()

    assert summary.human_review_status == "completed"
    assert summary.completed_review_count == 12
    assert summary.aggregate_scores is not None
    assert summary.aggregate_scores.business_relevance_score == 4.0
    assert summary.aggregate_scores.overall_human_score == 83.33

