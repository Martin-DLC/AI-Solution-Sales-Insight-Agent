from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.model_benchmark.routing import (
    build_formal_pilot_summary,
    build_node_model_routing_matrix,
    load_formal_pilot_runs,
)


def test_load_formal_pilot_runs_reads_explicit_mapping(tmp_path: Path) -> None:
    path = tmp_path / "runs.json"
    path.write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "node_name": "fact_extraction",
                        "run_id": "run-1",
                        "run_path": "data/runtime/model_benchmark_runs/run-1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    runs = load_formal_pilot_runs(path)

    assert runs[0].node_name == "fact_extraction"
    assert runs[0].run_id == "run-1"


def test_build_formal_pilot_summary_matches_expected_totals() -> None:
    summary = build_formal_pilot_summary(_formal_runs())

    assert summary["totals"]["planned"] == 48
    assert summary["totals"]["completed"] == 48
    assert summary["totals"]["passed"] == 43
    assert summary["totals"]["failed"] == 5
    assert summary["totals"]["request_errors"] == 0
    assert summary["totals"]["estimated_cost_cny"] == "0.893536"


def test_failure_taxonomy_is_safely_aggregated() -> None:
    summary = build_formal_pilot_summary(_formal_runs())
    taxonomy = summary["failure_taxonomy"]

    assert taxonomy["failure_total"] == 5
    assert taxonomy["by_node"] == {
        "fact_extraction": 2,
        "solution_recommendation": 3,
    }
    assert taxonomy["by_error_type"] == {
        "LLMJSONDecodeError": 1,
        "business_rule_error": 3,
        "schema_validation_error": 1,
    }
    assert all(len(item["failure_summary"]) <= 200 for item in taxonomy["failed_cases"])


def test_routing_matrix_prefers_eligible_model_with_lower_cost() -> None:
    summary = build_formal_pilot_summary(_formal_runs())
    matrix = build_node_model_routing_matrix(summary)
    nodes = {item["node_name"]: item for item in matrix["nodes"]}

    assert nodes["underlying_pain"]["primary_model_config_id"] == "ds-v4-flash-non-thinking"
    assert nodes["underlying_pain"]["fallback_model_config_id"] == "ds-v4-pro-non-thinking"
    assert nodes["underlying_pain"]["route_status"] == "route_ready"


def test_routing_matrix_uses_real_fact_extraction_result() -> None:
    summary = build_formal_pilot_summary(_formal_runs())
    matrix = build_node_model_routing_matrix(summary)
    nodes = {item["node_name"]: item for item in matrix["nodes"]}

    assert nodes["fact_extraction"]["primary_model_config_id"] == "ds-v4-flash-non-thinking"
    assert nodes["fact_extraction"]["fallback_model_config_id"] == "ds-v4-pro-thinking-high"
    assert nodes["fact_extraction"]["route_status"] == "route_ready"


def _formal_runs():
    root = Path(__file__).resolve().parents[1]
    return load_formal_pilot_runs(
        root / "data/evaluation/model_benchmark/formal_pilot_runs.v1.json"
    )
