from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.model_benchmark import (  # noqa: E402
    BenchmarkPlan,
    NodeModelBenchmarkRunner,
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


if __name__ == "__main__":
    raise SystemExit(main())
