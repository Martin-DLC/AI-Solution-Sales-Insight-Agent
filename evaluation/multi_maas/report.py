from __future__ import annotations

import json
from pathlib import Path

from evaluation.multi_maas.models import MultiMaaSEvaluationReport


JSON_REPORT_PATH = Path("reports/multi_maas_model_eval.latest.json")
MARKDOWN_REPORT_PATH = Path("reports/multi_maas_model_eval.latest.md")


def write_multi_maas_reports(
    report: MultiMaaSEvaluationReport,
    *,
    json_path: str | Path = JSON_REPORT_PATH,
    markdown_path: str | Path = MARKDOWN_REPORT_PATH,
) -> None:
    resolved_json_path = Path(json_path)
    resolved_markdown_path = Path(markdown_path)
    resolved_json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
    resolved_json_path.write_text(payload + "\n", encoding="utf-8")
    resolved_markdown_path.write_text(render_markdown_report(report), encoding="utf-8")


def render_markdown_report(report: MultiMaaSEvaluationReport) -> str:
    lines = [
        "# Multi-MaaS Model Evaluation Report",
        "",
        "## Run Summary",
        f"- run_id: `{report.run_id}`",
        f"- created_at: `{report.created_at}`",
        f"- dry_run: `{report.dry_run}`",
        f"- total_cases: {report.summary.total_cases}",
        f"- total_targets: {report.summary.total_targets}",
        f"- total_runs: {report.summary.total_runs}",
        "",
        "## Provider / Model Targets",
    ]
    for target in report.targets:
        lines.append(
            f"- `{target.provider_name}` / `{target.model_name}`: adapter=`{target.adapter_type}`, "
            f"verification=`{target.verification_status}`, dry_run=`{target.dry_run}`"
        )
    lines.extend(
        [
            "",
            "## Evaluation Status Counts",
            f"- success_count: {report.summary.success_count}",
            f"- skipped_count: {report.summary.skipped_count}",
            f"- failed_count: {report.summary.failed_count}",
            "",
            "## Metrics Summary",
            f"- schema_valid_rate: `{report.summary.schema_valid_rate}`",
            f"- usage_available_rate: `{report.summary.usage_available_rate}`",
            f"- average_latency_ms: `{report.summary.average_latency_ms}`",
            f"- average_estimated_cost: `{report.summary.average_estimated_cost}`",
            f"- provider_error_rate: `{report.summary.provider_error_rate}`",
            f"- timeout_rate: `{report.summary.timeout_rate}`",
            "",
            "## Per-provider Summary",
        ]
    )
    for summary in report.summary.provider_summaries:
        lines.append(
            f"- `{summary.provider_name}` / `{summary.model_name}`: total={summary.total_runs}, "
            f"success={summary.success_count}, skipped={summary.skipped_count}, failed={summary.failed_count}"
        )
    lines.extend(["", "## Per-case Results"])
    for result in report.results:
        lines.append(
            f"- `{result.case_id}` on `{result.provider_name}` / `{result.model_name}`: "
            f"status=`{result.status}`, schema_valid=`{result.schema_valid}`, "
            f"recovery=`{result.recommended_recovery_action}`"
        )
    lines.extend(
        [
            "",
            "## Recovery Recommendation Summary",
            f"- retry_recommended_count: {report.summary.retry_recommended_count}",
            f"- fallback_recommended_count: {report.summary.fallback_recommended_count}",
            f"- human_review_trigger_count: {report.summary.human_review_trigger_count}",
            "",
            "## Boundary Notes",
            "- skipped_missing_api_key is not a model quality failure conclusion.",
            "- skipped_dry_run is not a model quality result.",
            "- heuristic score does not represent human scoring.",
            "- estimated cost is not real billing.",
            "- not_verified provider status does not mean MaaS integration is complete.",
            "- provider fallback recommendation is not production routing.",
        ]
    )
    for note in report.boundary_notes:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"
