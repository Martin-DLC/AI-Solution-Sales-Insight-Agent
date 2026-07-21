from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.models import SolutionInsightRequest
from agent.observability.metrics import RunMetrics, build_run_metrics
from agent.observability.run_summary import (
    render_cost_summary_report,
    write_cost_summary_report,
    write_run_summary_json,
)
from agent.solution_insight_service import SolutionInsightService


SUMMARY_PATH = Path("reports/latest_run_summary.json")
COST_REPORT_PATH = Path("reports/latest_cost_summary.md")
_FORBIDDEN_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_-]+|traceback\s+\(most recent call last\)|benchmark gold|hidden reference pack)",
    re.IGNORECASE,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate local run summary and estimated cost report.")
    parser.add_argument("--write", action="store_true", help="Write latest run summary artifacts.")
    parser.add_argument("--check", action="store_true", help="Validate generated summary artifacts.")
    args = parser.parse_args(argv)

    response = _run_demo()
    metrics = build_run_metrics(response)
    report = render_cost_summary_report(metrics)

    if args.write:
        write_run_summary_json(metrics, SUMMARY_PATH)
        write_cost_summary_report(metrics, COST_REPORT_PATH)
        print(f"wrote {SUMMARY_PATH}")
        print(f"wrote {COST_REPORT_PATH}")
        return 0

    if args.check:
        _check(metrics, report)
        print("run_summary_report_check_passed")
        return 0

    print(json.dumps(metrics.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def _run_demo():
    service = SolutionInsightService.from_defaults(
        enable_shadow_retrieval=True,
        llm_mode="deterministic",
    )
    return service.generate_insight(
        SolutionInsightRequest(
            user_query="一家中型 SaaS 公司想提升销售线索转化和客户成功效率",
            industry="SaaS",
            company_size="中型",
            company_id="demo_saas_001",
            enable_shadow_retrieval=True,
            llm_mode="deterministic",
        )
    )


def _check(metrics: RunMetrics, report: str) -> None:
    payload = metrics.model_dump(mode="json")
    RunMetrics.model_validate(payload)
    required = {
        "run_id",
        "trace_id",
        "final_status",
        "model_call_count",
        "input_tokens",
        "output_tokens",
        "estimated_model_cost",
        "tool_call_count",
        "permission_check_count",
        "fallback_count",
        "human_review_count",
        "execution_steps",
        "total_latency_ms",
        "task_success",
        "cost_is_estimated",
    }
    missing = required - set(payload)
    if missing:
        raise AssertionError(f"Missing run summary fields: {sorted(missing)}")
    if payload["cost_is_estimated"] is not True:
        raise AssertionError("cost_is_estimated must be true for local demo reports.")
    serialized = json.dumps(payload, ensure_ascii=False) + "\n" + report
    if _FORBIDDEN_PATTERN.search(serialized):
        raise AssertionError("Run summary report contains forbidden sensitive content.")
    if "# Run Summary and Estimated Cost Report" not in report:
        raise AssertionError("Markdown report missing expected heading.")
    if "This report is not a production billing report." not in report:
        raise AssertionError("Markdown report must include billing limitation note.")


if __name__ == "__main__":
    raise SystemExit(main())
