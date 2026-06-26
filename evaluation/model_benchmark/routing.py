from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


TARGET_NODES = (
    "fact_extraction",
    "underlying_pain",
    "information_gap",
    "solution_recommendation",
)
EXPECTED_MODEL_CONFIG_IDS = (
    "ds-v4-flash-non-thinking",
    "ds-v4-pro-non-thinking",
    "ds-v4-pro-thinking-high",
)
EXPECTED_TOTALS = {
    "planned": 48,
    "completed": 48,
    "passed": 43,
    "failed": 5,
    "request_errors": 0,
    "estimated_cost_cny": Decimal("0.893536"),
}
FAILURE_SUMMARY_LIMIT = 200


@dataclass(frozen=True)
class FormalPilotRun:
    node_name: str
    run_id: str
    run_path: Path


def load_formal_pilot_runs(path: str | Path) -> list[FormalPilotRun]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    runs = payload.get("runs", [])
    result: list[FormalPilotRun] = []
    for item in runs:
        result.append(
            FormalPilotRun(
                node_name=item["node_name"],
                run_id=item["run_id"],
                run_path=Path(item["run_path"]),
            )
        )
    return result


def build_formal_pilot_summary(runs: list[FormalPilotRun]) -> dict[str, Any]:
    _validate_formal_run_inputs(runs)

    node_summaries: list[dict[str, Any]] = []
    model_overall: dict[str, dict[str, Any]] = {}
    failure_records: list[dict[str, Any]] = []
    totals = {
        "planned": 0,
        "completed": 0,
        "passed": 0,
        "failed": 0,
        "request_errors": 0,
        "unknown_cost_runs": 0,
        "estimated_cost_cny": Decimal("0"),
    }

    for run in runs:
        manifest = _load_json(run.run_path / "run_manifest.json")
        summaries = _load_summary_items(run.run_path / "node_model_summaries.json")
        case_results = _load_jsonl(run.run_path / "case_results.jsonl")

        _validate_formal_run(run, manifest, summaries, case_results)

        totals["planned"] += manifest["planned_run_count"]
        totals["completed"] += manifest["completed_run_count"]
        totals["passed"] += manifest["passed_count"]
        totals["failed"] += manifest["failed_count"]
        totals["request_errors"] += manifest["request_error_count"]
        totals["unknown_cost_runs"] += manifest["unknown_cost_run_count"]
        totals["estimated_cost_cny"] += Decimal(str(manifest["estimated_cost_cny"]))

        per_model_results = _group_case_results_by_model(case_results)
        node_entry = {
            "node_name": run.node_name,
            "run_id": run.run_id,
            "run_path": str(run.run_path),
            "planned_run_count": manifest["planned_run_count"],
            "completed_run_count": manifest["completed_run_count"],
            "passed_count": manifest["passed_count"],
            "failed_count": manifest["failed_count"],
            "request_error_count": manifest["request_error_count"],
            "unknown_cost_run_count": manifest["unknown_cost_run_count"],
            "stopped_by_budget": manifest["stopped_by_budget"],
            "estimated_cost_cny": _decimal_str(Decimal(str(manifest["estimated_cost_cny"]))),
            "model_summaries": [],
        }

        for item in sorted(summaries, key=lambda value: value["model_config_id"]):
            model_config_id = item["model_config_id"]
            result_rows = per_model_results[model_config_id]
            case_count = item["case_count"]
            failed_count = case_count - item["passed_count"]
            total_cost = _decimal_or_none(item.get("estimated_total_cost"))
            average_cost = (total_cost / case_count) if total_cost is not None and case_count else None
            average_tokens = (item["total_tokens"] / case_count) if case_count else 0.0
            node_entry["model_summaries"].append(
                {
                    "node_name": run.node_name,
                    "model_config_id": model_config_id,
                    "case_count": case_count,
                    "passed_count": item["passed_count"],
                    "failed_count": failed_count,
                    "pass_rate": _ratio_str(item["passed_count"], case_count),
                    "json_parse_pass_rate": _rate_str(item["json_parse_pass_rate"]),
                    "schema_pass_rate": _rate_str(item["schema_pass_rate"]),
                    "business_rule_pass_rate": _rate_str(item["business_rule_pass_rate"]),
                    "evidence_reference_pass_rate": _rate_str(item["evidence_reference_pass_rate"]),
                    "candidate_boundary_pass_rate": _rate_str(item["candidate_boundary_pass_rate"]),
                    "total_tokens": item["total_tokens"],
                    "average_tokens_per_case": round(average_tokens, 3),
                    "estimated_total_cost_cny": _decimal_str(total_cost),
                    "average_cost_per_case_cny": _decimal_str(average_cost),
                    "average_latency_ms": round(item["average_latency_ms"], 3),
                    "eligible_for_routing": item["eligible_for_routing"],
                    "disqualification_reasons": list(item["disqualification_reasons"]),
                    "request_error_count": sum(
                        1 for row in result_rows if row["status"] == "request_error"
                    ),
                }
            )

            current = model_overall.setdefault(
                model_config_id,
                {
                    "model_config_id": model_config_id,
                    "total_cases": 0,
                    "total_passed": 0,
                    "total_failed": 0,
                    "total_tokens": 0,
                    "total_cost_cny": Decimal("0"),
                    "average_latency_samples": [],
                },
            )
            current["total_cases"] += case_count
            current["total_passed"] += item["passed_count"]
            current["total_failed"] += failed_count
            current["total_tokens"] += item["total_tokens"]
            if total_cost is not None:
                current["total_cost_cny"] += total_cost
            current["average_latency_samples"].append(item["average_latency_ms"])

        failure_records.extend(_extract_failure_records(run, case_results))
        node_summaries.append(node_entry)

    _validate_formal_totals(totals)

    model_overall_summary = []
    for model_config_id in sorted(model_overall):
        item = model_overall[model_config_id]
        avg_latency = (
            sum(item["average_latency_samples"]) / len(item["average_latency_samples"])
            if item["average_latency_samples"]
            else 0.0
        )
        model_overall_summary.append(
            {
                "model_config_id": model_config_id,
                "total_cases": item["total_cases"],
                "total_passed": item["total_passed"],
                "total_failed": item["total_failed"],
                "total_tokens": item["total_tokens"],
                "total_cost_cny": _decimal_str(item["total_cost_cny"]),
                "average_latency_ms": round(avg_latency, 3),
            }
        )

    failure_taxonomy = _build_failure_taxonomy(failure_records)

    return {
        "summary_version": "v1",
        "formal_run_ids": [run.run_id for run in runs],
        "formal_run_paths": [str(run.run_path) for run in runs],
        "totals": {
            "planned": totals["planned"],
            "completed": totals["completed"],
            "passed": totals["passed"],
            "failed": totals["failed"],
            "request_errors": totals["request_errors"],
            "unknown_cost_runs": totals["unknown_cost_runs"],
            "estimated_cost_cny": _decimal_str(totals["estimated_cost_cny"]),
        },
        "node_summaries": node_summaries,
        "model_overall_summary": model_overall_summary,
        "failure_taxonomy": failure_taxonomy,
    }


