from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.model_providers.openai_compatible import (  # noqa: E402
    MaaSProviderResult,
    build_openai_compatible_provider,
)
from schemas.common_models import StrictBaseModel  # noqa: E402


JSON_REPORT_PATH = Path("reports/maas_provider_smoke_test.latest.json")
MARKDOWN_REPORT_PATH = Path("reports/maas_provider_smoke_test.latest.md")


class MaaSSmokeTestReport(StrictBaseModel):
    run_id: str
    created_at: str
    provider_name: str
    model_name: str
    adapter_type: str
    verification_status: str
    status: str
    api_key_env: str | None
    api_key_present: bool
    dry_run: bool
    latency_ms: int
    usage_available: bool
    estimated_cost: str | None
    error_type: str | None
    error_message: str | None
    recommended_recovery_action: str | None
    boundary_note: str
    result: dict[str, object]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an offline-safe MaaS provider smoke test.")
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--config", default="config/maas_providers.yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    dry_run = True if args.dry_run or args.check or not args.write else False
    provider = build_openai_compatible_provider(
        args.provider,
        path=args.config,
        model_name=args.model,
    )
    result = provider.smoke_test(dry_run=dry_run)
    report = build_report(result)

    if args.write:
        write_reports(report)
    if args.check:
        MaaSSmokeTestReport.model_validate(report.model_dump(mode="json"))
        render_markdown_report(report)
        print("maas_provider_smoke_test_check_passed")
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_report(result: MaaSProviderResult) -> MaaSSmokeTestReport:
    created_at = datetime.now(UTC).isoformat()
    run_id = f"maas-smoke-{created_at}"
    return MaaSSmokeTestReport(
        run_id=run_id,
        created_at=created_at,
        provider_name=result.provider_name,
        model_name=result.model_name,
        adapter_type=result.adapter_type,
        verification_status=result.verification_status,
        status=result.status,
        api_key_env=result.api_key_env,
        api_key_present=result.api_key_present,
        dry_run=result.dry_run,
        latency_ms=result.latency_ms,
        usage_available=result.usage_available,
        estimated_cost=result.estimated_cost,
        error_type=result.error_type,
        error_message=result.error_message,
        recommended_recovery_action=result.recommended_recovery_action,
        boundary_note=result.boundary_note,
        result=result.model_dump(mode="json"),
    )


def render_markdown_report(report: MaaSSmokeTestReport) -> str:
    lines = [
        "# MaaS Provider Smoke Test Report",
        "",
        "## Summary",
        f"- run_id: `{report.run_id}`",
        f"- created_at: `{report.created_at}`",
        f"- provider_name: `{report.provider_name}`",
        f"- model_name: `{report.model_name}`",
        f"- adapter_type: `{report.adapter_type}`",
        f"- verification_status: `{report.verification_status}`",
        f"- status: `{report.status}`",
        f"- api_key_env: `{report.api_key_env}`",
        f"- api_key_present: `{report.api_key_present}`",
        f"- dry_run: `{report.dry_run}`",
        "",
        "## Metrics",
        f"- latency_ms: {report.latency_ms}",
        f"- usage_available: `{report.usage_available}`",
        f"- estimated_cost: `{report.estimated_cost}`",
        "",
        "## Recovery",
        f"- error_type: `{report.error_type}`",
        f"- error_message: `{report.error_message}`",
        f"- recommended_recovery_action: `{report.recommended_recovery_action}`",
        "",
        "## Boundary",
        f"- {report.boundary_note}",
    ]
    return "\n".join(lines) + "\n"


def write_reports(report: MaaSSmokeTestReport) -> None:
    JSON_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
    JSON_REPORT_PATH.write_text(payload + "\n", encoding="utf-8")
    MARKDOWN_REPORT_PATH.write_text(render_markdown_report(report), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
