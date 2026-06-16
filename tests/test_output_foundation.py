from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import (
    ClaimType,
    CoreInsightAnalysis,
    SalesRole,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dev_01_output_foundation.json"


def load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_valid_fixture_loads_as_core_insight_analysis() -> None:
    analysis = CoreInsightAnalysis.model_validate(load_fixture())

    assert len(analysis.explicit_needs) == 2
    assert len(analysis.stakeholder_map) == 2


def test_model_dump_json_mode_executes() -> None:
    analysis = CoreInsightAnalysis.model_validate(load_fixture())

    dumped = analysis.model_dump(mode="json")

    assert dumped["customer_context"]["context_quality"] == "partially_sufficient"
    assert dumped["explicit_needs"][0]["claim_type"] == "fact"


def test_extra_field_fails_validation() -> None:
    data = load_fixture()
    data["unexpected_field"] = "not allowed"

    with pytest.raises(ValidationError):
        CoreInsightAnalysis.model_validate(data)


def test_explicit_need_inference_fails_validation() -> None:
    data = load_fixture()
    data["explicit_needs"][0]["claim_type"] = "inference"

    with pytest.raises(ValidationError, match="must be facts"):
        CoreInsightAnalysis.model_validate(data)


def test_explicit_need_without_evidence_fails_validation() -> None:
    data = load_fixture()
    data["explicit_needs"][0]["evidence"] = []

    with pytest.raises(ValidationError, match="Explicit needs must include at least one evidence"):
        CoreInsightAnalysis.model_validate(data)


def test_underlying_pain_fact_fails_validation() -> None:
    data = load_fixture()
    data["underlying_pains"][0]["claim_type"] = "fact"

    with pytest.raises(ValidationError, match="inference or assumption"):
        CoreInsightAnalysis.model_validate(data)


def test_underlying_pain_without_evidence_fails_validation() -> None:
    data = load_fixture()
    data["underlying_pains"][0]["evidence"] = []

    with pytest.raises(ValidationError, match="Underlying pain must include at least one evidence"):
        CoreInsightAnalysis.model_validate(data)


def test_validation_question_gets_chinese_question_mark() -> None:
    data = load_fixture()
    data["underlying_pains"][0]["validation_question"] = "What takes the most time today"

    analysis = CoreInsightAnalysis.model_validate(data)

    assert analysis.underlying_pains[0].validation_question.endswith("？")


def test_quantified_business_impact_without_values_fails_validation() -> None:
    data = load_fixture()
    data["business_impacts"][0]["quantified"] = True
    data["business_impacts"][0]["current_value"] = None
    data["business_impacts"][0]["target_value"] = None

    with pytest.raises(ValidationError, match="current value or a target value"):
        CoreInsightAnalysis.model_validate(data)


def test_unquantified_business_impact_without_measurement_needed_fails_validation() -> None:
    data = load_fixture()
    data["business_impacts"][0]["quantified"] = False
    data["business_impacts"][0]["current_value"] = None
    data["business_impacts"][0]["target_value"] = None
    data["business_impacts"][0]["measurement_needed"] = None

    with pytest.raises(ValidationError, match="measurement is needed"):
        CoreInsightAnalysis.model_validate(data)


def test_buying_intent_with_no_signals_fails_validation() -> None:
    data = load_fixture()
    data["buying_intent"]["positive_signals"] = []
    data["buying_intent"]["negative_signals"] = []
    data["buying_intent"]["unknown_factors"] = []

    with pytest.raises(ValidationError, match="at least one positive signal"):
        CoreInsightAnalysis.model_validate(data)


def test_buying_intent_duplicate_signals_are_deduplicated_in_order() -> None:
    data = load_fixture()
    data["buying_intent"]["positive_signals"] = [
        "Near-term planning milestone",
        "Concrete reporting need",
        "Near-term planning milestone",
    ]

    analysis = CoreInsightAnalysis.model_validate(data)

    assert analysis.buying_intent.positive_signals == [
        "Near-term planning milestone",
        "Concrete reporting need",
    ]


def test_confirmed_stakeholder_without_evidence_fails_validation() -> None:
    data = load_fixture()
    data["stakeholder_map"][0]["confirmed"] = True
    data["stakeholder_map"][0]["evidence"] = []

    with pytest.raises(ValidationError, match="Confirmed stakeholders"):
        CoreInsightAnalysis.model_validate(data)


def test_unconfirmed_stakeholder_without_next_validation_fails_validation() -> None:
    data = load_fixture()
    data["stakeholder_map"][1]["confirmed"] = False
    data["stakeholder_map"][1]["next_validation"] = None

    with pytest.raises(ValidationError, match="Unconfirmed stakeholders"):
        CoreInsightAnalysis.model_validate(data)


def test_critical_information_gap_with_short_business_impact_fails_validation() -> None:
    data = load_fixture()
    data["information_gaps"][0]["priority"] = "critical"
    data["information_gaps"][0]["business_impact"] = "Too short"

    with pytest.raises(ValidationError, match="at least 10 characters"):
        CoreInsightAnalysis.model_validate(data)


def test_customer_context_current_systems_are_deduplicated_in_order() -> None:
    data = load_fixture()
    data["customer_context"]["current_systems"] = ["CRM", "Ticketing system", "CRM"]

    analysis = CoreInsightAnalysis.model_validate(data)

    assert analysis.customer_context.current_systems == ["CRM", "Ticketing system"]


def test_core_insight_without_explicit_need_fails_validation() -> None:
    data = load_fixture()
    data["explicit_needs"] = []

    with pytest.raises(ValidationError, match="at least one explicit need"):
        CoreInsightAnalysis.model_validate(data)


def test_core_insight_without_stakeholder_fails_validation() -> None:
    data = load_fixture()
    data["stakeholder_map"] = []

    with pytest.raises(ValidationError, match="at least one stakeholder"):
        CoreInsightAnalysis.model_validate(data)


def test_empty_string_fails_validation() -> None:
    data = load_fixture()
    data["customer_context"]["company_name"] = "  "

    with pytest.raises(ValidationError, match="cannot be empty"):
        CoreInsightAnalysis.model_validate(data)


def test_information_gap_question_gets_chinese_question_mark() -> None:
    data = load_fixture()
    data["information_gaps"][0]["question_to_ask"] = "Who owns budget approval"

    analysis = CoreInsightAnalysis.model_validate(data)

    assert analysis.information_gaps[0].question_to_ask.endswith("？")


def test_model_exports_keep_enum_instances() -> None:
    analysis = CoreInsightAnalysis.model_validate(load_fixture())

    assert analysis.explicit_needs[0].claim_type is ClaimType.fact
    assert analysis.stakeholder_map[0].sales_role is SalesRole.business_owner
