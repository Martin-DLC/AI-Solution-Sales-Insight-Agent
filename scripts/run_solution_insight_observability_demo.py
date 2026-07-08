from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent import SolutionInsightRequest, SolutionInsightService
from agent.observability import ObservationSnapshot, build_observation_snapshot, render_observation_report


SNAPSHOT_PATH = Path("data/observability/latest_solution_insight_snapshot.json")
REPORT_PATH = Path("data/observability/latest_solution_insight_report.md")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Solution Insight observability demo.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if args.check:
        return _check()

    snapshot, report = _build_demo_artifacts()
    print(json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.write:
        _write(snapshot, report)
        print(f"Wrote snapshot to {SNAPSHOT_PATH}")
        print(f"Wrote report to {REPORT_PATH}")

    return 0


def _build_demo_artifacts() -> tuple[ObservationSnapshot, str]:
    request = SolutionInsightRequest(
        user_query="一家中型 SaaS 公司想提升销售线索转化和客户成功效率",
        company_id="demo_saas_001",
        industry="SaaS",
        enable_shadow_retrieval=True,
        llm_mode="deterministic",
    )
    service = SolutionInsightService.from_defaults(
        enable_shadow_retrieval=True,
        llm_mode="deterministic",
    )
    response = service.generate_insight(request)
    snapshot = build_observation_snapshot(response)
    report = render_observation_report(snapshot)
    return snapshot, report


def _write(snapshot: ObservationSnapshot, report: str) -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    REPORT_PATH.write_text(report, encoding="utf-8")


def _check() -> int:
    snapshot, report = _build_demo_artifacts()
    if not SNAPSHOT_PATH.exists() or not REPORT_PATH.exists():
        raise SystemExit("Observability demo artifacts are missing. Run with --write first.")

    parsed_snapshot = ObservationSnapshot.model_validate_json(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    report_text = REPORT_PATH.read_text(encoding="utf-8")
    if not parsed_snapshot.formal_path.evidence_titles:
        raise SystemExit("Snapshot is missing evidence_titles.")
    if "## Formal Retrieval Path" not in report_text:
        raise SystemExit("Report is missing the Formal Retrieval Path section.")
    if "## Shadow Retrieval Path" not in report_text:
        raise SystemExit("Report is missing the Shadow Retrieval Path section.")
    if not report:
        raise SystemExit("Regenerated report is empty.")
    print("solution_insight_observability_demo_check_passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
