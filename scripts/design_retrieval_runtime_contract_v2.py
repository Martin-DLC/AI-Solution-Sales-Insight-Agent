from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.retrieval.runtime_contract_design_v2 import (  # noqa: E402
    RUNTIME_CONTRACT_PROPOSAL_DOC_PATH,
    RUNTIME_CONTRACT_PROPOSAL_OUTPUT_PATH,
    build_plan_payload,
    build_runtime_contract_design_payload,
    check_runtime_contract_outputs,
    write_runtime_contract_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Design a retrieval runtime boundary contract v2.1 without modifying frozen retriever artifacts."
    )
    parser.add_argument("--write", action="store_true", help="Run the deterministic contract analysis and write tracked outputs.")
    parser.add_argument("--check", action="store_true", help="Recompute the deterministic contract analysis and compare tracked outputs.")
    args = parser.parse_args()

    if args.write and args.check:
        print("Choose either --write or --check, not both.", file=sys.stderr)
        return 2

    if args.check:
        ok, differences = check_runtime_contract_outputs()
        print(
            json.dumps(
                {
                    "mode": "check",
                    "status": "runtime_contract_outputs_match" if ok else "runtime_contract_outputs_drifted",
                    "differences": differences,
                    "output_file": str(RUNTIME_CONTRACT_PROPOSAL_OUTPUT_PATH),
                    "doc_file": str(RUNTIME_CONTRACT_PROPOSAL_DOC_PATH),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if ok else 1

    if args.write:
        payload = build_runtime_contract_design_payload()
        write_runtime_contract_outputs(payload)
        print(
            json.dumps(
                {
                    "mode": "write",
                    "proposal_version": payload["proposal_version"],
                    "diagnostic_only": payload["diagnostic_only"],
                    "evidence_classification": payload["evidence_classification"],
                    "proposed_upgrade_scope": payload["proposed_upgrade_scope"],
                    "final_upgrade_scope_decision": payload["final_upgrade_scope_decision"],
                    "boundary_contract_ready_for_versioning": payload["boundary_contract_ready_for_versioning"],
                    "retriever_v2_ready_for_implementation": payload["retriever_v2_ready_for_implementation"],
                    "architecture_c_status": payload["architecture_c_status"],
                    "output_file": str(RUNTIME_CONTRACT_PROPOSAL_OUTPUT_PATH),
                    "doc_file": str(RUNTIME_CONTRACT_PROPOSAL_DOC_PATH),
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
