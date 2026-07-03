from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.retrieval.candidate_generation_v2 import (  # noqa: E402
    CANDIDATE_GENERATION_DOC_PATH,
    CANDIDATE_GENERATION_OUTPUT_PATH,
    RECALL_ROUND_1_OUTPUT_PATH,
    RECALL_ROUND_2_OUTPUT_PATH,
    build_candidate_generation_payload,
    build_plan_payload,
    build_recall_round_1_payload,
    build_recall_round_1_plan_payload,
    build_recall_round_2_payload,
    build_recall_round_2_plan_payload,
    check_candidate_generation_outputs,
    check_recall_round_1_output,
    check_recall_round_2_output,
    write_candidate_generation_outputs,
    write_recall_round_1_output,
    write_recall_round_2_output,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze Retrieval Benchmark v2 candidate-generation strategies without modifying formal results."
    )
    parser.add_argument(
        "--recall-round-1",
        action="store_true",
        help="Run the Round 1 document-aware multi-view vector candidate-recall experiment.",
    )
    parser.add_argument(
        "--recall-round-2",
        action="store_true",
        help="Run the Round 2 hierarchical parent-first child-expansion candidate-recall experiment.",
    )
    parser.add_argument("--write", action="store_true", help="Run offline candidate-generation analysis and write tracked outputs.")
    parser.add_argument("--check", action="store_true", help="Recompute offline candidate-generation analysis and compare against tracked outputs.")
    args = parser.parse_args()

    if args.write and args.check:
        print("Choose either --write or --check, not both.", file=sys.stderr)
        return 2

    if args.recall_round_1 and args.recall_round_2:
        print("Choose only one recall round flag.", file=sys.stderr)
        return 2

    if args.recall_round_2:
        if args.check:
            ok, differences = check_recall_round_2_output()
            print(
                json.dumps(
                    {
                        "mode": "check",
                        "experiment": "recall_round_2",
                        "status": "recall_round_2_output_match" if ok else "recall_round_2_output_drifted",
                        "differences": differences,
                        "output_file": str(RECALL_ROUND_2_OUTPUT_PATH),
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0 if ok else 1

        if args.write:
            payload = build_recall_round_2_payload()
            write_recall_round_2_output(payload)
            print(
                json.dumps(
                    {
                        "mode": "write",
                        "experiment": "recall_round_2",
                        "output_file": str(RECALL_ROUND_2_OUTPUT_PATH),
                        "round_status": payload["round_status"],
                        "candidate_recall_at_20": payload["round_2_metrics"]["candidate_recall_at_20"],
                        "full_recall_case_count_at_20": payload["round_2_metrics"]["full_recall_case_count_at_20"],
                        "success_gate_passed": payload["success_gate"]["passed"],
                        "retriever_v2_status": payload["retriever_v2_status"],
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        print(json.dumps(build_recall_round_2_plan_payload(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.recall_round_1:
        if args.check:
            ok, differences = check_recall_round_1_output()
            print(
                json.dumps(
                    {
                        "mode": "check",
                        "experiment": "recall_round_1",
                        "status": "recall_round_1_output_match" if ok else "recall_round_1_output_drifted",
                        "differences": differences,
                        "output_file": str(RECALL_ROUND_1_OUTPUT_PATH),
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0 if ok else 1

        if args.write:
            payload = build_recall_round_1_payload()
            write_recall_round_1_output(payload)
            print(
                json.dumps(
                    {
                        "mode": "write",
                        "experiment": "recall_round_1",
                        "output_file": str(RECALL_ROUND_1_OUTPUT_PATH),
                        "round_status": payload["round_status"],
                        "candidate_recall_at_20": payload["overall_metrics"]["candidate_recall_at_20"],
                        "full_recall_case_count_at_20": payload["overall_metrics"]["full_recall_case_count_at_20"],
                        "success_gate_passed": payload["success_gate"]["passed"],
                        "next_step": payload["next_step"],
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        print(json.dumps(build_recall_round_1_plan_payload(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.check:
        ok, differences = check_candidate_generation_outputs()
        print(
            json.dumps(
                {
                    "mode": "check",
                    "status": "candidate_generation_outputs_match" if ok else "candidate_generation_outputs_drifted",
                    "differences": differences,
                    "output_file": str(CANDIDATE_GENERATION_OUTPUT_PATH),
                    "doc_file": str(CANDIDATE_GENERATION_DOC_PATH),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if ok else 1

    if args.write:
        payload = build_candidate_generation_payload()
        write_candidate_generation_outputs(payload)
        print(
            json.dumps(
                {
                    "mode": "write",
                    "analysis_version": payload["analysis_version"],
                    "diagnostic_only": payload["diagnostic_only"],
                    "output_file": str(CANDIDATE_GENERATION_OUTPUT_PATH),
                    "doc_file": str(CANDIDATE_GENERATION_DOC_PATH),
                    "candidate_generation_ready": payload["candidate_generation_ready"],
                    "rerank_required": payload["rerank_required"],
                    "query_rewrite_required": payload["query_rewrite_required"],
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
