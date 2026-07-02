from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.retrieval.metadata_blind_failure_analysis_v2 import (  # noqa: E402
    TRACKED_FAILURE_ANALYSIS_DOC_PATH,
    TRACKED_FAILURE_ANALYSIS_JSON_PATH,
    build_plan_payload,
    check_failure_analysis_outputs,
    run_blind_failure_analysis,
    write_failure_analysis_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose frozen blind metadata validation failures without modifying any frozen labels."
    )
    parser.add_argument("--write", action="store_true", help="Run failure diagnosis and write tracked outputs.")
    parser.add_argument("--check", action="store_true", help="Recompute and compare tracked failure diagnosis outputs.")
    args = parser.parse_args()

    if args.write and args.check:
        print("Choose either --write or --check, not both.", file=sys.stderr)
        return 2

    if args.check:
        ok, differences = check_failure_analysis_outputs()
        print(
            json.dumps(
                {
                    "mode": "check",
                    "status": "blind_failure_analysis_outputs_match" if ok else "blind_failure_analysis_outputs_drifted",
                    "differences": differences,
                    "tracked_outputs": {
                        "json": str(TRACKED_FAILURE_ANALYSIS_JSON_PATH),
                        "doc": str(TRACKED_FAILURE_ANALYSIS_DOC_PATH),
                    },
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if ok else 1

    if args.write:
        payload = run_blind_failure_analysis()
        write_failure_analysis_outputs(payload)
        print(
            json.dumps(
                {
                    "mode": "write",
                    "unique_error_candidate_count": payload["error_pair_summary"]["unique_error_candidate_count"],
                    "false_exclusion_count": payload["error_pair_summary"]["false_exclusion_count"],
                    "false_inclusion_count": payload["error_pair_summary"]["false_inclusion_count"],
                    "metadata_v2_2_design_required": payload["metadata_v2_2_design_required"],
                    "benchmark_case_review_required": payload["benchmark_case_review_required"],
                    "recommended_next_step": payload["recommended_next_step"],
                    "retriever_v2_status": payload["retriever_v2_status"],
                    "architecture_c_status": payload["architecture_c_status"],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    print(json.dumps(build_plan_payload(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
