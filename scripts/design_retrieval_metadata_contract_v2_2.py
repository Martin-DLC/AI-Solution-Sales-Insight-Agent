from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.retrieval.metadata_contract_v2_2_design import (  # noqa: E402
    TRACKED_PROPOSAL_DOC_PATH,
    TRACKED_PROPOSAL_OUTPUT_PATH,
    build_metadata_contract_v2_2_payload,
    build_plan_payload,
    check_metadata_contract_v2_2_outputs,
    write_metadata_contract_v2_2_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Design and validate the narrow Retrieval Metadata Contract v2.2 counterfactual proposal."
    )
    parser.add_argument("--write", action="store_true", help="Build the deterministic v2.2 proposal and write tracked outputs.")
    parser.add_argument("--check", action="store_true", help="Recompute and compare tracked v2.2 proposal outputs.")
    args = parser.parse_args()

    if args.write and args.check:
        print("Choose either --write or --check, not both.", file=sys.stderr)
        return 2

    if args.check:
        ok, differences = check_metadata_contract_v2_2_outputs()
        print(
            json.dumps(
                {
                    "mode": "check",
                    "status": "metadata_contract_v2_2_outputs_match" if ok else "metadata_contract_v2_2_outputs_drifted",
                    "differences": differences,
                    "tracked_outputs": {
                        "json": str(TRACKED_PROPOSAL_OUTPUT_PATH),
                        "doc": str(TRACKED_PROPOSAL_DOC_PATH),
                    },
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if ok else 1

    if args.write:
        payload = build_metadata_contract_v2_2_payload()
        write_metadata_contract_v2_2_outputs(payload)
        print(
            json.dumps(
                {
                    "mode": "write",
                    "best_schema_variant": payload["best_schema_variant"]["variant_id"],
                    "all_40_chunks_have_perfect_assignment": payload["best_schema_variant"]["perfect_candidate_count"] == 40,
                    "requires_new_enum_count": payload["single_enum_extension_results"]["requires_new_enum_count"],
                    "metadata_v2_2_ready_for_versioning": payload["metadata_v2_2_ready_for_versioning"],
                    "ready_for_blind_protocol_v2_2": payload["ready_for_blind_protocol_v2_2"],
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
