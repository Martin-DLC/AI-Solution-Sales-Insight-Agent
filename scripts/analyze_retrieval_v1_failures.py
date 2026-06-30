from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.retrieval.storage import diff_json_objects, load_json_record, load_jsonl_records, write_json_atomic


RETRIEVAL_CASES_PATH = Path("data/evaluation/retrieval/retrieval_cases.v1.jsonl")
LEXICAL_RESULTS_PATH = Path("data/evaluation/retrieval/lexical_baseline_results.v1.jsonl")
LEXICAL_SUMMARY_PATH = Path("data/evaluation/retrieval/lexical_baseline_summary.v1.json")
VECTOR_RESULTS_PATH = Path("data/evaluation/retrieval/vector_baseline_results.v1.jsonl")
VECTOR_SUMMARY_PATH = Path("data/evaluation/retrieval/vector_baseline_summary.v1.json")
HYBRID_RESULTS_PATH = Path("data/evaluation/retrieval/hybrid_baseline_results.v1.jsonl")
HYBRID_SUMMARY_PATH = Path("data/evaluation/retrieval/hybrid_baseline_summary.v1.json")
COMPARISON_PATH = Path("data/evaluation/retrieval/retrieval_method_comparison.v1.json")
DOCUMENTS_PATH = Path("data/knowledge_base/documents.v1.jsonl")
CHUNKS_PATH = Path("data/knowledge_base/chunks.v1.jsonl")
DEMO_SCOPE_PATH = Path("data/knowledge_base/demo_solution_scope.v1.json")
ANALYSIS_OUTPUT_PATH = Path("data/evaluation/retrieval/retrieval_failure_analysis.v1.json")

ARTIFACT_PATHS = {
    "retrieval_cases": RETRIEVAL_CASES_PATH,
    "lexical_results": LEXICAL_RESULTS_PATH,
    "lexical_summary": LEXICAL_SUMMARY_PATH,
    "vector_results": VECTOR_RESULTS_PATH,
    "vector_summary": VECTOR_SUMMARY_PATH,
    "hybrid_results": HYBRID_RESULTS_PATH,
    "hybrid_summary": HYBRID_SUMMARY_PATH,
    "method_comparison": COMPARISON_PATH,
    "knowledge_documents": DOCUMENTS_PATH,
    "knowledge_chunks": CHUNKS_PATH,
    "demo_solution_scope": DEMO_SCOPE_PATH,
}

