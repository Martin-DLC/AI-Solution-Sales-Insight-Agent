from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.retrieval.separability_v2 import (  # noqa: E402
    SEPARABILITY_DOC_PATH,
    SEPARABILITY_OUTPUT_PATH,
    build_plan_payload,
    build_separability_payload,
    check_separability_outputs,
    write_separability_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze Retrieval Benchmark v2 runtime separability and deterministic query/field strategies."
    )
    parser.add_argument("--write", action="store_true", help="Run deterministic offline separability analysis and write tracked outputs.")
    parser.add_argument("--check", action="store_true", help="Recompute separability analysis and compare with tracked outputs.")
    args = parser.parse_args()

    if args.write and args.check:
        print("Choose either --write or --check, not both.", file=sys.stderr)
        return 2

    if args.check:
        ok, differences = check_separability_outputs()
        print(
            json.dumps(
                {
                    "mode": "check",
                    "status": "separability_outputs_match" if ok else "separability_outputs_drifted",
                    "differences": differences,
                    "output_file": str(SEPARABILITY_OUTPUT_PATH),
                    "doc_file": str(SEPARABILITY_DOC_PATH),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if ok else 1

    if args.write:
        payload = build_separability_payload()
        write_separability_outputs(payload)
        print(
            json.dumps(
                {
                    "mode": "write",
                    "analysis_version": payload["analysis_version"],
                    "diagnostic_only": payload["diagnostic_only"],
                    "output_file": str(SEPARABILITY_OUTPUT_PATH),
                    "doc_file": str(SEPARABILITY_DOC_PATH),
                    "retriever_v2_ready_for_implementation": payload["retriever_v2_ready_for_implementation"],
                    "runtime_contract_upgrade_required": payload["runtime_contract_upgrade_required"],
                    "benchmark_case_upgrade_required": payload["benchmark_case_upgrade_required"],
                    "recommended_next_step": payload["recommended_next_step"],
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
