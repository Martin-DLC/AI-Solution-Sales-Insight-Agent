from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import (
    DEAL_SCORE_WEIGHTS,
    DealScoreDimensionName,
    SalesInsightReport,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dev_01_full_report.json"


def load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_full_fixture_loads_as_sales_insight_report() -> None:
    report = SalesInsightReport.model_validate(load_fixture())

    assert report.case_id == "DEV-01"
    assert report.deal_score.total_score == 68


def test_model_dump_json_mode_executes() -> None:
    report = SalesInsightReport.model_validate(load_fixture())

    dumped = report.model_dump(mode="json")

    assert dumped["generated_at"] == "2026-06-16T10:30:00Z"
    assert dumped["deal_score"]["score_level"] == "medium_high"


def test_extra_field_fails_validation() -> None:
    data = load_fixture()
    data["unexpected_field"] = "not allowed"

    with pytest.raises(ValidationError):
        SalesInsightReport.model_validate(data)


def test_ai_opportunity_without_related_pain_ids_fails_validation() -> None:
    data = load_fixture()
    data["ai_opportunities"][0]["related_pain_ids"] = []

    with pytest.raises(ValidationError, match="related pain"):
        SalesInsightReport.model_validate(data)


def test_ai_opportunity_prerequisite_suitability_requires_prerequisites() -> None:
    data = load_fixture()
    data["ai_opportunities"][0]["suitability"] = "suitable_after_prerequisites"
    data["ai_opportunities"][0]["prerequisites"] = []

    with pytest.raises(ValidationError, match="prerequisites"):
        SalesInsightReport.model_validate(data)


def test_ai_opportunity_not_suitable_requires_major_limitations() -> None:
    data = load_fixture()
    data["ai_opportunities"][0]["suitability"] = "not_suitable_for_ai"
    data["ai_opportunities"][0]["major_limitations"] = []

    with pytest.raises(ValidationError, match="major limitations"):
        SalesInsightReport.model_validate(data)


def test_ai_opportunity_fact_claim_type_fails_validation() -> None:
    data = load_fixture()
    data["ai_opportunities"][0]["claim_type"] = "fact"

    with pytest.raises(ValidationError, match="inference or assumption"):
        SalesInsightReport.model_validate(data)


def test_solution_recommendation_without_knowledge_references_fails_validation() -> None:
    data = load_fixture()
    data["solution_recommendations"][0]["knowledge_references"] = []

    with pytest.raises(ValidationError, match="knowledge references"):
        SalesInsightReport.model_validate(data)


def test_solution_recommendation_without_solution_library_reference_fails_validation() -> None:
    data = load_fixture()
    data["solution_recommendations"][0]["knowledge_references"][0][
        "source_type"
    ] = "meeting_transcript"

    with pytest.raises(ValidationError, match="solution library reference"):
        SalesInsightReport.model_validate(data)


def test_risk_without_evidence_fails_validation() -> None:
    data = load_fixture()
    data["risks_and_objections"][0]["evidence"] = []

    with pytest.raises(ValidationError, match="Risk must include at least one evidence"):
        SalesInsightReport.model_validate(data)


def test_deal_score_dimension_wrong_max_score_fails_validation() -> None:
    data = load_fixture()
    data["deal_score"]["dimensions"][0]["max_score"] = 99

    with pytest.raises(ValidationError, match="Max score"):
        SalesInsightReport.model_validate(data)


def test_deal_score_dimension_score_over_max_score_fails_validation() -> None:
    data = load_fixture()
    data["deal_score"]["dimensions"][0]["score"] = 21

    with pytest.raises(ValidationError, match="between 0 and max_score"):
        SalesInsightReport.model_validate(data)


def test_deal_score_duplicate_dimensions_fail_validation() -> None:
    data = load_fixture()
    data["deal_score"]["dimensions"][1]["dimension"] = "business_need"
    data["deal_score"]["dimensions"][1]["max_score"] = DEAL_SCORE_WEIGHTS[
        DealScoreDimensionName.business_need
    ]

    with pytest.raises(ValidationError, match="duplicate dimensions"):
        SalesInsightReport.model_validate(data)


def test_deal_score_missing_dimension_fails_validation() -> None:
    data = load_fixture()
    data["deal_score"]["dimensions"].pop()
    data["deal_score"]["total_score"] = 64
    data["deal_score"]["score_level"] = "medium"

    with pytest.raises(ValidationError, match="all 7 required dimensions"):
        SalesInsightReport.model_validate(data)


def test_deal_score_total_mismatch_fails_validation() -> None:
    data = load_fixture()
    data["deal_score"]["total_score"] = 69

    with pytest.raises(ValidationError, match="sum of dimension scores"):
        SalesInsightReport.model_validate(data)


def test_deal_score_level_mismatch_fails_validation() -> None:
    data = load_fixture()
    data["deal_score"]["score_level"] = "high"

    with pytest.raises(ValidationError, match="Deal score level"):
        SalesInsightReport.model_validate(data)


def test_p0_next_best_action_without_related_gap_ids_fails_validation() -> None:
    data = load_fixture()
    data["next_best_actions"][0]["priority"] = "P0"
    data["next_best_actions"][0]["related_gap_ids"] = []

    with pytest.raises(ValidationError, match="P0 next best actions"):
        SalesInsightReport.model_validate(data)


def test_vague_next_best_action_fails_validation() -> None:
    data = load_fixture()
    data["next_best_actions"][0]["action"] = "持续跟进"

    with pytest.raises(ValidationError, match="specific"):
        SalesInsightReport.model_validate(data)


def test_reliability_summary_negative_count_fails_validation() -> None:
    data = load_fixture()
    data["reliability_summary"]["fact_count"] = -1

    with pytest.raises(ValidationError, match="zero or greater"):
        SalesInsightReport.model_validate(data)


def test_knowledge_grounded_recommendation_rate_above_one_fails_validation() -> None:
    data = load_fixture()
    data["reliability_summary"]["knowledge_grounded_recommendation_rate"] = 1.1

    with pytest.raises(ValidationError, match="between 0 and 1"):
        SalesInsightReport.model_validate(data)


def test_human_review_required_without_reasons_fails_validation() -> None:
    data = load_fixture()
    data["reliability_summary"]["human_review_required"] = True
    data["reliability_summary"]["human_review_reasons"] = []

    with pytest.raises(ValidationError, match="Human review reasons"):
        SalesInsightReport.model_validate(data)


def test_evaluation_flag_without_affected_fields_fails_validation() -> None:
    data = load_fixture()
    data["evaluation_flags"][0]["affected_fields"] = []

    with pytest.raises(ValidationError, match="at least one affected field"):
        SalesInsightReport.model_validate(data)


def test_sales_insight_report_invalid_case_id_fails_validation() -> None:
    data = load_fixture()
    data["case_id"] = "DEV-1"

    with pytest.raises(ValidationError, match="DEV-01 or TEST-01"):
        SalesInsightReport.model_validate(data)


def test_executive_summary_intent_mismatch_fails_validation() -> None:
    data = load_fixture()
    data["executive_summary"]["overall_intent"] = "high"

    with pytest.raises(ValidationError, match="intent must match"):
        SalesInsightReport.model_validate(data)


def test_executive_summary_stage_mismatch_fails_validation() -> None:
    data = load_fixture()
    data["executive_summary"]["current_stage"] = "procurement"

    with pytest.raises(ValidationError, match="stage must match"):
        SalesInsightReport.model_validate(data)


def test_mvp_report_without_human_review_required_fails_validation() -> None:
    data = load_fixture()
    data["reliability_summary"]["human_review_required"] = False

    with pytest.raises(ValidationError, match="MVP sales insight reports"):
        SalesInsightReport.model_validate(data)


def test_sales_insight_report_without_ai_opportunities_fails_validation() -> None:
    data = load_fixture()
    data["ai_opportunities"] = []

    with pytest.raises(ValidationError, match="at least one AI opportunity"):
        SalesInsightReport.model_validate(data)


def test_sales_insight_report_without_risks_fails_validation() -> None:
    data = load_fixture()
    data["risks_and_objections"] = []

    with pytest.raises(ValidationError, match="at least one risk"):
        SalesInsightReport.model_validate(data)


def test_sales_insight_report_without_next_best_actions_fails_validation() -> None:
    data = load_fixture()
    data["next_best_actions"] = []

    with pytest.raises(ValidationError, match="at least one next best action"):
        SalesInsightReport.model_validate(data)


def test_enums_and_datetime_serialize_in_json_mode() -> None:
    report = SalesInsightReport.model_validate(load_fixture())

    dumped = report.model_dump(mode="json")

    assert dumped["generated_at"] == "2026-06-16T10:30:00Z"
    assert dumped["ai_opportunities"][0]["suitability"] == "suitable_for_poc"
    assert dumped["risks_and_objections"][0]["probability"] == "medium"


def test_solution_recommendations_may_be_empty() -> None:
    data = load_fixture()
    data["solution_recommendations"] = []
    data["reliability_summary"]["knowledge_grounded_recommendation_rate"] = 0.0

    report = SalesInsightReport.model_validate(data)

    assert report.solution_recommendations == []
