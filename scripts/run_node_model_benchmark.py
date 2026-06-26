from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.model_benchmark import (  # noqa: E402
    BenchmarkExecutionMode,
    BenchmarkPlan,
    NodeModelBenchmarkRunner,
    create_deepseek_live_client_factory,
    create_replay_client_factory,
    format_benchmark_plan,
    load_model_benchmark_configs,
    load_node_benchmark_cases,
    load_replay_records,
)


DEFAULT_CASES_FILE = PROJECT_ROOT / "data" / "evaluation" / "model_benchmark" / "node_cases.jsonl"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "runtime" / "model_benchmark_runs"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the node model benchmark.")
    parser.add_argument("--cases-file", default=str(DEFAULT_CASES_FILE))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--case", dest="case_ids", action="append")
    parser.add_argument("--model-config", dest="model_config_ids", action="append")
    parser.add_argument("--configs")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-live", action="store_true")
    parser.add_argument("--max-budget-cny")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate", action="store_true")
    mode.add_argument("--replay")
    args = parser.parse_args(argv)

    try:
        cases = load_node_benchmark_cases(Path(args.cases_file))
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to load benchmark cases: {exc}", file=sys.stderr)
        return 1

    if args.validate:
        try:
            runner = NodeModelBenchmarkRunner(
                cases=cases,
                model_configs=[],
                client_factory=_no_client_factory,
                output_root=args.output_root,
            )
            summary = runner.validate(project_root=PROJECT_ROOT)
        except Exception as exc:  # noqa: BLE001
            print(f"Benchmark validation failed: {exc}", file=sys.stderr)
            return 1
        print("Benchmark dataset validation passed.")
        print(f"Total benchmark cases: {summary['total_cases']}")
        print(f"Total model configs: {summary['total_models']}")
        print(f"Planned runs: {summary['planned_runs']}")
        return 0

    if args.live:
        if args.replay:
            print("--live cannot be used together with --replay.", file=sys.stderr)
            return 1
        if not args.confirm_live:
            print("--live requires --confirm-live.", file=sys.stderr)
            return 1
        if not args.configs:
            print("--live requires --configs.", file=sys.stderr)
            return 1
        if args.max_budget_cny is None:
            print("--live requires --max-budget-cny.", file=sys.stderr)
            return 1
        try:
            max_budget_cny = _parse_positive_decimal(args.max_budget_cny)
            model_configs = load_model_benchmark_configs(Path(args.configs))
            runner = NodeModelBenchmarkRunner(
                cases=cases,
                model_configs=model_configs,
                client_factory=create_deepseek_live_client_factory(),
                output_root=args.output_root,
                capture_debug_artifacts=False,
            )
            selected_cases = runner._filter_cases(args.case_ids)
            selected_model_configs = runner._filter_model_configs(args.model_config_ids)
        except Exception as exc:  # noqa: BLE001
            print(f"Benchmark live setup failed: {exc}", file=sys.stderr)
            return 1
        print("Node Model Benchmark Live Plan")
        print(f"  Selected cases: {len(selected_cases)}")
        print(f"  Selected model configs: {len(selected_model_configs)}")
        print(f"  Planned runs: {len(selected_cases) * len(selected_model_configs)}")
        print(f"  Models: {', '.join(config.model for config in selected_model_configs)}")
        print(
            "  Thinking modes: "
            + ", ".join(f"{config.config_id}={config.thinking_mode.value}" for config in selected_model_configs)
        )
        print(f"  Max budget (CNY): {max_budget_cny}")
        try:
            report = runner.run(
                case_ids=args.case_ids,
                model_config_ids=args.model_config_ids,
                fail_fast=args.fail_fast,
                execution_mode=BenchmarkExecutionMode.live,
                max_budget_cny=max_budget_cny,
                live_confirmed=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Benchmark live failed: {exc}", file=sys.stderr)
            return 1
        print(f"Run ID: {report.manifest.run_id}")
        print(f"Output directory: {report.manifest.output_directory}")
        print(f"Completed runs: {report.manifest.completed_run_count}")
        print(f"Passed: {report.manifest.passed_count}")
        print(f"Failed: {report.manifest.failed_count}")
        print(f"Request errors: {report.manifest.request_error_count}")
        print(f"Estimated cost (CNY): {report.manifest.estimated_cost_cny}")
        print(f"Stopped by budget: {report.manifest.stopped_by_budget}")
        return 1 if report.manifest.request_error_count > 0 else 0

    if args.replay:
        if not args.configs:
            print("--configs is required when using --replay.", file=sys.stderr)
            return 1
        try:
            model_configs = load_model_benchmark_configs(Path(args.configs))
            replay_records = load_replay_records(Path(args.replay))
            runner = NodeModelBenchmarkRunner(
                cases=cases,
                model_configs=model_configs,
                client_factory=create_replay_client_factory(replay_records=replay_records),
                output_root=args.output_root,
            )
            report = runner.run(
                case_ids=args.case_ids,
                model_config_ids=args.model_config_ids,
                fail_fast=args.fail_fast,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Benchmark replay failed: {exc}", file=sys.stderr)
            return 1
        print(f"Run ID: {report.manifest.run_id}")
        print(f"Output directory: {report.manifest.output_directory}")
        print(f"Planned runs: {report.manifest.planned_run_count}")
        print(f"Completed runs: {report.manifest.completed_run_count}")
        print(f"Passed: {report.manifest.passed_count}")
        print(f"Failed: {report.manifest.failed_count}")
        print(f"Request errors: {report.manifest.request_error_count}")
        print(f"Nodes summarized: {len(report.summaries)}")
        return 0

    try:
        runner = NodeModelBenchmarkRunner(
            cases=cases,
            model_configs=[],
            client_factory=_no_client_factory,
            output_root=args.output_root,
        )
        plan: BenchmarkPlan = runner.plan()
    except Exception as exc:  # noqa: BLE001
        print(f"Benchmark plan failed: {exc}", file=sys.stderr)
        return 1

    print(format_benchmark_plan(plan))
    return 0


def _no_client_factory(*args, **kwargs):  # type: ignore[no-untyped-def]
    raise RuntimeError("Benchmark plan/validate modes must not create an LLM client.")


def _parse_positive_decimal(raw_value: str) -> Decimal:
    try:
        value = Decimal(raw_value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Budget must be a valid decimal number.") from exc
    if value <= 0:
        raise ValueError("Budget must be greater than 0.")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
