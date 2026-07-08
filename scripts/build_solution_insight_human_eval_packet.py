from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.human import (
    ANNOTATION_TEMPLATE_PATH,
    PACKET_PATH,
    build_annotation_template,
    build_review_packets,
    check_packet_outputs,
    write_packet_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Solution Insight human evaluation review packet.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    active_modes = sum(bool(flag) for flag in (args.write, args.check))
    if active_modes > 1:
        print("Choose only one of --write or --check.", file=sys.stderr)
        return 2

    if args.check:
        matches, details = check_packet_outputs()
        if matches:
            print("solution_insight_human_eval_packet_outputs_match")
            return 0
        print(json.dumps(details, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    if args.write:
        payload = write_packet_outputs()
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    plan = {
        "mode": "plan",
        "packet_output_path": str(PACKET_PATH),
        "annotation_template_output_path": str(ANNOTATION_TEMPLATE_PATH),
        "packet_case_count": len(build_review_packets()),
        "annotation_case_count": len(build_annotation_template()),
        "note": "This command does not fabricate reviewer scores. It only prepares packet and empty annotations.",
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
