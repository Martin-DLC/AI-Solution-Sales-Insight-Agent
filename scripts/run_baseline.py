from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dataio.runtime_cases import load_runtime_cases  # noqa: E402
from evaluation.baselines import (  # noqa: E402
    BaselineArchitecture,
    BaselineARunner,
    BaselineRunStatus,
    calculate_prompt_sha256,
    render_baseline_a_prompt,
)
from llm import LLMConfig, create_llm_client  # noqa: E402


DEFAULT_CASES_FILE = PROJECT_ROOT / "data" / "evaluation" / "development_cases.jsonl"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Baseline A sales insight experiment.")
    parser.add_argument("--case", required=True, dest="case_id")
    parser.add_argument("--architecture", required=True)
    parser.add_argument("--cases-file", default=str(DEFAULT_CASES_FILE))
    parser.add_argument("--output-root", default="data/runtime/baseline_runs")
    parser.add_argument("--prompt-version", default="baseline_a_v1")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)

    if args.architecture != BaselineArchitecture.A.value:
        print("Only architecture A is supported in this runner.", file=sys.stderr)
        return 1

    cases_file = Path(args.cases_file)
    if not cases_file.exists():
        print(f"Cases file does not exist: {cases_file}", file=sys.stderr)
        return 1

    try:
        cases = load_runtime_cases(cases_file)
    except Exception as exc:
        print(f"Failed to load runtime cases: {exc}", file=sys.stderr)
        return 1

    case = next((item for item in cases if item.case_id == args.case_id), None)
    if case is None:
        print(f"Case ID not found: {args.case_id}", file=sys.stderr)
        return 1

    try:
        prompt = render_baseline_a_prompt(case, version=args.prompt_version)
    except Exception as exc:
        print(f"Failed to render prompt: {exc}", file=sys.stderr)
        return 1
    prompt_sha256 = calculate_prompt_sha256(prompt)

    if not args.live:
        print(f"Case ID: {case.case_id}")
        print(f"Architecture: {args.architecture}")
        print(f"Prompt version: {args.prompt_version}")
        print(f"Prompt SHA256: {prompt_sha256}")
        print(f"Prompt characters: {len(prompt)}")
        print("Live model call is disabled. Re-run with --live to continue.")
        return 0

    try:
        config = LLMConfig.from_env()
        client = create_llm_client(config)
        runner = BaselineARunner(client, config, output_root=args.output_root)
        record = runner.run_case(case, prompt_version=args.prompt_version)
    except Exception as exc:
        print(f"Baseline A run failed: {exc}", file=sys.stderr)
        return 1

    if record.status is BaselineRunStatus.failed:
        print(f"Baseline A run failed: {record.error_type}: {record.error_message}", file=sys.stderr)
        print(f"Output directory: {record.output_directory}")
        return 1

    print(f"Run ID: {record.run_id}")
    print(f"Case ID: {record.case_id}")
    print(f"Architecture: {record.architecture.value}")
    print(f"Model: {record.model}")
    print(f"Latency: {record.latency_ms} ms")
    print(f"Prompt tokens: {record.usage.prompt_tokens}")
    print(f"Completion tokens: {record.usage.completion_tokens}")
    print(f"Total tokens: {record.usage.total_tokens}")
    print(f"Output directory: {record.output_directory}")
    print(f"Run status: {record.status.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
