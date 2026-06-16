from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import dataio
from dataio import DatasetBoundaryError, DatasetLoadError, DuplicateCaseIdError
from dataio.evaluation_references import load_reference_packs
from dataio.jsonl_loader import load_jsonl_models
from dataio.runtime_cases import load_runtime_cases
from schemas import EvaluationCaseInput, HiddenReferencePack


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "evaluation"
SAMPLE_CASES = FIXTURE_DIR / "sample_cases.jsonl"
SAMPLE_REFERENCES = FIXTURE_DIR / "sample_references.jsonl"
DUPLICATE_CASES = FIXTURE_DIR / "duplicate_cases.jsonl"
INVALID_JSON = FIXTURE_DIR / "invalid_json.jsonl"


def test_load_runtime_cases_loads_sample_cases() -> None:
    cases = load_runtime_cases(SAMPLE_CASES)

    assert [case.case_id for case in cases] == ["DEV-01", "DEV-04"]


def test_load_reference_packs_loads_sample_references() -> None:
    references = load_reference_packs(SAMPLE_REFERENCES)

    assert [reference.case_id for reference in references] == ["DEV-01", "DEV-04"]


def test_case_id_sets_match_between_cases_and_references() -> None:
    cases = load_runtime_cases(SAMPLE_CASES)
    references = load_reference_packs(SAMPLE_REFERENCES)

    assert {case.case_id for case in cases} == {reference.case_id for reference in references}


def test_jsonl_record_order_is_preserved() -> None:
    cases = load_runtime_cases(SAMPLE_CASES)

    assert [case.case_id for case in cases] == ["DEV-01", "DEV-04"]


def test_empty_lines_are_ignored(tmp_path: Path) -> None:
    blank_line_file = tmp_path / "sample_cases_with_blank_lines.jsonl"
    blank_line_file.write_text(
        "\n" + SAMPLE_CASES.read_text(encoding="utf-8") + "\n\n",
        encoding="utf-8",
    )

    cases = load_runtime_cases(blank_line_file)

    assert [case.case_id for case in cases] == ["DEV-01", "DEV-04"]


def test_utf8_bom_file_loads(tmp_path: Path) -> None:
    bom_file = tmp_path / "sample_cases_bom.jsonl"
    bom_file.write_text(SAMPLE_CASES.read_text(encoding="utf-8"), encoding="utf-8-sig")

    cases = load_runtime_cases(bom_file)

    assert cases[0].case_id == "DEV-01"


def test_missing_file_raises_dataset_load_error(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing_cases.jsonl"

    with pytest.raises(DatasetLoadError, match="file does not exist"):
        load_runtime_cases(missing_file)


def test_empty_file_raises_dataset_load_error(tmp_path: Path) -> None:
    empty_file = tmp_path / "empty_cases.jsonl"
    empty_file.write_text("", encoding="utf-8")

    with pytest.raises(DatasetLoadError, match="no valid records"):
        load_runtime_cases(empty_file)


def test_invalid_json_error_includes_line_two() -> None:
    with pytest.raises(DatasetLoadError, match="line 2"):
        load_runtime_cases(INVALID_JSON)


def test_pydantic_validation_error_includes_path_and_line(tmp_path: Path) -> None:
    invalid_case_file = tmp_path / "invalid_case.jsonl"
    invalid_case_file.write_text('{"case_id":"DEV-01"}\n', encoding="utf-8")

    with pytest.raises(DatasetLoadError) as exc_info:
        load_runtime_cases(invalid_case_file)

    message = str(exc_info.value)
    assert str(invalid_case_file) in message
    assert "line 1" in message


def test_duplicate_cases_raise_duplicate_case_id_error() -> None:
    with pytest.raises(DuplicateCaseIdError, match="DEV-01"):
        load_runtime_cases(DUPLICATE_CASES)


def test_duplicate_case_id_error_includes_first_and_second_line_numbers() -> None:
    with pytest.raises(DuplicateCaseIdError) as exc_info:
        load_runtime_cases(DUPLICATE_CASES)

    message = str(exc_info.value)
    assert "line 1" in message
    assert "line 2" in message


def test_runtime_loader_rejects_reference_paths(tmp_path: Path) -> None:
    reference_path = tmp_path / "reference_cases.jsonl"
    reference_path.write_text(SAMPLE_CASES.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(DatasetBoundaryError, match="Hidden Reference Pack"):
        load_runtime_cases(reference_path)


def test_runtime_loader_rejects_hidden_paths(tmp_path: Path) -> None:
    hidden_path = tmp_path / "hidden_cases.jsonl"
    hidden_path.write_text(SAMPLE_CASES.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(DatasetBoundaryError, match="Hidden Reference Pack"):
        load_runtime_cases(hidden_path)


def test_runtime_cases_module_cannot_access_load_reference_packs() -> None:
    runtime_cases = importlib.import_module("dataio.runtime_cases")

    assert not hasattr(runtime_cases, "load_reference_packs")


def test_dataio_top_level_does_not_export_load_reference_packs() -> None:
    assert not hasattr(dataio, "load_reference_packs")


def test_load_reference_packs_returns_hidden_reference_pack_objects() -> None:
    references = load_reference_packs(SAMPLE_REFERENCES)

    assert all(isinstance(reference, HiddenReferencePack) for reference in references)


def test_load_runtime_cases_returns_evaluation_case_input_objects() -> None:
    cases = load_runtime_cases(SAMPLE_CASES)

    assert all(isinstance(case, EvaluationCaseInput) for case in cases)


def test_load_jsonl_models_rejects_non_object_records(tmp_path: Path) -> None:
    invalid_shape_file = tmp_path / "invalid_shape.jsonl"
    invalid_shape_file.write_text('["not", "an", "object"]\n', encoding="utf-8")

    with pytest.raises(DatasetLoadError, match="JSON object"):
        load_jsonl_models(invalid_shape_file, EvaluationCaseInput)
