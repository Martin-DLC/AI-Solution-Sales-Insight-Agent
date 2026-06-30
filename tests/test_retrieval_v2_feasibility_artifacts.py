from __future__ import annotations

import json
from pathlib import Path


FEASIBILITY_PATH = Path("data/evaluation/retrieval/retrieval_case_feasibility.v2.json")


def test_all_v2_cases_are_feasible() -> None:
    payload = json.loads(FEASIBILITY_PATH.read_text(encoding="utf-8"))

    assert payload["summary"]["case_count"] == 16
    assert payload["summary"]["feasible_case_count"] == 16
    assert payload["summary"]["infeasible_case_count"] == 0
    assert payload["summary"]["infeasible_case_ids"] == []


def test_rewritten_cases_are_now_boundary_safe() -> None:
    payload = json.loads(FEASIBILITY_PATH.read_text(encoding="utf-8"))
    case_map = {row["case_id"]: row for row in payload["cases"]}

    for case_id in ["RET2-005", "RET2-006", "RET2-009"]:
        assert case_map[case_id]["feasible"] is True
        assert case_map[case_id]["boundary_safe_expected_item_count"] >= 2
        assert case_map[case_id]["reasons"] == []
