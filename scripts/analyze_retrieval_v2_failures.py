from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.retrieval.diagnostics_v2 import (  # noqa: E402
    DIAGNOSIS_DOC_PATH,
    DIAGNOSIS_OUTPUT_PATH,
    build_diagnosis_payload,
    build_plan_payload,
    check_diagnosis_outputs,
    write_diagnosis_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose Retrieval Benchmark v2 failures without modifying formal results.")
    parser.add_argument("--write", action="store_true", help="Run offline diagnostics and write the tracked JSON plus Markdown report.")
    parser.add_argument("--check", action="store_true", help="Recompute diagnostics and compare against the tracked outputs.")
    args = parser.parse_args()

    if args.write and args.check:
        print("Choose either --write or --check, not both.", file=sys.stderr)
        return 2

    if args.check:
        ok, differences = check_diagnosis_outputs()
        payload = {
            "mode": "check",
            "status": "diagnosis_outputs_match" if ok else "diagnosis_outputs_drifted",
            "differences": differences,
            "output_file": str(DIAGNOSIS_OUTPUT_PATH),
            "doc_file": str(DIAGNOSIS_DOC_PATH),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if ok else 1

    if args.write:
        payload = build_diagnosis_payload()
        write_diagnosis_outputs(payload)
        print(
            json.dumps(
                {
                    "mode": "write",
                    "diagnosis_version": payload["diagnosis_version"],
                    "output_file": str(DIAGNOSIS_OUTPUT_PATH),
                    "doc_file": str(DIAGNOSIS_DOC_PATH),
                    "diagnostic_only": payload["diagnostic_only"],
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
