from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.retrieval.storage import diff_json_objects, load_json_record, load_jsonl_records, write_json_atomic


RETRIEVAL_CASES_PATH = Path("data/evaluation/retrieval/retrieval_cases.v1.jsonl")
DOCUMENTS_PATH = Path("data/knowledge_base/documents.v1.jsonl")
CHUNKS_PATH = Path("data/knowledge_base/chunks.v1.jsonl")
DEMO_SCOPE_PATH = Path("data/knowledge_base/demo_solution_scope.v1.json")
FAILURE_ANALYSIS_PATH = Path("data/evaluation/retrieval/retrieval_failure_analysis.v1.json")
PLAN_OUTPUT_PATH = Path("data/evaluation/retrieval/retrieval_v2_migration_plan.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan deterministic Retrieval Benchmark v2 migration without modifying v1.")
    parser.add_argument("--write", action="store_true", help="Write the tracked v2 migration plan JSON.")
    parser.add_argument("--check", action="store_true", help="Recompute the migration plan and compare with the tracked JSON.")
    args = parser.parse_args()

    if args.write and args.check:
        print("Choose either --write or --check, not both.", file=sys.stderr)
        return 2

    payload = build_migration_plan_payload()
    if args.check:
        tracked = load_json_record(PLAN_OUTPUT_PATH)
        differences = diff_json_objects(tracked, payload)
        if differences:
            for difference in differences:
                print(difference, file=sys.stderr)
            return 1
        print("Retrieval v2 migration plan is up to date.")
        return 0

    if args.write:
        write_json_atomic(PLAN_OUTPUT_PATH, payload)
        print(
            json.dumps(
                {
                    "plan_version": payload["plan_version"],
                    "output_file": str(PLAN_OUTPUT_PATH),
                    "infeasible_v1_case_ids": payload["infeasible_v1_case_ids"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0

    print(
        json.dumps(
            {
                "mode": "plan",
                "v1_document_count": payload["v1_document_count"],
                "v1_chunk_count": payload["v1_chunk_count"],
                "v1_case_count": payload["v1_case_count"],
                "infeasible_v1_case_ids": payload["infeasible_v1_case_ids"],
                "planned_v2_files": payload["required_new_v2_files"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def build_migration_plan_payload() -> dict[str, Any]:
    cases = load_jsonl_records(RETRIEVAL_CASES_PATH)
    documents = load_jsonl_records(DOCUMENTS_PATH)
    chunks = load_jsonl_records(CHUNKS_PATH)
    demo_scope = load_json_record(DEMO_SCOPE_PATH)
    failure_analysis = load_json_record(FAILURE_ANALYSIS_PATH)

    multi_solution_documents = [
        document["document_id"]
        for document in documents
        if len(document.get("solution_ids", [])) > 1
    ]
    all_solution_document_ids = [
        document["document_id"]
        for document in documents
        if document.get("solution_ids")
    ]
    infeasible_case_ids = list(failure_analysis["benchmark_feasibility"]["infeasible_case_ids"])
    taxonomy_misclassification_findings = [
        "v1 empty_query_tokens depends on lexical query_tokens debug and misclassifies vector_v1 and hybrid_v1 failures.",
        "v2 must classify empty_query from the normalized raw query text, not from missing lexical-only debug fields.",
    ]

    document_scope_migration_actions = [
        {
            "action": "document_scope_split_or_narrow",
            "document_ids": multi_solution_documents,
            "reason": "Multi-solution v1 document metadata is too broad for solution-boundary evaluation.",
        },
        {
            "action": "re-express_global_policy_documents",
            "document_ids": ["KB-COM-001"],
            "reason": "Global policy content must move to explicit global_policy semantics instead of broad inherited solution_ids.",
        },
    ]
    chunk_scope_migration_actions = [
        {
            "action": "add_chunk_level_scope_fields",
            "chunk_count": len(chunks),
            "reason": "v2 chunks must be allowed to narrow document scope and must not inherit overly broad solution_ids by default.",
        }
    ]
    case_migration_actions = [
        {
            "retrieval_case_id": "RET-006",
            "action": "rewrite_case_contract",
            "reason": "Expected relevant items conflict with forbidden scope and safe_expected_item_count is 0.",
        },
        {
            "retrieval_case_id": "RET-009",
            "action": "rewrite_case_contract",
            "reason": "Expected relevant items conflict with forbidden scope and safe_expected_item_count is 0.",
        },
        {
            "retrieval_case_id": "RET-001",
            "action": "review_expected_vs_forbidden_scope",
            "reason": "Expected relevant items currently touch forbidden scope through multi-solution metadata.",
        },
        {
            "retrieval_case_id": "RET-002",
            "action": "review_expected_vs_forbidden_scope",
            "reason": "Expected relevant items currently touch forbidden scope through multi-solution metadata.",
        },
        {
            "retrieval_case_id": "RET-005",
            "action": "review_expected_vs_forbidden_scope",
            "reason": "Expected relevant items currently touch forbidden scope through multi-solution metadata.",
        },
    ]
    required_new_v2_files = [
        "data/knowledge_base/documents.v2.jsonl",
        "data/knowledge_base/chunks.v2.jsonl",
        "data/knowledge_base/manifest.v2.json",
        "data/evaluation/retrieval/retrieval_cases.v2.jsonl",
        "data/evaluation/retrieval/retrieval_benchmark_config.v2.json",
        "data/evaluation/retrieval/lexical_baseline_results.v2.jsonl",
        "data/evaluation/retrieval/vector_baseline_results.v2.jsonl",
        "data/evaluation/retrieval/hybrid_baseline_results.v2.jsonl",
    ]
    unchanged_v1_files = [
        "data/evaluation/retrieval/retrieval_cases.v1.jsonl",
        "data/knowledge_base/documents.v1.jsonl",
        "data/knowledge_base/chunks.v1.jsonl",
        "data/knowledge_base/manifest.v1.json",
        "data/evaluation/retrieval/lexical_baseline_summary.v1.json",
        "data/evaluation/retrieval/vector_baseline_summary.v1.json",
        "data/evaluation/retrieval/hybrid_baseline_summary.v1.json",
        "data/evaluation/retrieval/retrieval_method_comparison.v1.json",
        "data/evaluation/retrieval/retrieval_failure_analysis.v1.json",
    ]
    migration_risks = [
        "Chunk-level scope narrowing can reduce accidental boundary violations but may lower recall if gold IDs are not regenerated carefully.",
        "Separating runtime context from evaluation gold requires rewriting forbidden-scope expectations without leaking gold constraints into retriever inputs.",
        "A v2 feasibility gate must block unreachable cases before any formal benchmark run is frozen.",
    ]
    acceptance_criteria = [
        "v1 legacy artifacts remain reproducible and hash-stable.",
        "v2 empty_query classification depends only on normalized raw query text.",
        "v2 knowledge documents and chunks carry explicit scope semantics.",
        "All v2 retrieval cases pass the feasibility validator before formal benchmarking.",
        "No v2 data file overwrites any v1 tracked file.",
    ]

    return {
        "plan_version": "retrieval_v2_migration_plan_v1",
        "v1_document_count": len(documents),
        "v1_chunk_count": len(chunks),
        "v1_case_count": len(cases),
        "demo_solution_ids": list(demo_scope["selected_solution_ids"]),
        "multi_solution_document_ids": multi_solution_documents,
        "all_solution_document_ids": all_solution_document_ids,
        "infeasible_v1_case_ids": infeasible_case_ids,
        "taxonomy_misclassification_findings": taxonomy_misclassification_findings,
        "document_scope_migration_actions": document_scope_migration_actions,
        "chunk_scope_migration_actions": chunk_scope_migration_actions,
        "case_migration_actions": case_migration_actions,
        "required_new_v2_files": required_new_v2_files,
        "unchanged_v1_files": unchanged_v1_files,
        "migration_risks": migration_risks,
        "acceptance_criteria": acceptance_criteria,
        "no_v1_files_modified": True,
    }


if __name__ == "__main__":
    raise SystemExit(main())