METHOD_LABELS = ("lexical", "vector", "hybrid")
COUNTERFACTUAL_EXCLUDED_REASONS = {"empty_query_tokens"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze frozen retrieval v1 failures without rerunning retrieval.")
    parser.add_argument("--write", action="store_true", help="Write the tracked retrieval failure analysis JSON.")
    parser.add_argument("--check", action="store_true", help="Recompute the analysis and compare with the tracked JSON.")
    args = parser.parse_args()

    if args.write and args.check:
        print("Choose either --write or --check, not both.", file=sys.stderr)
        return 2

    analysis = build_analysis_payload()
    if args.check:
        tracked = load_json_record(ANALYSIS_OUTPUT_PATH)
        differences = diff_json_objects(tracked, analysis)
        if differences:
            for difference in differences:
                print(difference, file=sys.stderr)
            return 1
        print("Retrieval failure analysis artifacts are up to date.")
        return 0

    if args.write:
        write_json_atomic(ANALYSIS_OUTPUT_PATH, analysis)
        print(
            json.dumps(
                {
                    "analysis_version": analysis["analysis_version"],
                    "output_file": str(ANALYSIS_OUTPUT_PATH),
                    "infeasible_case_ids": analysis["benchmark_feasibility"]["infeasible_case_ids"],
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
                "methods": list(METHOD_LABELS),
                "retrieval_case_count": 16,
                "document_count": 20,
                "chunk_count": 40,
                "planned_analysis_items": [
                    "empty_query_tokens_audit",
                    "empty_query_tokens_counterfactual",
                    "boundary_violation_summary",
                    "benchmark_feasibility",
                    "knowledge_metadata_findings",
                    "v2_recommendations",
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def build_analysis_payload() -> dict[str, Any]:
    artifact_hashes_before = compute_artifact_hashes()
    cases = load_jsonl_records(RETRIEVAL_CASES_PATH)
    lexical_results = load_jsonl_records(LEXICAL_RESULTS_PATH)
    vector_results = load_jsonl_records(VECTOR_RESULTS_PATH)
    hybrid_results = load_jsonl_records(HYBRID_RESULTS_PATH)
    documents = load_jsonl_records(DOCUMENTS_PATH)
    chunks = load_jsonl_records(CHUNKS_PATH)
    demo_scope = load_json_record(DEMO_SCOPE_PATH)
    lexical_summary = load_json_record(LEXICAL_SUMMARY_PATH)
    vector_summary = load_json_record(VECTOR_SUMMARY_PATH)
    hybrid_summary = load_json_record(HYBRID_SUMMARY_PATH)
    comparison = load_json_record(COMPARISON_PATH)

    cases_by_id = {case["retrieval_case_id"]: case for case in cases}
    documents_by_id = {document["document_id"]: document for document in documents}
    chunks_by_id = {chunk["chunk_id"]: chunk for chunk in chunks}
    selected_solution_ids = set(demo_scope["selected_solution_ids"])

    original_method_summaries = {
        "lexical": _extract_method_summary(lexical_summary),
        "vector": _extract_method_summary(vector_summary),
        "hybrid": _extract_method_summary(hybrid_summary),
        "comparison": {
            "selected_method": comparison.get("selected_method"),
            "selection_status": comparison.get("selection_status"),
            "selection_reasons": list(comparison.get("selection_reasons", [])),
            "rejected_methods": comparison.get("rejected_methods", []),
            "comparison_limitations": list(comparison.get("comparison_limitations", [])),
        },
    }

    empty_query_tokens_audit = build_empty_query_tokens_audit(
        cases=cases,
        vector_results=vector_results,
        hybrid_results=hybrid_results,
    )
    counterfactual = build_empty_query_tokens_counterfactual(
        vector_results=vector_results,
        hybrid_results=hybrid_results,
    )
    boundary_summary, boundary_cause_counts, per_case_boundary = build_boundary_analysis(
        cases_by_id=cases_by_id,
        documents_by_id=documents_by_id,
        chunks_by_id=chunks_by_id,
        selected_solution_ids=selected_solution_ids,
        lexical_results=lexical_results,
        vector_results=vector_results,
        hybrid_results=hybrid_results,
    )
    feasibility = build_benchmark_feasibility(
        cases=cases,
        documents_by_id=documents_by_id,
        chunks_by_id=chunks_by_id,
    )
    metadata_findings = build_knowledge_metadata_findings(documents=documents, chunks=chunks)
    evaluation_contract_findings = build_evaluation_contract_findings(
        feasibility=feasibility,
        per_case_boundary=per_case_boundary,
    )
    retriever_quality_findings = build_retriever_quality_findings(
        lexical_results=lexical_results,
        vector_results=vector_results,
        hybrid_results=hybrid_results,
    )
    blocking_gate_findings = build_blocking_gate_findings(
        original_method_summaries=original_method_summaries,
        counterfactual=counterfactual,
        feasibility=feasibility,
    )
    per_case_analysis = build_per_case_analysis(
        cases=cases,
        documents_by_id=documents_by_id,
        chunks_by_id=chunks_by_id,
        lexical_results=lexical_results,
        vector_results=vector_results,
        hybrid_results=hybrid_results,
        per_case_boundary=per_case_boundary,
        feasibility=feasibility,
    )

    analysis = {
        "analysis_version": "retrieval_failure_analysis_v1",
        "frozen_artifact_hashes": artifact_hashes_before,
        "dataset_scope": {
            "retrieval_case_count": len(cases),
            "document_count": len(documents),
            "chunk_count": len(chunks),
            "demo_solution_count": len(demo_scope["selected_solution_ids"]),
            "demo_solution_ids": list(demo_scope["selected_solution_ids"]),
            "methods": list(METHOD_LABELS),
        },
        "original_method_summaries": original_method_summaries,
        "empty_query_tokens_audit": empty_query_tokens_audit,
        "empty_query_tokens_counterfactual": counterfactual,
        "boundary_violation_summary": boundary_summary,
        "boundary_cause_counts": boundary_cause_counts,
        "per_case_analysis": per_case_analysis,
        "benchmark_feasibility": feasibility,
        "knowledge_metadata_findings": metadata_findings,
        "evaluation_contract_findings": evaluation_contract_findings,
        "retriever_quality_findings": retriever_quality_findings,
        "blocking_gate_findings": blocking_gate_findings,
        "v2_recommendations": build_v2_recommendations(
            feasibility=feasibility,
            metadata_findings=metadata_findings,
        ),
        "no_input_artifacts_modified": artifact_hashes_before == compute_artifact_hashes(),
    }
    return analysis


def compute_artifact_hashes() -> dict[str, str]:
    return {label: _sha256(path) for label, path in ARTIFACT_PATHS.items()}


def build_empty_query_tokens_audit(
    *,
    cases: list[dict[str, Any]],
    vector_results: list[dict[str, Any]],
    hybrid_results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "runner_trigger": "not retrieval_debug.get('query_tokens')",
        "query_tokens_is_lexical_debug_field": True,
        "vector_debug_contract_includes_query_tokens": False,
        "hybrid_debug_contract_includes_query_tokens": False,
        "raw_query_empty_case_ids": [case["retrieval_case_id"] for case in cases if not case["query"].strip()],
        "vector_case_count": len(vector_results),
        "hybrid_case_count": len(hybrid_results),
        "vector_case_ids_with_candidates": [
            result["retrieval_case_id"] for result in vector_results if result["retrieved_candidates"]
        ],
        "hybrid_case_ids_with_candidates": [
            result["retrieval_case_id"] for result in hybrid_results if result["retrieved_candidates"]
        ],
        "vector_all_cases_have_candidates": all(bool(result["retrieved_candidates"]) for result in vector_results),
        "hybrid_all_cases_have_candidates": all(bool(result["retrieved_candidates"]) for result in hybrid_results),
        "vector_candidate_count": sum(len(result["retrieved_candidates"]) for result in vector_results),
        "hybrid_candidate_count": sum(len(result["retrieved_candidates"]) for result in hybrid_results),
        "vector_candidates_with_empty_matched_terms": sum(
            1
            for result in vector_results
            for candidate in result["retrieved_candidates"]
            if not candidate["matched_terms"]
        ),
        "hybrid_candidates_with_empty_matched_terms": sum(
            1
            for result in hybrid_results
            for candidate in result["retrieved_candidates"]
            if not candidate["matched_terms"]
        ),
        "vector_empty_query_tokens_case_ids": [
            result["retrieval_case_id"] for result in vector_results if "empty_query_tokens" in result["failure_reasons"]
        ],
        "hybrid_empty_query_tokens_case_ids": [
            result["retrieval_case_id"] for result in hybrid_results if "empty_query_tokens" in result["failure_reasons"]
        ],
        "classification": "failure_taxonomy_misclassification",
        "impacts_formal_ranking_or_metric_values": False,
        "impacts_failure_reasons": True,
        "impacts_summary_disqualification_reasons": True,
        "impacts_failed_case_ids": False,
        "impacts_eligible_for_rag": False,
    }


def build_empty_query_tokens_counterfactual(
    *,
    vector_results: list[dict[str, Any]],
    hybrid_results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "counterfactual_only": True,
        "excluded_failure_reasons": sorted(COUNTERFACTUAL_EXCLUDED_REASONS),
        "vector": _counterfactual_method_summary(vector_results),
        "hybrid": _counterfactual_method_summary(hybrid_results),
    }


def build_boundary_analysis(
    *,
    cases_by_id: dict[str, dict[str, Any]],
    documents_by_id: dict[str, dict[str, Any]],
    chunks_by_id: dict[str, dict[str, Any]],
    selected_solution_ids: set[str],
    lexical_results: list[dict[str, Any]],
    vector_results: list[dict[str, Any]],
    hybrid_results: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    per_case_boundary: dict[str, dict[str, Any]] = defaultdict(dict)
    summary: dict[str, Any] = {}
    cause_counts: dict[str, Any] = {}
    for method, rows in {
        "lexical": lexical_results,
        "vector": vector_results,
        "hybrid": hybrid_results,
    }.items():
        candidate_counter: Counter[str] = Counter()
        case_counter: Counter[str] = Counter()
        affected_cases: list[str] = []
        for row in rows:
            case = cases_by_id[row["retrieval_case_id"]]
            case_analysis = analyze_boundary_for_case(
                case=case,
                result=row,
                documents_by_id=documents_by_id,
                chunks_by_id=chunks_by_id,
                selected_solution_ids=selected_solution_ids,
            )
            per_case_boundary[row["retrieval_case_id"]][method] = case_analysis
            if case_analysis["violation_candidate_count"] > 0:
                affected_cases.append(row["retrieval_case_id"])
            for cause in case_analysis["case_level_cause_tags"]:
                case_counter[cause] += 1
            for candidate in case_analysis["violation_candidates"]:
                for cause in candidate["cause_tags"]:
                    candidate_counter[cause] += 1
        summary[method] = {
            "affected_case_ids": affected_cases,
            "affected_case_count": len(affected_cases),
            "candidate_violation_count": sum(
                case_data[method]["violation_candidate_count"]
                for case_data in per_case_boundary.values()
                if method in case_data
            ),
        }
        cause_counts[method] = {
            "case_level": dict(sorted(case_counter.items())),
            "candidate_level": dict(sorted(candidate_counter.items())),
        }
    return summary, cause_counts, per_case_boundary


def analyze_boundary_for_case(
    *,
    case: dict[str, Any],
    result: dict[str, Any],
    documents_by_id: dict[str, dict[str, Any]],
    chunks_by_id: dict[str, dict[str, Any]],
    selected_solution_ids: set[str],
) -> dict[str, Any]:
    expected_documents = set(case["expected_relevant_document_ids"])
    expected_chunks = set(case["expected_relevant_chunk_ids"])
    required_solution_ids = set(case["required_solution_ids"])
    forbidden_solution_ids = set(case["forbidden_solution_ids"])
    violation_candidates: list[dict[str, Any]] = []
    case_level_tags: set[str] = set()
    for candidate in result["retrieved_candidates"]:
        solution_ids = list(candidate["solution_ids"])
        solution_set = set(solution_ids)
        violates_required = bool(required_solution_ids) and not solution_set.issubset(required_solution_ids)
        violates_forbidden = bool(solution_set & forbidden_solution_ids)
        if not (violates_required or violates_forbidden):
            continue
        cause_tags: list[str] = []
        if any(solution_id not in selected_solution_ids for solution_id in solution_ids):
            cause_tags.append("out_of_scope_solution_reference")
        is_expected = candidate["document_id"] in expected_documents or candidate["chunk_id"] in expected_chunks
        if is_expected:
            cause_tags.append("expected_document_contains_forbidden_solution")
        if len(solution_ids) > 1:
            cause_tags.append("multi_solution_document_overlap")
        if required_solution_ids and any(solution_id in selected_solution_ids and solution_id not in required_solution_ids for solution_id in solution_ids):
            cause_tags.append("cross_solution_retrieval")
        if "solution_ids" not in case["filters"]:
            cause_tags.append("operational_filter_gap")
        if is_expected and len(solution_ids) > 1:
            cause_tags.append("gold_boundary_overconstraint")
        if not cause_tags:
            cause_tags.append("unknown_boundary_cause")
        case_level_tags.update(cause_tags)
        violation_candidates.append(
            {
                "rank": candidate["rank"],
                "document_id": candidate["document_id"],
                "chunk_id": candidate["chunk_id"],
                "document_type": candidate["metadata"].get("document_type"),
                "solution_ids": solution_ids,
                "is_expected_relevant": is_expected,
                "violates_required": violates_required,
                "violates_forbidden": violates_forbidden,
                "forbidden_solution_overlap": sorted(solution_set & forbidden_solution_ids),
                "cause_tags": sorted(set(cause_tags)),
            }
        )
    return {
        "retrieval_case_id": case["retrieval_case_id"],
        "query_type": case["query_type"],
        "required_solution_ids": list(case["required_solution_ids"]),
        "forbidden_solution_ids": list(case["forbidden_solution_ids"]),
        "operational_filters": case["filters"],
        "top_5_candidate_ids": [
            {
                "rank": candidate["rank"],
                "document_id": candidate["document_id"],
                "chunk_id": candidate["chunk_id"],
            }
            for candidate in result["retrieved_candidates"]
        ],
        "violation_candidate_count": len(violation_candidates),
        "first_violation_rank": violation_candidates[0]["rank"] if violation_candidates else None,
        "violation_candidates": violation_candidates,
        "case_level_cause_tags": sorted(case_level_tags),
    }


def build_benchmark_feasibility(
    *,
    cases: list[dict[str, Any]],
    documents_by_id: dict[str, dict[str, Any]],
    chunks_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    feasible_case_ids: list[str] = []
    infeasible_case_ids: list[str] = []
    per_case: dict[str, Any] = {}
    for case in cases:
        required_solution_ids = set(case["required_solution_ids"])
        forbidden_solution_ids = set(case["forbidden_solution_ids"])
        safe_expected_items: list[dict[str, str]] = []
        conflicting_expected_items: list[dict[str, Any]] = []
        for document_id in case["expected_relevant_document_ids"]:
            document = documents_by_id[document_id]
            solution_ids = set(document["solution_ids"])
            conflict = (required_solution_ids and not solution_ids.issubset(required_solution_ids)) or bool(
                solution_ids & forbidden_solution_ids
            )
            target = conflicting_expected_items if conflict else safe_expected_items
            target.append({"kind": "document", "id": document_id, "solution_ids": list(document["solution_ids"])})
        for chunk_id in case["expected_relevant_chunk_ids"]:
            chunk = chunks_by_id[chunk_id]
            solution_ids = set(chunk["solution_ids"])
            conflict = (required_solution_ids and not solution_ids.issubset(required_solution_ids)) or bool(
                solution_ids & forbidden_solution_ids
            )
            target = conflicting_expected_items if conflict else safe_expected_items
            target.append({"kind": "chunk", "id": chunk_id, "solution_ids": list(chunk["solution_ids"])})

        reasons: list[str] = []
        if len(safe_expected_items) < case["minimum_relevant_hits"]:
            reasons.append("minimum_relevant_hits_exceeds_safe_expected_items")
        if conflicting_expected_items:
            reasons.append("expected_relevant_items_conflict_with_boundary")
        is_feasible = len(safe_expected_items) >= case["minimum_relevant_hits"]
        if is_feasible:
            feasible_case_ids.append(case["retrieval_case_id"])
        else:
            infeasible_case_ids.append(case["retrieval_case_id"])
        per_case[case["retrieval_case_id"]] = {
            "safe_expected_item_count": len(safe_expected_items),
            "conflicting_expected_item_count": len(conflicting_expected_items),
            "minimum_relevant_hits": case["minimum_relevant_hits"],
            "benchmark_case_infeasible": not is_feasible,
            "infeasibility_reasons": reasons,
        }
    return {
        "feasible_case_ids": feasible_case_ids,
        "infeasible_case_ids": infeasible_case_ids,
        "infeasibility_reasons_by_case": {
            case_id: case_data["infeasibility_reasons"]
            for case_id, case_data in per_case.items()
            if case_data["benchmark_case_infeasible"]
        },
        "per_case": per_case,
    }


def build_knowledge_metadata_findings(
    *,
    documents: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    by_cardinality = Counter(len(document["solution_ids"]) for document in documents)
    multi_solution_documents = [
        {
            "document_id": document["document_id"],
            "document_type": document["document_type"],
            "solution_id_count": len(document["solution_ids"]),
            "solution_ids": list(document["solution_ids"]),
        }
        for document in documents
        if len(document["solution_ids"]) > 1
    ]
    wide_types = Counter(
        document["document_type"] for document in documents if len(document["solution_ids"]) > 1
    )
    chunk_matches_document_scope = all(
        chunk["solution_ids"] == next(document["solution_ids"] for document in documents if document["document_id"] == chunk["document_id"])
        for chunk in chunks
    )
    return {
        "document_solution_cardinality_distribution": {
            str(key): value for key, value in sorted(by_cardinality.items())
        },
        "multi_solution_document_count": len(multi_solution_documents),
        "multi_solution_documents": multi_solution_documents,
        "multi_solution_document_type_counts": dict(sorted(wide_types.items())),
        "chunk_inherits_document_solution_scope": chunk_matches_document_scope,
        "v2_metadata_candidates": [
            "primary_solution_id",
            "applicable_solution_ids",
            "excluded_solution_ids",
            "chunk_level_solution_scope",
            "scope_type",
        ],
    }


def build_evaluation_contract_findings(
    *,
    feasibility: dict[str, Any],
    per_case_boundary: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    expected_conflict_cases = sorted(
        {
            case_id
            for case_id, method_payloads in per_case_boundary.items()
            for payload in method_payloads.values()
            if "expected_document_contains_forbidden_solution" in payload["case_level_cause_tags"]
        }
    )
    return {
        "benchmark_case_infeasible_count": len(feasibility["infeasible_case_ids"]),
        "benchmark_case_infeasible_ids": list(feasibility["infeasible_case_ids"]),
        "expected_relevant_boundary_conflict_case_ids": expected_conflict_cases,
        "notes": [
            "Boundary evaluation is candidate-level, while forbidden and required solution semantics are encoded at case level.",
            "Expected relevant items can themselves carry forbidden or out-of-required solution metadata.",
        ],
    }


def build_retriever_quality_findings(
    *,
    lexical_results: list[dict[str, Any]],
    vector_results: list[dict[str, Any]],
    hybrid_results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "lexical_cases_below_recall_at_5": [
            result["retrieval_case_id"]
            for result in lexical_results
            if result["case_metrics"]["recall_at_5"] < 1.0
        ],
        "vector_cases_below_recall_at_5": [
            result["retrieval_case_id"] for result in vector_results if result["recall_at_5"] < 1.0
        ],
        "hybrid_cases_below_recall_at_5": [
            result["retrieval_case_id"] for result in hybrid_results if result["recall_at_5"] < 1.0
        ],
        "vector_forbidden_hit_case_ids": [
            result["retrieval_case_id"] for result in vector_results if result["forbidden_hit"]
        ],
        "hybrid_forbidden_hit_case_ids": [
            result["retrieval_case_id"] for result in hybrid_results if result["forbidden_hit"]
        ],
        "mrr_vs_recall_explanation": {
            "lexical_cases_with_rr1": sum(
                1 for result in lexical_results if result["case_metrics"]["reciprocal_rank"] == 1.0
            ),
            "vector_cases_with_rr1": sum(1 for result in vector_results if result["reciprocal_rank"] == 1.0),
            "hybrid_cases_with_rr1": sum(1 for result in hybrid_results if result["reciprocal_rank"] == 1.0),
            "explanation": "MRR measures the rank of the first relevant result, while recall measures how much of the full relevant set is covered within top-k.",
        },
    }


def build_blocking_gate_findings(
    *,
    original_method_summaries: dict[str, Any],
    counterfactual: dict[str, Any],
    feasibility: dict[str, Any],
) -> dict[str, Any]:
    return {
        "selected_method": original_method_summaries["comparison"]["selected_method"],
        "selection_status": original_method_summaries["comparison"]["selection_status"],
        "selection_reasons": list(original_method_summaries["comparison"]["selection_reasons"]),
        "counterfactual_changes_eligibility": {
            "vector_case_level_all_still_fail": counterfactual["vector"]["all_cases_still_fail_case_level"],
            "hybrid_case_level_all_still_fail": counterfactual["hybrid"]["all_cases_still_fail_case_level"],
            "vector_method_still_ineligible": counterfactual["vector"]["method_still_ineligible_due_to_frozen_summary_metrics"],
            "hybrid_method_still_ineligible": counterfactual["hybrid"]["method_still_ineligible_due_to_frozen_summary_metrics"],
        },
        "benchmark_infeasible_case_ids": list(feasibility["infeasible_case_ids"]),
        "assessment": [
            "Removing empty_query_tokens from vector_v1 or hybrid_v1 does not create an eligible retrieval method.",
            "The frozen blocking gate remains internally consistent with the frozen v1 result files.",
        ],
    }


def build_per_case_analysis(
    *,
    cases: list[dict[str, Any]],
    documents_by_id: dict[str, dict[str, Any]],
    chunks_by_id: dict[str, dict[str, Any]],
    lexical_results: list[dict[str, Any]],
    vector_results: list[dict[str, Any]],
    hybrid_results: list[dict[str, Any]],
    per_case_boundary: dict[str, dict[str, Any]],
    feasibility: dict[str, Any],
) -> list[dict[str, Any]]:
    lexical_by_id = {result["retrieval_case_id"]: result for result in lexical_results}
    vector_by_id = {result["retrieval_case_id"]: result for result in vector_results}
    hybrid_by_id = {result["retrieval_case_id"]: result for result in hybrid_results}
    rows: list[dict[str, Any]] = []
    for case in cases:
        case_id = case["retrieval_case_id"]
        rows.append(
            {
                "retrieval_case_id": case_id,
                "query_type": case["query_type"],
                "source_case_id": case["source_case_id"],
                "required_solution_ids": list(case["required_solution_ids"]),
                "forbidden_solution_ids": list(case["forbidden_solution_ids"]),
                "forbidden_document_ids": list(case["forbidden_document_ids"]),
                "minimum_relevant_hits": case["minimum_relevant_hits"],
                "expected_relevant_document_ids": list(case["expected_relevant_document_ids"]),
                "expected_relevant_chunk_ids": list(case["expected_relevant_chunk_ids"]),
                "expected_relevant_item_count": len(case["expected_relevant_document_ids"]) + len(case["expected_relevant_chunk_ids"]),
                "benchmark_case_infeasible": feasibility["per_case"][case_id]["benchmark_case_infeasible"],
                "infeasibility_reasons": list(feasibility["per_case"][case_id]["infeasibility_reasons"]),
                "method_metrics": {
                    "lexical": {
                        "recall_at_1": lexical_by_id[case_id]["case_metrics"]["recall_at_1"],
                        "recall_at_3": lexical_by_id[case_id]["case_metrics"]["recall_at_3"],
                        "recall_at_5": lexical_by_id[case_id]["case_metrics"]["recall_at_5"],
                        "reciprocal_rank": lexical_by_id[case_id]["case_metrics"]["reciprocal_rank"],
                        "failure_reasons": list(lexical_by_id[case_id]["failure_reasons"]),
                    },
                    "vector": {
                        "recall_at_1": vector_by_id[case_id]["recall_at_1"],
                        "recall_at_3": vector_by_id[case_id]["recall_at_3"],
                        "recall_at_5": vector_by_id[case_id]["recall_at_5"],
                        "reciprocal_rank": vector_by_id[case_id]["reciprocal_rank"],
                        "failure_reasons": list(vector_by_id[case_id]["failure_reasons"]),
                    },
                    "hybrid": {
                        "recall_at_1": hybrid_by_id[case_id]["recall_at_1"],
                        "recall_at_3": hybrid_by_id[case_id]["recall_at_3"],
                        "recall_at_5": hybrid_by_id[case_id]["recall_at_5"],
                        "reciprocal_rank": hybrid_by_id[case_id]["reciprocal_rank"],
                        "failure_reasons": list(hybrid_by_id[case_id]["failure_reasons"]),
                    },
                },
                "boundary_analysis": per_case_boundary[case_id],
            }
        )
    return rows


def build_v2_recommendations(
    *,
    feasibility: dict[str, Any],
    metadata_findings: dict[str, Any],
) -> dict[str, Any]:
    return {
        "A_must_fix_technical_bug": [
            "Do not derive vector_v1 or hybrid_v1 empty-query failures from the lexical-only query_tokens debug field.",
            "Rename or split failure taxonomy so empty_query_tokens means an actually empty tokenized query, not a missing debug field.",
        ],
        "B_versioned_data_contract_improvements": [
            "Create a v2 knowledge corpus with chunk-level solution scope instead of inheriting all solution_ids from each document.",
            "Add primary_solution_id, applicable_solution_ids, excluded_solution_ids, and scope_type to the v2 knowledge metadata contract.",
        ],
        "C_versioned_evaluation_improvements": [
            "Define v2 boundary evaluation separately for expected relevant content versus candidate-level scope violations.",
            "Add a v2 case audit that rejects infeasible cases before formal benchmarking.",
            "Do not mutate v1 retrieval cases or v1 metrics; version the evaluation dataset forward.",
        ],
        "D_retriever_improvements": [
            "Re-evaluate vector and hybrid retrieval only after v2 metadata and v2 evaluation contracts are frozen.",
            "Investigate whether forbidden hits remain after boundary-safe chunk scope is introduced in v2.",
        ],
        "E_blocking_gate_notes": [
            "Keep the frozen v1 blocking gate unchanged for auditability.",
            "Only allow Architecture C retrieval integration after a v2 method reaches eligible_for_rag=true under the versioned v2 benchmark.",
        ],
        "infeasible_case_ids": list(feasibility["infeasible_case_ids"]),
        "knowledge_metadata_pressure_points": [
            finding["document_id"]
            for finding in metadata_findings["multi_solution_documents"]
            if finding["solution_id_count"] >= 3
        ],
    }


def _extract_method_summary(summary: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "recall_at_1": summary["recall_at_1"],
        "recall_at_3": summary["recall_at_3"],
        "recall_at_5": summary["recall_at_5"],
        "precision_at_3": summary["precision_at_3"],
        "precision_at_5": summary["precision_at_5"],
        "mean_reciprocal_rank": summary["mean_reciprocal_rank"],
        "forbidden_hit_rate": summary["forbidden_hit_rate"],
        "solution_boundary_violation_rate": summary["solution_boundary_violation_rate"],
        "average_latency_ms": summary["average_latency_ms"],
        "eligible_for_rag": summary["eligible_for_rag"],
        "failed_case_ids": list(summary["failed_case_ids"]),
        "disqualification_reasons": list(summary["disqualification_reasons"]),
    }
    if "embedding_dimension" in summary:
        payload["embedding_dimension"] = summary["embedding_dimension"]
        payload["resolved_model_revision"] = summary["resolved_model_revision"]
    return payload


def _counterfactual_method_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    filtered = {}
    for result in results:
        remaining = [reason for reason in result["failure_reasons"] if reason not in COUNTERFACTUAL_EXCLUDED_REASONS]
        filtered[result["retrieval_case_id"]] = remaining
    failed_case_ids = [case_id for case_id, reasons in filtered.items() if reasons]
    summary_reasons: list[str] = []
    for reasons in filtered.values():
        for reason in reasons:
            if reason not in summary_reasons:
                summary_reasons.append(reason)
    return {
        "failed_case_ids": failed_case_ids,
        "disqualification_reasons": summary_reasons,
        "all_cases_still_fail_case_level": len(failed_case_ids) == len(results),
        "case_level_pass_count_after_exclusion": len(results) - len(failed_case_ids),
        "method_still_ineligible_due_to_frozen_summary_metrics": True,
        "per_case_remaining_failure_reasons": filtered,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
