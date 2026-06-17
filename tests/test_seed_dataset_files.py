from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from dataio.errors import DatasetBoundaryError
from dataio.evaluation_references import load_reference_packs
from dataio.runtime_cases import load_runtime_cases


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "data" / "evaluation" / "development_cases.jsonl"
REFERENCES_PATH = PROJECT_ROOT / "data" / "evaluation" / "development_reference.jsonl"
VALIDATION_SCRIPT = PROJECT_ROOT / "scripts" / "validate_seed_dataset.py"
EXPECTED_CASE_IDS = ["DEV-01", "DEV-04", "DEV-05"]
FORBIDDEN_MARKERS = ("TODO", "待补充", "同上", "省略")


@pytest.fixture
def seed_cases():
    return load_runtime_cases(CASES_PATH)


@pytest.fixture
def seed_references():
    return load_reference_packs(REFERENCES_PATH)


def non_empty_lines(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_official_cases_load(seed_cases) -> None:
    assert [case.case_id for case in seed_cases] == EXPECTED_CASE_IDS


def test_official_references_load(seed_references) -> None:
    assert [reference.case_id for reference in seed_references] == EXPECTED_CASE_IDS


def test_cases_count_is_three(seed_cases) -> None:
    assert len(seed_cases) == 3


def test_references_count_is_three(seed_references) -> None:
    assert len(seed_references) == 3


def test_case_ids_match_exactly(seed_cases, seed_references) -> None:
    assert [case.case_id for case in seed_cases] == [
        reference.case_id for reference in seed_references
    ]


def test_case_order_is_expected(seed_cases, seed_references) -> None:
    assert [case.case_id for case in seed_cases] == EXPECTED_CASE_IDS
    assert [reference.case_id for reference in seed_references] == EXPECTED_CASE_IDS


def test_all_dataset_splits_are_development(seed_cases) -> None:
    assert all(case.dataset_split.value == "development" for case in seed_cases)


def test_each_case_transcript_is_at_least_100_characters(seed_cases) -> None:
    assert all(len(case.meeting.transcript) >= 100 for case in seed_cases)


def test_each_case_has_at_least_two_participants(seed_cases) -> None:
    assert all(len(case.meeting.participants) >= 2 for case in seed_cases)


def test_each_case_has_salesperson_note(seed_cases) -> None:
    assert all(len(case.salesperson_notes) >= 1 for case in seed_cases)


def test_each_case_has_unverified_salesperson_note(seed_cases) -> None:
    assert all(any(note.verified is False for note in case.salesperson_notes) for case in seed_cases)


def test_each_case_has_at_least_two_constraints(seed_cases) -> None:
    assert all(len(case.known_constraints) >= 2 for case in seed_cases)


def test_each_case_has_at_least_two_solutions(seed_cases) -> None:
    assert all(len(case.available_solution_library) >= 2 for case in seed_cases)


def test_each_reference_has_hard_failure_traps(seed_references) -> None:
    assert all(reference.hard_failure_traps for reference in seed_references)


def test_each_reference_has_solution_whitelist(seed_references) -> None:
    assert all(reference.solution_whitelist for reference in seed_references)


def test_each_reference_has_solution_blacklist(seed_references) -> None:
    assert all(reference.solution_blacklist for reference in seed_references)


def test_each_reference_has_critical_information_gaps(seed_references) -> None:
    assert all(reference.critical_information_gaps for reference in seed_references)


def test_each_reference_has_acceptable_next_actions(seed_references) -> None:
    assert all(reference.acceptable_next_actions for reference in seed_references)


def test_runtime_loader_cannot_load_reference_file() -> None:
    with pytest.raises(DatasetBoundaryError):
        load_runtime_cases(REFERENCES_PATH)


def test_all_objects_dump_in_json_mode(seed_cases, seed_references) -> None:
    for item in [*seed_cases, *seed_references]:
        assert isinstance(item.model_dump(mode="json"), dict)


def test_seed_data_has_no_forbidden_markers() -> None:
    combined_text = (
        CASES_PATH.read_text(encoding="utf-8")
        + "\n"
        + REFERENCES_PATH.read_text(encoding="utf-8")
    )
    assert not any(marker in combined_text for marker in FORBIDDEN_MARKERS)


def test_both_jsonl_files_have_three_non_empty_physical_lines() -> None:
    assert len(non_empty_lines(CASES_PATH)) == 3
    assert len(non_empty_lines(REFERENCES_PATH)) == 3


def test_each_non_empty_physical_line_is_independent_json() -> None:
    for path in (CASES_PATH, REFERENCES_PATH):
        for line in non_empty_lines(path):
            assert isinstance(json.loads(line), dict)


def test_validate_seed_dataset_script_succeeds() -> None:
    result = subprocess.run(
        [sys.executable, str(VALIDATION_SCRIPT)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_validate_seed_dataset_script_outputs_success_message() -> None:
    result = subprocess.run(
        [sys.executable, str(VALIDATION_SCRIPT)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert "Seed dataset validation passed." in result.stdout
