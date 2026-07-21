from __future__ import annotations

import json
import re
from pathlib import Path

from agent.observability.metrics import RunMetrics


_FORBIDDEN_PATTERN = re.compile(r"(sk-[A-Za-z0-9_-]+|traceback\s+\(most recent call last\)|benchmark gold|hidden reference pack)", re.IGNORECASE)


def write_run_summary_json(metrics: RunMetrics, path: str | Path) -> None:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(metrics.model_dump(mode="json"), ensure_ascii=False, indent=2)
    _ensure_safe_report(payload)
    resolved.write_text(payload + "\n", encoding="utf-8")


def render_cost_summary_report(metrics: RunMetrics) -> str:
    lines = [
        "# Run Summary and Estimated Cost Report",
        "",
        "## Run Overview",
        f"- run_id: `{metrics.run_id}`",
        f"- trace_id: `{metrics.trace_id}`",
        f"- final_status: `{metrics.final_status}`",
        f"- task_success: `{metrics.task_success}`",
        f"- execution_steps: {metrics.execution_steps}",
        f"- total_latency_ms: {metrics.total_latency_ms}",
        "",
        "## Model Usage",
        f"- model_call_count: {metrics.model_call_count}",
        f"- input_tokens: {metrics.input_tokens}",
        f"- output_tokens: {metrics.output_tokens}",
        f"- estimated_model_cost: `{metrics.estimated_model_cost}`",
        f"- cost_is_estimated: `{metrics.cost_is_estimated}`",
        "",
        "## Tool and Permission Usage",
        f"- tool_call_count: {metrics.tool_call_count}",
        f"- permission_check_count: {metrics.permission_check_count}",
        f"- permission_denied_count: {metrics.permission_denied_count}",
        f"- approval_request_count: {metrics.approval_request_count}",
        "",
        "## Risk and Fallback",
        f"- fallback_count: {metrics.fallback_count}",
        f"- human_review_count: {metrics.human_review_count}",
        f"- stopped_by_policy: `{metrics.final_status == 'stopped_by_policy'}`",
        "",
        "## Notes",
        "- Costs are estimated for local demo purposes.",
        "- Deterministic mode does not represent real model billing.",
        "- This report is not a production billing report.",
    ]
    report = "\n".join(lines) + "\n"
    _ensure_safe_report(report)
    return report


def write_cost_summary_report(metrics: RunMetrics, path: str | Path) -> None:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(render_cost_summary_report(metrics), encoding="utf-8")


def _ensure_safe_report(content: str) -> None:
    if _FORBIDDEN_PATTERN.search(content):
        raise ValueError("Run summary report contains forbidden sensitive content.")
