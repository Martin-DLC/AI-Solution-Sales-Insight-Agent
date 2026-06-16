from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import EvaluationCaseInput


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dev_01_minimal.json"


def load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_valid_json_loads_successfully() -> None:
    data = load_fixture()

    evaluation_case = EvaluationCaseInput.model_validate(data)

    assert evaluation_case.case_id == "DEV-01"


def test_model_dump_json_mode_executes() -> None:
    evaluation_case = EvaluationCaseInput.model_validate(load_fixture())

    dumped = evaluation_case.model_dump(mode="json")

    assert dumped["dataset_split"] == "development"
    assert dumped["difficulty"] == "low"


def test_missing_case_id_fails_validation() -> None:
    data = load_fixture()
    data.pop("case_id")

    with pytest.raises(ValidationError):
        EvaluationCaseInput.model_validate(data)


def test_invalid_case_id_format_fails_validation() -> None:
    data = load_fixture()
    data["case_id"] = "DEV-1"

    with pytest.raises(ValidationError, match="Case ID must use the format DEV-01 or TEST-01"):
        EvaluationCaseInput.model_validate(data)


def test_short_meeting_transcript_fails_validation() -> None:
    data = load_fixture()
    data["meeting"]["transcript"] = "Too short."

    with pytest.raises(ValidationError, match="at least 100 characters"):
        EvaluationCaseInput.model_validate(data)


def test_empty_scenario_tags_fail_validation() -> None:
    data = load_fixture()
    data["scenario_tags"] = []

    with pytest.raises(ValidationError, match="at least one tag"):
        EvaluationCaseInput.model_validate(data)


def test_empty_available_solution_library_fails_validation() -> None:
    data = load_fixture()
    data["available_solution_library"] = []

    with pytest.raises(ValidationError, match="at least one solution"):
        EvaluationCaseInput.model_validate(data)


def test_extra_field_fails_validation() -> None:
    data = load_fixture()
    data["unexpected_field"] = "not allowed"

    with pytest.raises(ValidationError):
        EvaluationCaseInput.model_validate(data)


def test_duplicate_scenario_tags_are_deduplicated_in_order() -> None:
    data = load_fixture()
    data["scenario_tags"] = ["discovery", "renewal", "discovery", "service"]

    evaluation_case = EvaluationCaseInput.model_validate(data)

    assert evaluation_case.scenario_tags == ["discovery", "renewal", "service"]


def test_salesperson_note_verified_defaults_to_false() -> None:
    evaluation_case = EvaluationCaseInput.model_validate(load_fixture())

    assert evaluation_case.salesperson_notes[0].verified is False
