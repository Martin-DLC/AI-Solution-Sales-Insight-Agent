from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dataio.errors import DatasetBoundaryError  # noqa: E402
from dataio.evaluation_references import load_reference_packs  # noqa: E402
from dataio.runtime_cases import load_runtime_cases  # noqa: E402


EXPECTED_CASE_IDS = ["DEV-01", "DEV-04", "DEV-05"]
CASES_PATH = PROJECT_ROOT / "data" / "evaluation" / "development_cases.jsonl"
REFERENCES_PATH = PROJECT_ROOT / "data" / "evaluation" / "development_reference.jsonl"
FORBIDDEN_MARKERS = ("TODO", "待补充", "同上", "省略")


def fail(message: str) -> None:
    print(f"Seed dataset validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def non_empty_lines(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def assert_no_forbidden_markers(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for marker in FORBIDDEN_MARKERS:
        if marker in text:
            fail(f"{path} contains forbidden marker {marker!r}.")


def assert_independent_json_lines(path: Path) -> None:
    for line_number, line in enumerate(non_empty_lines(path), start=1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            fail(f"{path} line {line_number} is not valid JSON: {exc.msg}.")
        if not isinstance(value, dict):
            fail(f"{path} line {line_number} must be a JSON object.")


def main() -> int:
    assert_true(CASES_PATH.exists(), f"{CASES_PATH} does not exist.")
    assert_true(REFERENCES_PATH.exists(), f"{REFERENCES_PATH} does not exist.")

    assert_no_forbidden_markers(CASES_PATH)
    assert_no_forbidden_markers(REFERENCES_PATH)
    assert_independent_json_lines(CASES_PATH)
    assert_independent_json_lines(REFERENCES_PATH)

    cases = load_runtime_cases(CASES_PATH)
    references = load_reference_packs(REFERENCES_PATH)

    case_ids = [case.case_id for case in cases]
    reference_ids = [reference.case_id for reference in references]

    assert_true(len(cases) == 3, f"Expected 3 runtime cases, got {len(cases)}.")
    assert_true(len(references) == 3, f"Expected 3 reference packs, got {len(references)}.")
    assert_true(case_ids == EXPECTED_CASE_IDS, f"Case order must be {EXPECTED_CASE_IDS}, got {case_ids}.")
    assert_true(
        reference_ids == EXPECTED_CASE_IDS,
        f"Reference order must be {EXPECTED_CASE_IDS}, got {reference_ids}.",
    )
    assert_true(
        case_ids == reference_ids,
        f"Case and reference IDs must match exactly, got {case_ids} and {reference_ids}.",
    )
    assert_true(len(set(case_ids)) == len(case_ids), f"Duplicate case IDs found: {case_ids}.")

    case_lines = non_empty_lines(CASES_PATH)
    reference_lines = non_empty_lines(REFERENCES_PATH)
    assert_true(len(case_lines) == 3, f"{CASES_PATH} must have exactly 3 non-empty lines.")
    assert_true(
        len(reference_lines) == 3,
        f"{REFERENCES_PATH} must have exactly 3 non-empty lines.",
    )

    for case in cases:
        assert_true(
            case.dataset_split.value == "development",
            f"{case.case_id} dataset_split must be development.",
        )
        assert_true(
            len(case.meeting.transcript) >= 100,
            f"{case.case_id} meeting transcript must contain at least 100 characters.",
        )
        assert_true(
            len(case.meeting.participants) >= 2,
            f"{case.case_id} must include at least 2 meeting participants.",
        )
        assert_true(
            len(case.salesperson_notes) >= 1,
            f"{case.case_id} must include at least 1 salesperson note.",
        )
        assert_true(
            any(note.verified is False for note in case.salesperson_notes),
            f"{case.case_id} must include at least 1 unverified salesperson note.",
        )
        assert_true(
            len(case.known_constraints) >= 2,
            f"{case.case_id} must include at least 2 known constraints.",
        )
        assert_true(
            len(case.available_solution_library) >= 2,
            f"{case.case_id} must include at least 2 available solutions.",
        )
        case.model_dump(mode="json")

    reference_by_id = {reference.case_id: reference for reference in references}
    for reference in references:
        assert_true(
            len(reference.hard_failure_traps) >= 1,
            f"{reference.case_id} must include at least 1 hard failure trap.",
        )
        assert_true(
            len(reference.solution_whitelist) >= 1,
            f"{reference.case_id} must include at least 1 solution whitelist entry.",
        )
        assert_true(
            len(reference.solution_blacklist) >= 1,
            f"{reference.case_id} must include at least 1 solution blacklist entry.",
        )
        assert_true(
            len(reference.critical_information_gaps) >= 1,
            f"{reference.case_id} must include at least 1 critical information gap.",
        )
        assert_true(
            len(reference.acceptable_next_actions) >= 1,
            f"{reference.case_id} must include at least 1 acceptable next action.",
        )
        reference.model_dump(mode="json")

    try:
        load_runtime_cases(REFERENCES_PATH)
    except DatasetBoundaryError:
        pass
    else:
        fail("Runtime loader must reject the Hidden Reference Pack file.")

    print("Case ID | Transcript chars | Participants | Sales notes | Constraints | Solutions | Hard traps")
    for case in cases:
        reference = reference_by_id[case.case_id]
        print(
            " | ".join(
                [
                    case.case_id,
                    str(len(case.meeting.transcript)),
                    str(len(case.meeting.participants)),
                    str(len(case.salesperson_notes)),
                    str(len(case.known_constraints)),
                    str(len(case.available_solution_library)),
                    str(len(reference.hard_failure_traps)),
                ]
            )
        )

    print("Seed dataset validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