def build_node_model_routing_matrix(summary: dict[str, Any]) -> dict[str, Any]:
    nodes = summary["node_summaries"]
    routing_nodes = []

    for node_entry in sorted(nodes, key=lambda item: TARGET_NODES.index(item["node_name"])):
        eligible = [
            item
            for item in node_entry["model_summaries"]
            if item["eligible_for_routing"] and item["case_count"] == 4
        ]
        eligible = sorted(eligible, key=_routing_sort_key)
        primary = eligible[0] if eligible else None
        fallback = eligible[1] if len(eligible) > 1 else None

        disqualified_models = [
            {
                "model_config_id": item["model_config_id"],
                "disqualification_reasons": list(item["disqualification_reasons"]),
                "eligible_for_routing": item["eligible_for_routing"],
            }
            for item in sorted(node_entry["model_summaries"], key=lambda item: item["model_config_id"])
            if item not in eligible
        ]

        route_status = "route_ready" if primary is not None else "no_eligible_model"
        selection_reason = (
            "Selected by eligible_for_routing gate, then ordered by total cost, average latency, total tokens, and model_config_id."
            if primary is not None
            else "No model satisfied the existing routing eligibility gate for this node."
        )
        limitations = []
        if fallback is None:
            limitations.append("Only one eligible model is available." if primary else "No eligible fallback model is available.")
        if disqualified_models:
            limitations.append("Some models remain disqualified by existing benchmark gating.")

        routing_nodes.append(
            {
                "node_name": node_entry["node_name"],
                "case_count": 4,
                "route_status": route_status,
                "primary_model_config_id": primary["model_config_id"] if primary else None,
                "fallback_model_config_id": fallback["model_config_id"] if fallback else None,
                "eligible_model_config_ids": [item["model_config_id"] for item in eligible],
                "disqualified_models": disqualified_models,
                "primary_cost_cny": primary["estimated_total_cost_cny"] if primary else None,
                "primary_average_latency_ms": primary["average_latency_ms"] if primary else None,
                "primary_total_tokens": primary["total_tokens"] if primary else None,
                "selection_reason": selection_reason,
                "limitations": limitations,
            }
        )

    return {
        "matrix_version": "v1",
        "formal_run_ids": list(summary["formal_run_ids"]),
        "nodes": routing_nodes,
    }


