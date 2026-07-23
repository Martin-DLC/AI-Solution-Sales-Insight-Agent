from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.multi_maas.models import MultiMaaSEvaluationReport  # noqa: E402
from evaluation.multi_maas.report import render_markdown_report, write_multi_maas_reports  # noqa: E402
from evaluation.multi_maas.runner import run_multi_maas_evaluation  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run offline-safe Multi-MaaS model evaluation.")
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--config", default="config/maas_providers.yaml")
    parser.add_argument("--cases", default="evaluation/multi_maas/cases.jsonl")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--selection-policy", default="conservative_eval_policy")
    parser.add_argument("--selection-config", default="config/maas_selection_policies.yaml")
    args = parser.parse_args(argv)

    dry_run = True if args.dry_run or args.check or not args.write else False
    report = run_multi_maas_evaluation(
        provider_name=args.provider,
        model_name=args.model,
        cases_path=args.cases,
        config_path=args.config,
        dry_run=dry_run,
        policy_name=args.selection_policy,
        selection_config_path=args.selection_config,
    )

    if args.write:
        write_multi_maas_reports(report)
    if args.check:
        MultiMaaSEvaluationReport.model_validate(report.model_dump(mode="json"))
        render_markdown_report(report)
        print("multi_maas_model_eval_check_passed")
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
