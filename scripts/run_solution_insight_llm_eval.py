from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.llm import build_plan_payload, check_baseline, write_baseline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Solution Insight Agent LLM evaluation harness v0.2.")
    parser.add_argument("--provider", default="deterministic")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if args.write and args.check:
        print("Choose only one of --write or --check.", file=sys.stderr)
        return 2

    if args.check:
        matches, details = check_baseline(provider=args.provider)
        if matches:
            print("solution_insight_llm_eval_outputs_match")
            return 0
        print(json.dumps(details, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    if args.write:
        report = write_baseline(provider=args.provider)
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    plan = build_plan_payload(provider=args.provider)
    print(json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
