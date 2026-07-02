from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.retrieval.metadata_blind_evaluation_v2 import (  # noqa: E402
    TRACKED_EVALUATION_DOC_PATH,
    TRACKED_EVALUATION_OUTPUT_PATH,
    build_plan_payload,
    check_evaluation_outputs,
    run_blind_metadata_evaluation,
    write_evaluation_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate frozen blind retrieval metadata labels without running any retriever."
    )
    parser.add_argument("--write", action="store_true", help="Run the independent post-freeze evaluation and write tracked outputs.")
    parser.add_argument("--check", action="store_true", help="Recompute and compare tracked blind evaluation outputs.")
    args = parser.parse_args()

    if args.write and args.check:
        print("Choose either --write or --check, not both.", file=sys.stderr)
        return 2

    if args.check:
        ok, differences = check_evaluation_outputs()
        print(
            json.dumps(
                {
                    "mode": "check",
                    "status": "blind_label_evaluation_outputs_match" if ok else "blind_label_evaluation_outputs_drifted",
                    "differences": differences,
                    "tracked_outputs": {
                        "json": str(TRACKED_EVALUATION_OUTPUT_PATH),
                        "doc": str(TRACKED_EVALUATION_DOC_PATH),
                    },
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if ok else 1

    if args.write:
        payload = run_blind_metadata_evaluation()
        write_evaluation_outputs(payload)
        print(
            json.dumps(
                {
                    "mode": "write",
                    "provenance_gate_passed": payload["provenance_gate"]["passed"],
                    "pair_count": payload["pairwise_evaluation_scope"]["pair_count"],
                    "relevant_candidate_retention_rate": payload["overall_metrics"].get("relevant_candidate_retention_rate"),
                    "boundary_candidate_removal_rate": payload["overall_metrics"].get("boundary_candidate_removal_rate"),
                    "p0_validation_status": payload["p0_validation_status"],
                    "metadata_v2_1_versioning_status": payload["metadata_v2_1_versioning_status"],
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