def _validate_formal_run_inputs(runs: list[FormalPilotRun]) -> None:
    if len(runs) != 4:
        raise ValueError(f"Expected exactly 4 formal pilot runs, got {len(runs)}.")
    run_nodes = sorted(run.node_name for run in runs)
    if run_nodes != sorted(TARGET_NODES):
        raise ValueError(f"Formal pilot runs must match target nodes {list(TARGET_NODES)}.")


def _validate_formal_run(
    run: FormalPilotRun,
    manifest: dict[str, Any],
    summaries: list[dict[str, Any]],
    case_results: list[dict[str, Any]],
) -> None:
    checks = {
        "planned_run_count": 12,
        "completed_run_count": 12,
        "request_error_count": 0,
        "unknown_cost_run_count": 0,
        "stopped_by_budget": False,
    }
    for field_name, expected in checks.items():
        actual = manifest.get(field_name)
        if actual != expected:
            raise ValueError(f"{run.run_id} {field_name} expected {expected}, got {actual}.")

    if len(summaries) != 3:
        raise ValueError(f"{run.run_id} expected 3 model summaries, got {len(summaries)}.")

    model_config_ids = sorted({item["model_config_id"] for item in summaries})
    if model_config_ids != sorted(EXPECTED_MODEL_CONFIG_IDS):
        raise ValueError(f"{run.run_id} model config set mismatch: {model_config_ids}.")

    nodes = {item["node_name"] for item in summaries}
    if nodes != {run.node_name}:
        raise ValueError(f"{run.run_id} node summary mismatch: {nodes}.")

    if len(case_results) != 12:
        raise ValueError(f"{run.run_id} expected 12 case results, got {len(case_results)}.")

    per_model = _group_case_results_by_model(case_results)
    for model_config_id, rows in per_model.items():
        if len(rows) != 4:
            raise ValueError(
                f"{run.run_id} model {model_config_id} expected 4 case results, got {len(rows)}."
            )


def _validate_formal_totals(totals: dict[str, Any]) -> None:
    for key, expected in EXPECTED_TOTALS.items():
        actual = totals[key]
        if actual != expected:
            raise ValueError(f"Formal pilot total {key} expected {expected}, got {actual}.")


