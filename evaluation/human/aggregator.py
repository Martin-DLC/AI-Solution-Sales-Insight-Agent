from __future__ import annotations

import json
from pathlib import Path

from dataio.jsonl_loader import load_jsonl_models
from evaluation.human.models import (
    SolutionInsightHumanAnnotation,
    SolutionInsightHumanEvalAggregateScores,
    SolutionInsightHumanEvalSummary,
)
from evaluation.human.packet_builder import ANNOTATION_TEMPLATE_PATH, EVALUATION_VERSION, PACKET_PATH


SUMMARY_PATH = Path("data/evaluation/human/solution_insight_human_eval_summary.v1.json")


def build_summary() -> SolutionInsightHumanEvalSummary:
    packet_count = _count_jsonl_rows(PACKET_PATH)
    annotations = load_jsonl_models(ANNOTATION_TEMPLATE_PATH, SolutionInsightHumanAnnotation)
    completed = [item for item in annotations if item.reviewer_id is not None]

    if not completed:
        return SolutionInsightHumanEvalSummary(
            evaluation_version=EVALUATION_VERSION,
            human_review_status="not_started",
            review_packet_case_count=packet_count,
            annotation_case_count=len(annotations),
            completed_review_count=0,
            aggregate_scores=None,
            pass_rate=None,
            limitations=[
                "no_human_scores_collected_yet",
                "annotation_template_ready",
                "future_reviews_required",
            ],
        )

    aggregate = SolutionInsightHumanEvalAggregateScores(
        business_relevance_score=_average(completed, "business_relevance_score"),
        evidence_grounding_score=_average(completed, "evidence_grounding_score"),
        risk_fallback_score=_average(completed, "risk_fallback_score"),
        actionability_score=_average(completed, "actionability_score"),
        communication_quality_score=_average(completed, "communication_quality_score"),
        product_thinking_score=_average(completed, "product_thinking_score"),
        overall_human_score=_average(completed, "overall_human_score"),
    )
    pass_count = sum(1 for item in completed if item.pass_fail == "pass")
    status = "completed" if len(completed) == len(annotations) else "in_progress"
    return SolutionInsightHumanEvalSummary(
        evaluation_version=EVALUATION_VERSION,
        human_review_status=status,
        review_packet_case_count=packet_count,
        annotation_case_count=len(annotations),
        completed_review_count=len(completed),
        aggregate_scores=aggregate,
        pass_rate=round(pass_count / len(completed), 4),
        strengths_summary=_merge_text_lists(completed, "strengths"),
        weaknesses_summary=_merge_text_lists(completed, "weaknesses"),
        suggested_improvements_summary=_merge_text_lists(completed, "suggested_improvements"),
        limitations=[] if status == "completed" else ["partial_human_reviews_collected"],
    )


def write_summary() -> SolutionInsightHumanEvalSummary:
    summary = build_summary()
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(
        json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def check_summary() -> tuple[bool, dict[str, object]]:
    if not SUMMARY_PATH.exists():
        return False, {"reason": "missing_summary"}
    expected = build_summary().model_dump(mode="json")
    actual = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    if actual != expected:
        return False, {"reason": "summary_mismatch"}
    return True, {"reason": "summary_matches"}


def _average(items: list[SolutionInsightHumanAnnotation], field_name: str) -> float:
    values = [float(getattr(item, field_name)) for item in items]
    return round(sum(values) / len(values), 4)


def _merge_text_lists(items: list[SolutionInsightHumanAnnotation], field_name: str) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in items:
        for value in getattr(item, field_name):
            if value not in seen:
                seen.add(value)
                merged.append(value)
    return merged


def _count_jsonl_rows(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
