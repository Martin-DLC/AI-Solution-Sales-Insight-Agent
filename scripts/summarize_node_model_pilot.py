from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.model_benchmark.routing import (  # noqa: E402
    build_formal_pilot_summary,
    build_node_model_routing_matrix,
    load_formal_pilot_runs,
)


DEFAULT_RUNS_FILE = (
    PROJECT_ROOT / "data" / "evaluation" / "model_benchmark" / "formal_pilot_runs.v1.json"
)
DEFAULT_SUMMARY_FILE = (
    PROJECT_ROOT / "data" / "evaluation" / "model_benchmark" / "formal_pilot_summary.v1.json"
)
DEFAULT_MATRIX_FILE = (
    PROJECT_ROOT / "data" / "evaluation" / "model_benchmark" / "node_model_routing_matrix.v1.json"
)


def main() -> int:
    runs = load_formal_pilot_runs(DEFAULT_RUNS_FILE)
    summary = build_formal_pilot_summary(runs)
    matrix = build_node_model_routing_matrix(summary)

    _write_json(DEFAULT_SUMMARY_FILE, summary)
    _write_json(DEFAULT_MATRIX_FILE, matrix)

    print(f"Formal pilot runs: {len(runs)}")
    print(f"Summary file: {DEFAULT_SUMMARY_FILE}")
    print(f"Routing matrix file: {DEFAULT_MATRIX_FILE}")
    print(
        "Formal totals: "
        f"planned={summary['totals']['planned']} "
        f"completed={summary['totals']['completed']} "
        f"passed={summary['totals']['passed']} "
        f"failed={summary['totals']['failed']} "
        f"request_errors={summary['totals']['request_errors']}"
    )
    for node in matrix["nodes"]:
        print(
            f"{node['node_name']}: "
            f"status={node['route_status']} "
            f"primary={node['primary_model_config_id']} "
            f"fallback={node['fallback_model_config_id']}"
        )
    return 0


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
