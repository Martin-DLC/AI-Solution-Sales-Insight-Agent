from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.retrieval.dataset import load_retrieval_evaluation_cases
from evaluation.retrieval.models import summarize_case_mix
from evaluation.retrieval.runner import build_summary_payload, run_retrieval_evaluation
from evaluation.retrieval.storage import (
    diff_json_objects,
    load_json_record,
    load_jsonl_records,
    write_json_atomic,
    write_jsonl_atomic,
)
from knowledge_base.dataset import (
    load_demo_solution_scope,
    load_knowledge_chunks,
    load_knowledge_documents,
    load_knowledge_manifest,
)
from knowledge_base.retrieval import LexicalBaselineConfig, WeightedBM25Retriever


CONFIG_PATH = Path("data/evaluation/retrieval/lexical_baseline_config.v1.json")
RESULTS_PATH = Path("data/evaluation/retrieval/lexical_baseline_results.v1.jsonl")
SUMMARY_PATH = Path("data/evaluation/retrieval/lexical_baseline_summary.v1.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan, verify, or write the lexical retrieval baseline artifacts.")
    parser.add_argument("--check", action="store_true", help="Re-run the lexical baseline and compare with tracked results.")
    parser.add_argument("--write", action="store_true", help="Re-run the lexical baseline and write tracked results.")
    args = parser.parse_args()

    if args.check and args.write:
        print("Choose either --check or --write, not both.", file=sys.stderr)
        return 2

    config = LexicalBaselineConfig.model_validate(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")
    chunks = load_knowledge_chunks("data/knowledge_base/chunks.v1.jsonl")
    manifest = load_knowledge_manifest("data/knowledge_base/manifest.v1.json")
    demo_scope = load_demo_solution_scope("data/knowledge_base/demo_solution_scope.v1.json")
    cases = load_retrieval_evaluation_cases("data/evaluation/retrieval/retrieval_cases.v1.jsonl")

    plan_payload = {
        "knowledge_document_count": len(documents),
        "chunk_count": len(chunks),
        "demo_solution_count": len(demo_scope.selected_solution_ids),
        "retrieval_case_count": len(cases),
        "query_type_counts": summarize_case_mix(cases),
        "baseline_config": config.model_dump(mode="json"),
        "planned_top_k": config.top_k,
    }
    if not args.check and not args.write:
        print(json.dumps(plan_payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    retriever = WeightedBM25Retriever(config=config)
    retriever.build_index(documents=documents, chunks=chunks)
    report = run_retrieval_evaluation(
        cases=cases,
        retriever=retriever,
        method_id="lexical_v1",
        top_k=config.top_k,
    )
    result_payloads = [case_result.model_dump(mode="json") for case_result in report.case_results]
    summary_payload = build_summary_payload(
        cases=cases,
        config=config,
        manifest=manifest,
        demo_scope=demo_scope,
        report=report,
    )

    if args.check:
        tracked_results = load_jsonl_records(RESULTS_PATH)
        tracked_summary = load_json_record(SUMMARY_PATH)
        differences = _compare_results(
            tracked_results=tracked_results,
            current_results=result_payloads,
            tracked_summary=tracked_summary,
            current_summary=summary_payload,
        )
        if differences:
            for difference in differences:
                print(difference, file=sys.stderr)
            return 1
        print("Lexical retrieval baseline artifacts are up to date.")
        return 0

    write_jsonl_atomic(RESULTS_PATH, result_payloads)
    write_json_atomic(SUMMARY_PATH, summary_payload)
    print(
        json.dumps(
            {
                "baseline_version": config.baseline_version,
                "case_count": len(result_payloads),
                "eligible_for_rag": summary_payload["eligible_for_rag"],
                "failed_case_ids": summary_payload["failed_case_ids"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _compare_results(
    *,
    tracked_results: list[dict[str, object]],
    current_results: list[dict[str, object]],
    tracked_summary: dict[str, object],
    current_summary: dict[str, object],
) -> list[str]:
    differences: list[str] = []
    if len(tracked_results) != len(current_results):
        differences.append(f"results:length")
        return differences

    for tracked, current in zip(tracked_results, current_results):
        case_id = str(current.get("retrieval_case_id", tracked.get("retrieval_case_id", "unknown_case")))
        for path in diff_json_objects(tracked, current):
            if _is_ignored_check_path(path):
                continue
            differences.append(f"{case_id}:{path}")

    for path in diff_json_objects(tracked_summary, current_summary):
        if _is_ignored_check_path(path):
            continue
        differences.append(f"summary:{path}")
    return differences


def _is_ignored_check_path(path: str) -> bool:
    return path.endswith("case_metrics.latency_ms") or path.endswith("average_latency_ms")


if __name__ == "__main__":
    raise SystemExit(main())
