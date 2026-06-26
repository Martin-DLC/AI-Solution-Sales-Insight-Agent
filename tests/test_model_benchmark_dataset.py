from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.model_benchmark.dataset import (
    DEFAULT_DEVELOPMENT_CASES_PATH,
    DEFAULT_REFERENCE_PACK_PATH,
    NODE_REQUIRED_STATE_FIELDS,
    load_development_cases,
    load_node_benchmark_cases,
    load_node_input_fixture,
    load_reference_packs,
    summarize_dataset_coverage,
    validate_node_benchmark_dataset,
)
from evaluation.model_benchmark.models import BenchmarkAssertionType, BenchmarkNodeName, NodeBenchmarkCase


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_development_cases_expand_to_twelve_and_preserve_original_ids() -> None:
    cases = load_development_cases(PROJECT_ROOT / DEFAULT_DEVELOPMENT_CASES_PATH)
    assert len(cases) == 12
    assert [case.case_id for case in cases[:3]] == ["DEV-01", "DEV-04", "DEV-05"]
    assert len({case.case_id for case in cases}) == 12


def test_reference_pack_remains_one_to_one_with_cases() -> None:
    refs = load_reference_packs(PROJECT_ROOT / DEFAULT_REFERENCE_PACK_PATH)
    cases = load_development_cases(PROJECT_ROOT / DEFAULT_DEVELOPMENT_CASES_PATH)
    assert len(refs) == len(cases) == 12
    assert [ref.case_id for ref in refs] == [case.case_id for case in cases]


def test_node_benchmark_cases_count_and_node_distribution() -> None:
    cases = load_node_benchmark_cases(
        PROJECT_ROOT / "data/evaluation/model_benchmark/node_cases.jsonl"
    )
    assert len(cases) == 16
    counts = {node.value: 0 for node in NODE_REQUIRED_STATE_FIELDS}
    for case in cases:
        counts[case.node_name.value] += 1
    assert counts == {
        "fact_extraction": 4,
        "underlying_pain": 4,
        "information_gap": 4,
        "solution_recommendation": 4,
    }


def test_node_benchmark_cases_cover_at_least_eight_source_cases() -> None:
    cases = load_node_benchmark_cases(
        PROJECT_ROOT / "data/evaluation/model_benchmark/node_cases.jsonl"
    )
    source_case_ids = {case.source_case_id for case in cases}
    assert len(source_case_ids) >= 8


def test_validate_node_benchmark_dataset_passes() -> None:
    cases = load_node_benchmark_cases(
        PROJECT_ROOT / "data/evaluation/model_benchmark/node_cases.jsonl"
    )
    validate_node_benchmark_dataset(cases=cases, project_root=PROJECT_ROOT)


def test_fixture_metadata_matches_case_and_required_state_fields_exist() -> None:
    cases = load_node_benchmark_cases(
        PROJECT_ROOT / "data/evaluation/model_benchmark/node_cases.jsonl"
    )
    for case in cases:
        fixture = load_node_input_fixture(PROJECT_ROOT / case.input_fixture)
        assert fixture["benchmark_case_id"] == case.benchmark_case_id
        assert fixture["source_case_id"] == case.source_case_id
        assert fixture["node_name"] == case.node_name.value
        state = fixture["state"]
        assert isinstance(state, dict)
        for field_name in NODE_REQUIRED_STATE_FIELDS[case.node_name]:
            assert field_name in state


def test_fixture_paths_and_benchmark_ids_are_unique() -> None:
    cases = load_node_benchmark_cases(
        PROJECT_ROOT / "data/evaluation/model_benchmark/node_cases.jsonl"
    )
    assert len({case.benchmark_case_id for case in cases}) == 16
    assert all(not Path(case.input_fixture).is_absolute() for case in cases)
    assert all(".." not in Path(case.input_fixture).parts for case in cases)
    assert all((PROJECT_ROOT / case.input_fixture).exists() for case in cases)


def test_fixture_secret_fields_are_rejected(tmp_path: Path) -> None:
    bad_fixture = tmp_path / "bad.json"
    bad_fixture.write_text(
        json.dumps(
            {
                "fixture_version": "1.0",
                "benchmark_case_id": "NB-TEST-01",
                "source_case_id": "DEV-01",
                "node_name": "fact_extraction",
                "state": {"api_key": "secret"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="forbidden field"):
        load_node_input_fixture(bad_fixture)


def test_fixture_parent_traversal_paths_are_rejected(tmp_path: Path) -> None:
    data_dir = tmp_path / "data/evaluation"
    data_dir.mkdir(parents=True)
    data_dir.joinpath("development_cases.jsonl").write_text(
        (PROJECT_ROOT / DEFAULT_DEVELOPMENT_CASES_PATH).read_text(encoding="utf-8").splitlines()[0]
        + "\n",
        encoding="utf-8",
    )
    cases = []
    node_cycle = [
        BenchmarkNodeName.fact_extraction,
        BenchmarkNodeName.underlying_pain,
        BenchmarkNodeName.information_gap,
        BenchmarkNodeName.solution_recommendation,
    ]
    for index, node_name in enumerate(node_cycle * 4, start=1):
        cases.append(
            NodeBenchmarkCase(
                benchmark_case_id=f"NB-TEST-{index:02d}",
                source_case_id="DEV-01",
                node_name=node_name,
                input_fixture="../escape.json",
                assertions=[
                    {
                        "assertion_id": f"A-{index}",
                        "assertion_type": BenchmarkAssertionType.json_parse_success,
                        "location": "state",
                        "expected_value": True,
                        "description": "JSON parse must succeed.",
                        "blocking": True,
                    }
                ],
            )
        )
    with pytest.raises(ValueError, match="escape the project root"):
        validate_node_benchmark_dataset(cases=cases, project_root=tmp_path)


def test_dataset_summary_is_stable() -> None:
    cases = load_node_benchmark_cases(
        PROJECT_ROOT / "data/evaluation/model_benchmark/node_cases.jsonl"
    )
    summary = summarize_dataset_coverage(cases)
    assert summary["total_cases"] == 16
    assert summary["cases_per_node"] == {
        "fact_extraction": 4,
        "underlying_pain": 4,
        "information_gap": 4,
        "solution_recommendation": 4,
    }
    assert summary["unique_source_case_count"] >= 8
    assert len(summary["source_case_ids"]) == summary["unique_source_case_count"]
    assert sum(summary["assertion_type_counts"].values()) >= 16


def test_assertion_type_counts_include_required_contract_types() -> None:
    cases = load_node_benchmark_cases(
        PROJECT_ROOT / "data/evaluation/model_benchmark/node_cases.jsonl"
    )
    summary = summarize_dataset_coverage(cases)
    for assertion_type in (
        "json_parse_success",
        "schema_validation_success",
        "business_rule_success",
        "evidence_reference_valid",
        "candidate_boundary_valid",
        "required_value_equals",
        "forbidden_value_absent",
        "referenced_id_exists",
    ):
        assert assertion_type in summary["assertion_type_counts"]
