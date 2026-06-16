from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import HiddenReferencePack, ReferenceSalesStage


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "evaluation" / "sample_references.jsonl"


def load_reference_payload() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8").splitlines()[0])


def test_valid_hidden_reference_pack_loads() -> None:
    reference = HiddenReferencePack.model_validate(load_reference_payload())

    assert reference.case_id == "DEV-01"
    assert reference.expected_sales_stage_range[0] is ReferenceSalesStage.early_discovery


def test_hidden_reference_pack_model_dump_json_mode_executes() -> None:
    reference = HiddenReferencePack.model_validate(load_reference_payload())

    dumped = reference.model_dump(mode="json")

    assert dumped["case_id"] == "DEV-01"
    assert dumped["expected_sales_stage_range"] == ["early_discovery", "discovery"]


def test_hidden_reference_pack_invalid_case_id_fails_validation() -> None:
    data = load_reference_payload()
    data["case_id"] = "DEV-1"

    with pytest.raises(ValidationError, match="DEV-01 or TEST-01"):
        HiddenReferencePack.model_validate(data)


def test_hidden_reference_pack_without_must_capture_facts_fails_validation() -> None:
    data = load_reference_payload()
    data["must_capture_facts"] = []

    with pytest.raises(ValidationError, match="must_capture_facts"):
        HiddenReferencePack.model_validate(data)


def test_hidden_reference_pack_without_solution_whitelist_fails_validation() -> None:
    data = load_reference_payload()
    data["solution_whitelist"] = []

    with pytest.raises(ValidationError, match="solution_whitelist"):
        HiddenReferencePack.model_validate(data)


def test_hidden_reference_pack_without_hard_failure_traps_fails_validation() -> None:
    data = load_reference_payload()
    data["hard_failure_traps"] = []

    with pytest.raises(ValidationError, match="hard_failure_traps"):
        HiddenReferencePack.model_validate(data)


def test_hidden_reference_pack_short_scoring_notes_fails_validation() -> None:
    data = load_reference_payload()
    data["scoring_notes"] = "Too short"

    with pytest.raises(ValidationError, match="20 characters"):
        HiddenReferencePack.model_validate(data)


def test_hidden_reference_pack_duplicate_lists_are_deduplicated_in_order() -> None:
    data = load_reference_payload()
    data["must_capture_facts"] = ["Fact A", "Fact B", "Fact A"]

    reference = HiddenReferencePack.model_validate(data)

    assert reference.must_capture_facts == ["Fact A", "Fact B"]


def test_hidden_reference_pack_extra_field_fails_validation() -> None:
    data = load_reference_payload()
    data["unexpected_field"] = "not allowed"

    with pytest.raises(ValidationError):
        HiddenReferencePack.model_validate(data)


def test_reference_sales_stage_enum_serializes_in_json_mode() -> None:
    reference = HiddenReferencePack.model_validate(load_reference_payload())

    dumped = reference.model_dump(mode="json")

    assert dumped["expected_sales_stage_range"][0] == "early_discovery"