def _extract_failure_records(
    run: FormalPilotRun,
    case_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records = []
    for result in case_results:
        if result["status"] == "passed":
            continue
        assertion_path = (
            run.run_path
            / "cases"
            / result["benchmark_case_id"]
            / result["model_config_id"]
            / result["node_name"]
            / "assertion_results.json"
        )
        assertion_results = _load_json(assertion_path)
        failed_assertions = [item for item in assertion_results if not item["passed"]]
        failure_summary = _build_failure_summary(result, failed_assertions)
        records.append(
            {
                "benchmark_case_id": result["benchmark_case_id"],
                "node_name": result["node_name"],
                "model_config_id": result["model_config_id"],
                "status": result["status"],
                "error_type": result["error_type"],
                "failed_assertion_ids": [item["assertion_id"] for item in failed_assertions],
                "failed_assertion_types": [item["assertion_type"] for item in failed_assertions],
                "blocking_failure_count": result["blocking_failure_count"],
                "failure_summary": failure_summary,
                "json_parse_success": result["json_parse_success"],
                "schema_validation_success": result["schema_validation_success"],
                "business_rule_success": result["business_rule_success"],
                "evidence_reference_valid": result["evidence_reference_valid"],
                "candidate_boundary_valid": result["candidate_boundary_valid"],
                "blocking_assertion_failures": sum(1 for item in failed_assertions if item["blocking"]),
                "non_blocking_assertion_failures": sum(1 for item in failed_assertions if not item["blocking"]),
            }
        )
    return records


def _build_failure_taxonomy(failure_records: list[dict[str, Any]]) -> dict[str, Any]:
    by_node = _count_by_key(failure_records, "node_name")
    by_model = _count_by_key(failure_records, "model_config_id")
    by_error_type = _count_by_key(failure_records, "error_type")

    assertion_counts: dict[str, int] = {}
    blocking_count = 0
    non_blocking_count = 0
    schema_failures = 0
    business_rule_failures = 0
    evidence_reference_failures = 0
    candidate_boundary_failures = 0

    for record in failure_records:
        blocking_count += record["blocking_assertion_failures"]
        non_blocking_count += record["non_blocking_assertion_failures"]
        if not record["schema_validation_success"]:
            schema_failures += 1
        if not record["business_rule_success"]:
            business_rule_failures += 1
        if not record["evidence_reference_valid"]:
            evidence_reference_failures += 1
        if not record["candidate_boundary_valid"]:
            candidate_boundary_failures += 1
        for assertion_type in record["failed_assertion_types"]:
            assertion_counts[assertion_type] = assertion_counts.get(assertion_type, 0) + 1

    safe_failures = []
    for record in failure_records:
        safe_failures.append(
            {
                "benchmark_case_id": record["benchmark_case_id"],
                "node_name": record["node_name"],
                "model_config_id": record["model_config_id"],
                "error_type": record["error_type"],
                "failed_assertion_ids": list(record["failed_assertion_ids"]),
                "failed_assertion_types": list(record["failed_assertion_types"]),
                "blocking_failure_count": record["blocking_failure_count"],
                "failure_summary": record["failure_summary"],
            }
        )

    return {
        "failure_total": len(failure_records),
        "by_node": by_node,
        "by_model_config": by_model,
        "by_error_type": by_error_type,
        "by_assertion_type": dict(sorted(assertion_counts.items())),
        "blocking_failure_count": blocking_count,
        "non_blocking_failure_count": non_blocking_count,
        "schema_failure_count": schema_failures,
        "business_rule_failure_count": business_rule_failures,
        "evidence_reference_failure_count": evidence_reference_failures,
        "candidate_boundary_failure_count": candidate_boundary_failures,
        "failed_cases": safe_failures,
    }


def _build_failure_summary(
    result: dict[str, Any],
    failed_assertions: list[dict[str, Any]],
) -> str:
    parts = []
    if result.get("error_type"):
        parts.append(f"error_type={result['error_type']}")
    if failed_assertions:
        assertion_types = ",".join(sorted({item["assertion_type"] for item in failed_assertions}))
        parts.append(f"assertions={assertion_types}")
    error_message = (result.get("error_message") or "").strip()
    if error_message:
        parts.append(" ".join(error_message.split()))
    summary = " | ".join(parts) if parts else "Benchmark failure without additional summary."
    if len(summary) <= FAILURE_SUMMARY_LIMIT:
        return summary
    return summary[: FAILURE_SUMMARY_LIMIT - 3] + "..."


def _group_case_results_by_model(case_results: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {config_id: [] for config_id in EXPECTED_MODEL_CONFIG_IDS}
    for row in case_results:
        grouped.setdefault(row["model_config_id"], []).append(row)
    return grouped


def _routing_sort_key(item: dict[str, Any]) -> tuple[Decimal, float, int, str]:
    return (
        _decimal_or_none(item["estimated_total_cost_cny"]) or Decimal("999999"),
        float(item["average_latency_ms"]),
        int(item["total_tokens"]),
        item["model_config_id"],
    )


def _count_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(key) or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_summary_items(path: Path) -> list[dict[str, Any]]:
    payload = _load_json(path)
    if isinstance(payload, dict):
        return payload.get("summaries", payload.get("items", []))
    return payload


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _decimal_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{value.quantize(Decimal('0.000001'))}"


def _rate_str(value: float) -> str:
    return f"{value:.6f}"


def _ratio_str(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.000000"
    return f"{(numerator / denominator):.6f}"
