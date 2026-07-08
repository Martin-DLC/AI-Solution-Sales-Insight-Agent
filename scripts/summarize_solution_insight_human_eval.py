from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.human import SUMMARY_PATH, build_summary, check_summary, write_summary
from evaluation.human.packet_builder import ANNOTATION_TEMPLATE_PATH


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize Solution Insight human evaluation annotations.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    active_modes = sum(bool(flag) for flag in (args.write, args.check))
    if active_modes > 1:
        print("Choose only one of --write or --check.", file=sys.stderr)
        return 2

    if args.check:
        matches, details = check_summary()
        if matches:
            print("solution_insight_human_eval_summary_matches")
            return 0
        print(json.dumps(details, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    if args.write:
        summary = write_summary()
        print(json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    annotation_ready = ANNOTATION_TEMPLATE_PATH.exists()
    human_review_status = build_summary().human_review_status if annotation_ready else "not_started"
    plan = {
        "mode": "plan",
        "summary_output_path": str(SUMMARY_PATH),
        "annotation_template_ready": annotation_ready,
        "human_review_status": human_review_status,
        "note": (
            "No summary file is written in plan mode. Empty annotations remain unscored."
            if annotation_ready
            else "Annotation template is missing. Run the human eval packet builder with --write first."
        ),
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
