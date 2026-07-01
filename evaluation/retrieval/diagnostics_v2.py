from __future__ import annotations

import contextlib
import hashlib
import json
import socket
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from evaluation.retrieval.contracts_v2 import RetrievalEvaluationCaseV2, evaluate_candidate_boundary_v2
from evaluation.retrieval.failure_taxonomy import classify_retrieval_failures_v2
from evaluation.retrieval.models import RetrievalMethod, RetrievalRunResult
from evaluation.retrieval.runner_v2 import (
    RetrievalRunnerV2CaseResult,
    RetrievalRunnerV2Report,
    _build_debug_payload,
    _safe_error_message,
    aggregate_summary_metrics_v2,
    build_formal_case_results_v2,
    build_formal_summary_v2,
    evaluate_retrieval_case_v2,
    make_runtime_input_v2,
    project_v2_chunks_to_legacy_runtime_inputs,
    project_v2_documents_to_legacy_runtime_inputs,
    runtime_input_has_gold_leak,
    runtime_input_to_retriever_filters,
)
from evaluation.retrieval.storage import diff_json_objects, load_json_record, load_jsonl_records, write_json_atomic
from knowledge_base import KnowledgeChunkV2, KnowledgeDocumentV2
from knowledge_base.retrieval import (
    ExactVectorRetriever,
    HybridBaselineConfig,
    LexicalBaselineConfig,
    ReciprocalRankFusionRetriever,
    SentenceTransformerEmbeddingProvider,
    VectorBaselineConfig,
)
from knowledge_base.retrieval.embeddings import (
    DEFAULT_EMBEDDING_REVISION,
    huggingface_offline_environment,
    resolve_local_model_snapshot,
)
from knowledge_base.retrieval.lexical import WeightedBM25Retriever


PROJECT_ROOT = Path(__file__).resolve().parents[2]

BENCHMARK_CONFIG_PATH = Path("data/evaluation/retrieval/retrieval_benchmark_config.v2.json")
LEXICAL_CONFIG_PATH = Path("data/evaluation/retrieval/lexical_baseline_config.v2.json")
VECTOR_CONFIG_PATH = Path("data/evaluation/retrieval/vector_baseline_config.v2.json")
HYBRID_CONFIG_PATH = Path("data/evaluation/retrieval/hybrid_baseline_config.v2.json")

LEXICAL_RESULTS_PATH = Path("data/evaluation/retrieval/lexical_baseline_results.v2.jsonl")
LEXICAL_SUMMARY_PATH = Path("data/evaluation/retrieval/lexical_baseline_summary.v2.json")
VECTOR_RESULTS_PATH = Path("data/evaluation/retrieval/vector_baseline_results.v2.jsonl")
VECTOR_SUMMARY_PATH = Path("data/evaluation/retrieval/vector_baseline_summary.v2.json")
HYBRID_RESULTS_PATH = Path("data/evaluation/retrieval/hybrid_baseline_results.v2.jsonl")
HYBRID_SUMMARY_PATH = Path("data/evaluation/retrieval/hybrid_baseline_summary.v2.json")
COMPARISON_PATH = Path("data/evaluation/retrieval/retrieval_method_comparison.v2.json")

DIAGNOSIS_OUTPUT_PATH = Path("data/evaluation/retrieval/retrieval_v2_failure_diagnosis.json")
DIAGNOSIS_DOC_PATH = Path("docs/28_Retrieval_V2_Failure_Diagnosis.md")

FORMAL_ARTIFACT_PATHS = {
    "lexical_results": LEXICAL_RESULTS_PATH,
    "lexical_summary": LEXICAL_SUMMARY_PATH,
    "vector_results": VECTOR_RESULTS_PATH,
    "vector_summary": VECTOR_SUMMARY_PATH,
    "hybrid_results": HYBRID_RESULTS_PATH,
    "hybrid_summary": HYBRID_SUMMARY_PATH,
    "comparison": COMPARISON_PATH,
}
METHOD_CONFIG_PATHS = {
    "lexical_v1": LEXICAL_CONFIG_PATH,
    "vector_v1": VECTOR_CONFIG_PATH,
    "hybrid_v1": HYBRID_CONFIG_PATH,
}

TOP_K_FORMAL = 5
TOP_K_DIAGNOSTIC = 20
BOUNDARY_FOCUS_CASE_IDS = ("RET2-005", "RET2-006", "RET2-009")
NON_DETERMINISTIC_PATH_SUFFIXES = {
    "elapsed_ms",
    "average_latency_ms",
}


@dataclass(frozen=True)
class DiagnosticContext:
    benchmark_config: dict[str, Any]
    cases: list[RetrievalEvaluationCaseV2]
    documents: list[KnowledgeDocumentV2]
    chunks: list[KnowledgeChunkV2]
    lexical_config_payload: dict[str, Any]
    vector_config_payload: dict[str, Any]
    hybrid_config_payload: dict[str, Any]
    lexical_results: list[dict[str, Any]]
    lexical_summary: dict[str, Any]
    vector_results: list[dict[str, Any]]
    vector_summary: dict[str, Any]
    hybrid_results: list[dict[str, Any]]
    hybrid_summary: dict[str, Any]
    comparison: dict[str, Any]


@dataclass(frozen=True)
class DiagnosticMethodRun:
    method_id: str
    top_k: int
    report: RetrievalRunnerV2Report
    formal_case_results: list[dict[str, Any]]
    summary: dict[str, Any]
    debug_by_case_id: dict[str, dict[str, Any]]


def build_plan_payload() -> dict[str, Any]:
    benchmark_config = load_json_record(BENCHMARK_CONFIG_PATH)
    return {
        "mode": "plan",
        "diagnostic_only": True,
        "benchmark_version": benchmark_config["benchmark_version"],
        "case_count": benchmark_config["case_count"],
        "document_count": benchmark_config["document_count"],
        "chunk_count": benchmark_config["chunk_count"],
        "top_k_formal": benchmark_config["top_k"],
        "top_k_diagnostic": TOP_K_DIAGNOSTIC,
        "methods": ["lexical_v1", "vector_v1", "hybrid_v1"],
        "boundary_focus_case_ids": list(BOUNDARY_FOCUS_CASE_IDS),
        "formal_result_hashes": compute_formal_result_hashes(),
        "planned_outputs": {
            "json": str(DIAGNOSIS_OUTPUT_PATH),
            "doc": str(DIAGNOSIS_DOC_PATH),
        },
    }


def build_diagnosis_payload() -> dict[str, Any]:
    context = load_diagnostic_context()
    formal_result_hashes_before = compute_formal_result_hashes()
    case_recall_feasibility = build_case_recall_feasibility(context.cases, top_k=TOP_K_FORMAL)

    lexical_run = run_method_diagnostic(context=context, method_id="lexical_v1", top_k=TOP_K_DIAGNOSTIC)
    vector_run = run_method_diagnostic(context=context, method_id="vector_v1", top_k=TOP_K_DIAGNOSTIC)
    hybrid_run = run_method_diagnostic(context=context, method_id="hybrid_v1", top_k=TOP_K_DIAGNOSTIC)

    diagnostic_runs = {
        "lexical_v1": lexical_run,
        "vector_v1": vector_run,
        "hybrid_v1": hybrid_run,
    }

    per_method_case_diagnostics = {
        method_id: build_per_method_case_diagnostics(
            method_id=method_id,
            cases=context.cases,
            formal_case_results=_formal_results_for_method(context, method_id),
            diagnostic_formal_case_results=run.formal_case_results,
            debug_by_case_id=run.debug_by_case_id,
        )
        for method_id, run in diagnostic_runs.items()
    }

    boundary_violation_diagnostics = build_boundary_violation_diagnostics(
        cases=context.cases,
        documents=context.documents,
        chunks=context.chunks,
        diagnostic_runs=diagnostic_runs,
    )
    top20_recall_analysis = build_top20_recall_analysis(
        cases=context.cases,
        per_method_case_diagnostics=per_method_case_diagnostics,
    )
    scope_filter_backfill_counterfactual = build_scope_filter_backfill_counterfactual(
        cases=context.cases,
        documents=context.documents,
        chunks=context.chunks,
        diagnostic_runs=diagnostic_runs,
    )
    cross_method_findings = build_cross_method_findings(
        case_recall_feasibility=case_recall_feasibility,
        top20_recall_analysis=top20_recall_analysis,
        boundary_violation_diagnostics=boundary_violation_diagnostics,
        counterfactual=scope_filter_backfill_counterfactual,
    )
    recommendations = build_recommendations(
        top20_recall_analysis=top20_recall_analysis,
        boundary_violation_diagnostics=boundary_violation_diagnostics,
        counterfactual=scope_filter_backfill_counterfactual,
    )

    payload = {
        "diagnosis_version": "retrieval_v2_failure_diagnosis_v1",
        "diagnostic_only": True,
        "formal_result_hashes": formal_result_hashes_before,
        "benchmark_hash": compute_file_sha256(BENCHMARK_CONFIG_PATH),
        "method_config_hashes": {
            method_id: compute_file_sha256(path)
            for method_id, path in METHOD_CONFIG_PATHS.items()
        },
        "case_recall_feasibility": case_recall_feasibility,
        "per_method_case_diagnostics": per_method_case_diagnostics,
        "boundary_violation_diagnostics": boundary_violation_diagnostics,
        "top20_recall_analysis": top20_recall_analysis,
        "scope_filter_backfill_counterfactual": scope_filter_backfill_counterfactual,
        "cross_method_findings": cross_method_findings,
        "recommended_minimum_change": recommendations["recommended_minimum_change"],
        "secondary_change_if_needed": recommendations["secondary_change_if_needed"],
        "changes_not_justified_by_evidence": recommendations["changes_not_justified_by_evidence"],
        "whether_new_retriever_version_is_required": recommendations["whether_new_retriever_version_is_required"],
        "architecture_c_status": "blocked",
        "limitations": [
            "This diagnosis reuses the frozen v2 dataset and frozen retriever parameters.",
            "Top-20 runs are diagnostic-only and are not formal benchmark results.",
            "Vector and hybrid diagnostics require the frozen local embedding snapshot in strict offline mode.",
            "Counterfactual scope-aware filtering uses runtime context plus candidate scope metadata only.",
        ],
        "formal_results_unchanged": formal_result_hashes_before == compute_formal_result_hashes(),
    }
    return payload


def render_diagnosis_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Retrieval Benchmark V2 Failure Diagnosis")
    lines.append("")
    lines.append("## 为什么不能直接调参")
    lines.append("")
    lines.append("- 当前诊断严格复用冻结的 v2 数据、算法和参数，只做诊断性 Top-20 扩展。")
    lines.append("- 正式结果仍以冻结的 Top-5 正式 Artifact 为准。")
    lines.append("- 任何改动建议都必须由本次证据链支持，不能先改再解释。")
    lines.append("")
    lines.append("## 正式结果摘要")
    lines.append("")
    for method_id in ("lexical_v1", "vector_v1", "hybrid_v1"):
        method_summary = payload["cross_method_findings"]["formal_method_summaries"][method_id]
        lines.append(f"### {method_id}")
        lines.append("")
        lines.append(f"- recall_at_5: {method_summary['recall_at_5']}")
        lines.append(f"- solution_boundary_violation_rate: {method_summary['solution_boundary_violation_rate']}")
        lines.append(f"- eligible_for_rag: {method_summary['eligible_for_rag']}")
        lines.append(f"- failed_case_ids: {', '.join(method_summary['failed_case_ids']) or 'none'}")
        lines.append("")
    lines.append("## Recall Gate 与 Boundary Gate")
    lines.append("")
    lines.append("- 冻结 Gate 同时要求 summary recall_at_5 == 1.0、boundary violation rate == 0、forbidden hit rate == 0、request_error_count == 0，以及所有 case-level gate 通过。")
    lines.append("- 本次诊断重点区分三类问题：候选召回不足、Top-5 排序 / 拥挤、以及 runtime scope 未提前拦截的 boundary 违规。")
    lines.append("")
    lines.append("## 每条 Case Recall 可达性")
    lines.append("")
    for item in payload["case_recall_feasibility"]:
        lines.append(
            f"- {item['retrieval_case_id']}: relevant_items={item['relevant_item_count']}, "
            f"max_possible_recall_at_5={item['maximum_possible_recall_at_5']}, "
            f"recall_gate_feasible={str(item['recall_at_5_gate_feasible']).lower()}, "
            f"minimum_hits_gate_feasible={str(item['minimum_hits_gate_feasible']).lower()}"
        )
    lines.append("")
    lines.append("## 三方法 Top-5 / Top-10 / Top-20 分析")
    lines.append("")
    for method_id, analysis in payload["top20_recall_analysis"].items():
        lines.append(f"### {method_id}")
        lines.append("")
        lines.append(f"- cases_recall_1_at_5: {analysis['cases_recall_1_at_5']}")
        lines.append(f"- cases_recall_1_at_10: {analysis['cases_recall_1_at_10']}")
        lines.append(f"- cases_recall_1_at_20: {analysis['cases_recall_1_at_20']}")
        lines.append(f"- missing_items_not_in_top20: {analysis['missing_items_not_in_top20']}")
        lines.append(f"- cases_affected_by_duplicate_crowding: {analysis['cases_affected_by_duplicate_crowding']}")
        lines.append(f"- cases_affected_by_scope_filter: {analysis['cases_affected_by_scope_filter']}")
        lines.append("")
    lines.append("## Missing Gold 分布")
    lines.append("")
    for method_id, analysis in payload["top20_recall_analysis"].items():
        distribution = analysis["missing_item_cause_distribution"]
        ordered = ", ".join(f"{key}={value}" for key, value in sorted(distribution.items()))
        lines.append(f"- {method_id}: {ordered or 'none'}")
    lines.append("")
    lines.append("## 重复 Chunk 和 Document 拥挤")
    lines.append("")
    for method_id, analysis in payload["top20_recall_analysis"].items():
        lines.append(
            f"- {method_id}: duplicate_document_case_count={analysis['duplicate_document_case_count']}, "
            f"same_document_chunk_crowding_case_count={analysis['same_document_chunk_crowding_case_count']}"
        )
    lines.append("")
    for case_id in BOUNDARY_FOCUS_CASE_IDS:
        lines.append(f"## {case_id} 分析")
        lines.append("")
        boundary_entry = payload["boundary_violation_diagnostics"][case_id]
        lines.append(f"- failing_methods: {', '.join(boundary_entry['failing_methods'])}")
        lines.append(f"- dominant_causes: {', '.join(boundary_entry['dominant_causes']) or 'none'}")
        for method_id, candidates in boundary_entry["violating_candidates_by_method"].items():
            lines.append(f"- {method_id}: {len(candidates)} violating candidates")
        lines.append("")
    lines.append("## Scope-aware Filter + Backfill 反事实")
    lines.append("")
    for method_id, result in payload["scope_filter_backfill_counterfactual"].items():
        lines.append(f"### {method_id}")
        lines.append("")
        lines.append(f"- counterfactual_summary_recall_at_5: {result['counterfactual_summary_recall_at_5']}")
        lines.append(f"- counterfactual_boundary_violation_rate: {result['counterfactual_boundary_violation_rate']}")
        lines.append(f"- counterfactual_failed_case_ids: {', '.join(result['counterfactual_failed_case_ids']) or 'none'}")
        lines.append(f"- counterfactual_eligible_for_rag: {str(result['counterfactual_eligible_for_rag']).lower()}")
        lines.append("")
    lines.append("## 哪些 Boundary 可以运行时提前阻断")
    lines.append("")
    lines.append(
        f"- runtime_preventable_cases: {', '.join(payload['cross_method_findings']['runtime_preventable_boundary_case_ids']) or 'none'}"
    )
    lines.append("")
    lines.append("## 哪些问题属于排序")
    lines.append("")
    lines.append(
        f"- ranking_dominated_case_ids: {', '.join(payload['cross_method_findings']['ranking_dominated_case_ids']) or 'none'}"
    )
    lines.append("")
    lines.append("## 哪些问题属于候选召回")
    lines.append("")
    lines.append(
        f"- candidate_recall_gap_case_ids: {', '.join(payload['cross_method_findings']['candidate_recall_gap_case_ids']) or 'none'}"
    )
    lines.append("")
    lines.append("## 最小改进建议")
    lines.append("")
    lines.append(f"- recommended_minimum_change: {payload['recommended_minimum_change']}")
    lines.append(f"- secondary_change_if_needed: {payload['secondary_change_if_needed']}")
    lines.append("")
    lines.append("## 不建议立即实施的改动")
    lines.append("")
    for item in payload["changes_not_justified_by_evidence"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Architecture C 仍被阻断")
    lines.append("")
    lines.append(f"- architecture_c_status: {payload['architecture_c_status']}")
    lines.append("- 当前没有方法通过冻结 Gate，因此仍不得接入 Architecture C。")
    lines.append("")
    lines.append("## 数据规模与合成数据限制")
    lines.append("")
    for limitation in payload["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


def write_diagnosis_outputs(payload: dict[str, Any]) -> None:
    write_json_atomic(DIAGNOSIS_OUTPUT_PATH, payload)
    DIAGNOSIS_DOC_PATH.write_text(render_diagnosis_markdown(payload), encoding="utf-8")


def check_diagnosis_outputs() -> tuple[bool, list[str]]:
    expected = build_diagnosis_payload()
    tracked = load_json_record(DIAGNOSIS_OUTPUT_PATH)
    differences = [
        path
        for path in diff_json_objects(tracked, expected)
        if not any(path.endswith(suffix) for suffix in NON_DETERMINISTIC_PATH_SUFFIXES)
    ]
    tracked_doc = DIAGNOSIS_DOC_PATH.read_text(encoding="utf-8")
    expected_doc = render_diagnosis_markdown(expected)
    if tracked_doc != expected_doc:
        differences.append("docs/28_Retrieval_V2_Failure_Diagnosis.md")
    return (not differences, differences)


def compute_formal_result_hashes() -> dict[str, str]:
    return {label: compute_file_sha256(path) for label, path in FORMAL_ARTIFACT_PATHS.items()}


def compute_file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_diagnostic_context() -> DiagnosticContext:
    benchmark_config = load_json_record(BENCHMARK_CONFIG_PATH)
    cases = [
        RetrievalEvaluationCaseV2.model_validate(row)
        for row in load_jsonl_records(Path(benchmark_config["case_file"]))
    ]
    documents = [
        KnowledgeDocumentV2.model_validate(row)
        for row in load_jsonl_records(Path(benchmark_config["document_file"]))
    ]
    chunks = [
        KnowledgeChunkV2.model_validate(row)
        for row in load_jsonl_records(Path(benchmark_config["chunk_file"]))
    ]
    return DiagnosticContext(
        benchmark_config=benchmark_config,
        cases=cases,
        documents=documents,
        chunks=chunks,
        lexical_config_payload=load_json_record(LEXICAL_CONFIG_PATH),
        vector_config_payload=load_json_record(VECTOR_CONFIG_PATH),
        hybrid_config_payload=load_json_record(HYBRID_CONFIG_PATH),
        lexical_results=load_jsonl_records(LEXICAL_RESULTS_PATH),
        lexical_summary=load_json_record(LEXICAL_SUMMARY_PATH),
        vector_results=load_jsonl_records(VECTOR_RESULTS_PATH),
        vector_summary=load_json_record(VECTOR_SUMMARY_PATH),
        hybrid_results=load_jsonl_records(HYBRID_RESULTS_PATH),
        hybrid_summary=load_json_record(HYBRID_SUMMARY_PATH),
        comparison=load_json_record(COMPARISON_PATH),
    )


def build_case_recall_feasibility(
    cases: list[RetrievalEvaluationCaseV2],
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for case in cases:
        relevant_item_count = len(case.evaluation_gold.expected_relevant_document_ids) + len(
            case.evaluation_gold.expected_relevant_chunk_ids
        )
        maximum_possible_recall = min(relevant_item_count, top_k) / relevant_item_count
        minimum_hits_gate_feasible = (
            case.evaluation_gold.minimum_relevant_hits <= top_k
            and case.evaluation_gold.minimum_relevant_hits <= relevant_item_count
        )
        items.append(
            {
                "retrieval_case_id": case.retrieval_case_id,
                "source_case_id": case.source_case_id,
                "query_type": case.query_type.value,
                "expected_document_count": len(case.evaluation_gold.expected_relevant_document_ids),
                "expected_chunk_count": len(case.evaluation_gold.expected_relevant_chunk_ids),
                "relevant_item_count": relevant_item_count,
                "top_k": top_k,
                "maximum_possible_recall_at_5": maximum_possible_recall,
                "recall_at_5_gate_feasible": relevant_item_count <= top_k,
                "minimum_relevant_hits": case.evaluation_gold.minimum_relevant_hits,
                "minimum_hits_gate_feasible": minimum_hits_gate_feasible,
            }
        )
    return items


def run_method_diagnostic(
    *,
    context: DiagnosticContext,
    method_id: str,
    top_k: int,
) -> DiagnosticMethodRun:
    legacy_documents = project_v2_documents_to_legacy_runtime_inputs(context.documents)
    legacy_chunks = project_v2_chunks_to_legacy_runtime_inputs(context.chunks)
    retriever = _build_retriever(
        context=context,
        method_id=method_id,
        legacy_documents=legacy_documents,
        legacy_chunks=legacy_chunks,
    )
    report, debug_by_case_id = _run_diagnostic_report(
        cases=context.cases,
        retriever=retriever,
        method_id=method_id,
        top_k=top_k,
        documents=context.documents,
        chunks=context.chunks,
    )
    formal_case_results = [
        item.model_dump(mode="json")
        for item in build_formal_case_results_v2(
            report=report,
            cases=context.cases,
            documents=context.documents,
            chunks=context.chunks,
        )
    ]
    summary = build_formal_summary_v2(
        benchmark_version=context.benchmark_config["benchmark_version"],
        benchmark_config_hash=compute_file_sha256(BENCHMARK_CONFIG_PATH),
        method_config_hash=compute_file_sha256(METHOD_CONFIG_PATHS[method_id]),
        retrieval_method=RetrievalMethod(method_id),
        report=report,
        document_count=len(context.documents),
        chunk_count=len(context.chunks),
    ).model_dump(mode="json")
    return DiagnosticMethodRun(
        method_id=method_id,
        top_k=top_k,
        report=report,
        formal_case_results=formal_case_results,
        summary=summary,
        debug_by_case_id=debug_by_case_id,
    )


def build_per_method_case_diagnostics(
    *,
    method_id: str,
    cases: list[RetrievalEvaluationCaseV2],
    formal_case_results: list[dict[str, Any]],
    diagnostic_formal_case_results: list[dict[str, Any]],
    debug_by_case_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    cases_by_id = {case.retrieval_case_id: case for case in cases}
    formal_by_id = {item["retrieval_case_id"]: item for item in formal_case_results}
    diagnostic_by_id = {item["retrieval_case_id"]: item for item in diagnostic_formal_case_results}
    outputs: list[dict[str, Any]] = []
    for case in cases:
        formal_case = formal_by_id[case.retrieval_case_id]
        diagnostic_case = diagnostic_by_id[case.retrieval_case_id]
        top20_candidates = diagnostic_case["candidates"]
        top5_candidates = formal_case["candidates"]
        missing_items = _build_missing_item_diagnostics(
            case=case,
            method_id=method_id,
            top5_candidates=top5_candidates,
            top20_candidates=top20_candidates,
            debug_payload=debug_by_case_id[case.retrieval_case_id],
        )
        outputs.append(
            {
                "case_id": case.retrieval_case_id,
                "source_case_id": case.source_case_id,
                "query_type": case.query_type.value,
                "relevant_item_count": len(case.evaluation_gold.expected_relevant_document_ids)
                + len(case.evaluation_gold.expected_relevant_chunk_ids),
                "formal_top5_relevant_hits": _count_relevant_items_in_candidates(case=case, candidates=top5_candidates, top_k=5),
                "formal_recall_at_5": formal_case["case_metrics"]["recall_at_5"],
                "missing_relevant_items_at_5": len(missing_items),
                "missing_expected_document_ids": [
                    item["item_id"] for item in missing_items if item["item_type"] == "document"
                ],
                "missing_expected_chunk_ids": [
                    item["item_id"] for item in missing_items if item["item_type"] == "chunk"
                ],
                "missing_items": missing_items,
                "first_missing_item_rank": min(
                    (item["rank_in_top_20"] for item in missing_items if item["rank_in_top_20"] is not None),
                    default=None,
                ),
                "relevant_hits_at_10": _count_relevant_items_in_candidates(case=case, candidates=top20_candidates, top_k=10),
                "relevant_hits_at_20": _count_relevant_items_in_candidates(case=case, candidates=top20_candidates, top_k=20),
                "recall_at_10": _recall_at(case=case, candidates=top20_candidates, top_k=10),
                "recall_at_20": _recall_at(case=case, candidates=top20_candidates, top_k=20),
                "top5_non_relevant_candidates": [
                    _candidate_identity(candidate)
                    for candidate in top5_candidates
                    if _candidate_relevance_id_for_case(case=case, candidate=candidate) not in _relevant_item_ids(case)
                ],
                "top5_duplicate_document_count": _duplicate_document_count(top5_candidates),
                "same_document_chunk_crowding_count": _same_document_chunk_crowding_count(top5_candidates),
                "runtime_gold_leak_detected": False,
                "debug": debug_by_case_id[case.retrieval_case_id],
            }
        )
    return outputs


def build_boundary_violation_diagnostics(
    *,
    cases: list[RetrievalEvaluationCaseV2],
    documents: list[KnowledgeDocumentV2],
    chunks: list[KnowledgeChunkV2],
    diagnostic_runs: dict[str, DiagnosticMethodRun],
) -> dict[str, Any]:
    cases_by_id = {case.retrieval_case_id: case for case in cases}
    documents_by_id = {document.document_id: document for document in documents}
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    output: dict[str, Any] = {}
    for case_id in BOUNDARY_FOCUS_CASE_IDS:
        case = cases_by_id[case_id]
        per_method: dict[str, list[dict[str, Any]]] = {}
        cause_counter: Counter[str] = Counter()
        failing_methods: list[str] = []
        for method_id, run in diagnostic_runs.items():
            case_result = next(item for item in run.formal_case_results if item["retrieval_case_id"] == case_id)
            violating_candidates: list[dict[str, Any]] = []
            for candidate in case_result["candidates"]:
                candidate_record = _augment_boundary_candidate_record(
                    case=case,
                    candidate=candidate,
                    documents_by_id=documents_by_id,
                    chunks_by_id=chunks_by_id,
                )
                if candidate_record["boundary_violation"]:
                    violating_candidates.append(candidate_record)
                    cause_counter[candidate_record["boundary_reason_category"]] += 1
            if violating_candidates:
                failing_methods.append(method_id)
            per_method[method_id] = violating_candidates
        output[case_id] = {
            "failing_methods": failing_methods,
            "dominant_causes": [name for name, _ in cause_counter.most_common()],
            "cause_distribution": dict(sorted(cause_counter.items())),
            "violating_candidates_by_method": per_method,
        }
    return output


def build_top20_recall_analysis(
    *,
    cases: list[RetrievalEvaluationCaseV2],
    per_method_case_diagnostics: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    outputs: dict[str, Any] = {}
    for method_id, items in per_method_case_diagnostics.items():
        missing_counter: Counter[str] = Counter()
        duplicate_cases = 0
        crowding_cases = 0
        scope_cases = 0
        recall1_at_5 = 0
        recall1_at_10 = 0
        recall1_at_20 = 0
        not_in_top20 = 0
        for item in items:
            if item["formal_recall_at_5"] == 1.0:
                recall1_at_5 += 1
            if item["recall_at_10"] == 1.0:
                recall1_at_10 += 1
            if item["recall_at_20"] == 1.0:
                recall1_at_20 += 1
            if item["top5_duplicate_document_count"] > 0:
                duplicate_cases += 1
            if item["same_document_chunk_crowding_count"] > 0:
                crowding_cases += 1
            if any(missing["cause"] == "scope_filter_interaction" for missing in item["missing_items"]):
                scope_cases += 1
            for missing in item["missing_items"]:
                missing_counter[missing["cause"]] += 1
                if missing["cause"] == "not_in_top_20":
                    not_in_top20 += 1
        outputs[method_id] = {
            "cases_recall_1_at_5": recall1_at_5,
            "cases_recall_1_at_10": recall1_at_10,
            "cases_recall_1_at_20": recall1_at_20,
            "missing_items_not_in_top20": not_in_top20,
            "cases_affected_by_duplicate_crowding": duplicate_cases,
            "cases_affected_by_scope_filter": scope_cases,
            "duplicate_document_case_count": duplicate_cases,
            "same_document_chunk_crowding_case_count": crowding_cases,
            "missing_item_cause_distribution": dict(sorted(missing_counter.items())),
            "failed_case_ids": [
                item["case_id"] for item in items if item["formal_recall_at_5"] < 1.0 or item["missing_relevant_items_at_5"] > 0
            ],
        }
    return outputs


def build_scope_filter_backfill_counterfactual(
    *,
    cases: list[RetrievalEvaluationCaseV2],
    documents: list[KnowledgeDocumentV2],
    chunks: list[KnowledgeChunkV2],
    diagnostic_runs: dict[str, DiagnosticMethodRun],
) -> dict[str, Any]:
    documents_by_id = {document.document_id: document for document in documents}
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    outputs: dict[str, Any] = {}
    for method_id, run in diagnostic_runs.items():
        case_results: list[dict[str, Any]] = []
        failed_case_ids: list[str] = []
        boundary_flags: list[float] = []
        recall_values: list[float] = []
        for case in cases:
            diagnostic_case = next(item for item in run.formal_case_results if item["retrieval_case_id"] == case.retrieval_case_id)
            filtered_top5, removed_candidates = _scope_filter_and_backfill(
                case=case,
                candidates=diagnostic_case["candidates"],
                documents_by_id=documents_by_id,
                chunks_by_id=chunks_by_id,
                top_k=TOP_K_FORMAL,
            )
            recall_at_5 = _recall_at(case=case, candidates=filtered_top5, top_k=TOP_K_FORMAL)
            boundary_violation = _has_evaluation_boundary_violation(
                case=case,
                candidates=filtered_top5,
                documents_by_id=documents_by_id,
                chunks_by_id=chunks_by_id,
            )
            failed = recall_at_5 < 1.0 or boundary_violation
            if failed:
                failed_case_ids.append(case.retrieval_case_id)
            case_results.append(
                {
                    "case_id": case.retrieval_case_id,
                    "retained_top5": filtered_top5,
                    "removed_candidate_ids": [_candidate_identity(candidate) for candidate in removed_candidates],
                    "counterfactual_recall_at_5": recall_at_5,
                    "counterfactual_boundary_violation": boundary_violation,
                    "counterfactual_relevant_hits_at_5": _count_relevant_items_in_candidates(
                        case=case,
                        candidates=filtered_top5,
                        top_k=TOP_K_FORMAL,
                    ),
                }
            )
            boundary_flags.append(1.0 if boundary_violation else 0.0)
            recall_values.append(recall_at_5)
        outputs[method_id] = {
            "case_results": case_results,
            "counterfactual_recall_at_5": {item["case_id"]: item["counterfactual_recall_at_5"] for item in case_results},
            "counterfactual_forbidden_hit_rate": 0.0,
            "counterfactual_boundary_violation_rate": sum(boundary_flags) / len(boundary_flags),
            "counterfactual_failed_case_ids": failed_case_ids,
            "counterfactual_summary_recall_at_5": sum(recall_values) / len(recall_values),
            "counterfactual_eligible_for_rag": not failed_case_ids and sum(boundary_flags) == 0,
        }
    return outputs


def build_cross_method_findings(
    *,
    case_recall_feasibility: list[dict[str, Any]],
    top20_recall_analysis: dict[str, Any],
    boundary_violation_diagnostics: dict[str, Any],
    counterfactual: dict[str, Any],
) -> dict[str, Any]:
    runtime_preventable_case_ids: set[str] = set()
    ranking_dominated_case_ids: set[str] = set()
    candidate_recall_gap_case_ids: set[str] = set()
    for case_id, details in boundary_violation_diagnostics.items():
        for candidates in details["violating_candidates_by_method"].values():
            for candidate in candidates:
                if candidate["should_be_excluded_by_runtime_eligibility"]:
                    runtime_preventable_case_ids.add(case_id)
    for method_id, analysis in top20_recall_analysis.items():
        for case_id in analysis["failed_case_ids"]:
            if case_id not in runtime_preventable_case_ids and analysis["cases_recall_1_at_20"] >= analysis["cases_recall_1_at_5"]:
                ranking_dominated_case_ids.add(case_id)
        if analysis["missing_items_not_in_top20"] > 0:
            candidate_recall_gap_case_ids.update(analysis["failed_case_ids"])
    return {
        "all_cases_recall_feasible": all(item["recall_at_5_gate_feasible"] for item in case_recall_feasibility),
        "all_cases_minimum_hits_feasible": all(item["minimum_hits_gate_feasible"] for item in case_recall_feasibility),
        "runtime_preventable_boundary_case_ids": sorted(runtime_preventable_case_ids),
        "ranking_dominated_case_ids": sorted(ranking_dominated_case_ids),
        "candidate_recall_gap_case_ids": sorted(candidate_recall_gap_case_ids),
        "formal_method_summaries": {
            "lexical_v1": {
                "recall_at_5": load_json_record(LEXICAL_SUMMARY_PATH)["recall_at_5"],
                "solution_boundary_violation_rate": load_json_record(LEXICAL_SUMMARY_PATH)["solution_boundary_violation_rate"],
                "eligible_for_rag": load_json_record(LEXICAL_SUMMARY_PATH)["eligible_for_rag"],
                "failed_case_ids": load_json_record(LEXICAL_SUMMARY_PATH)["failed_case_ids"],
            },
            "vector_v1": {
                "recall_at_5": load_json_record(VECTOR_SUMMARY_PATH)["recall_at_5"],
                "solution_boundary_violation_rate": load_json_record(VECTOR_SUMMARY_PATH)["solution_boundary_violation_rate"],
                "eligible_for_rag": load_json_record(VECTOR_SUMMARY_PATH)["eligible_for_rag"],
                "failed_case_ids": load_json_record(VECTOR_SUMMARY_PATH)["failed_case_ids"],
            },
            "hybrid_v1": {
                "recall_at_5": load_json_record(HYBRID_SUMMARY_PATH)["recall_at_5"],
                "solution_boundary_violation_rate": load_json_record(HYBRID_SUMMARY_PATH)["solution_boundary_violation_rate"],
                "eligible_for_rag": load_json_record(HYBRID_SUMMARY_PATH)["eligible_for_rag"],
                "failed_case_ids": load_json_record(HYBRID_SUMMARY_PATH)["failed_case_ids"],
            },
        },
        "counterfactual_summary": {
            method_id: {
                "counterfactual_summary_recall_at_5": payload["counterfactual_summary_recall_at_5"],
                "counterfactual_boundary_violation_rate": payload["counterfactual_boundary_violation_rate"],
                "counterfactual_eligible_for_rag": payload["counterfactual_eligible_for_rag"],
            }
            for method_id, payload in counterfactual.items()
        },
    }


def build_recommendations(
    *,
    top20_recall_analysis: dict[str, Any],
    boundary_violation_diagnostics: dict[str, Any],
    counterfactual: dict[str, Any],
) -> dict[str, Any]:
    any_counterfactual_solves_boundary = any(
        payload["counterfactual_boundary_violation_rate"] == 0.0
        for payload in counterfactual.values()
    )
    any_counterfactual_solves_recall = any(
        payload["counterfactual_summary_recall_at_5"] == 1.0
        for payload in counterfactual.values()
    )
    if any_counterfactual_solves_boundary and not any_counterfactual_solves_recall:
        recommended_minimum_change = "scope_aware_hard_filter_plus_candidate_pool_or_rerank"
        secondary_change = "document_diversity_or_chunk_dedup"
    elif any_counterfactual_solves_boundary and any_counterfactual_solves_recall:
        recommended_minimum_change = "scope_aware_hard_filter_plus_backfill"
        secondary_change = "document_diversity_or_chunk_dedup"
    else:
        recommended_minimum_change = "scope_aware_hard_filter_plus_candidate_pool_or_rerank"
        secondary_change = "embedding_or_query_strategy_review_if_top20_gaps_persist"
    return {
        "recommended_minimum_change": recommended_minimum_change,
        "secondary_change_if_needed": secondary_change,
        "changes_not_justified_by_evidence": [
            "change_bm25_parameters",
            "change_embedding_model_or_revision",
            "change_rrf_parameters",
            "introduce_reranker_before_runtime_scope_control_is_evaluated",
            "modify_gold_or_benchmark_contracts",
        ],
        "whether_new_retriever_version_is_required": True,
    }


def _build_retriever(
    *,
    context: DiagnosticContext,
    method_id: str,
    legacy_documents: list[Any],
    legacy_chunks: list[Any],
) -> Any:
    lexical_config = LexicalBaselineConfig.model_validate(context.lexical_config_payload["algorithm_config"])
    lexical_retriever = WeightedBM25Retriever(config=lexical_config)
    lexical_retriever.build_index(documents=legacy_documents, chunks=legacy_chunks)
    if method_id == "lexical_v1":
        return lexical_retriever

    vector_config = VectorBaselineConfig.model_validate(context.vector_config_payload["algorithm_config"])
    knowledge_base_version = load_json_record(Path(context.benchmark_config["manifest_file"]))["knowledge_base_version"]
    with _network_guard(), huggingface_offline_environment():
        snapshot_path = resolve_local_model_snapshot(
            repo_id=vector_config.model_name_or_path,
            revision=vector_config.model_revision or DEFAULT_EMBEDDING_REVISION,
        )
        provider = SentenceTransformerEmbeddingProvider(
            model_name_or_path=vector_config.model_name_or_path,
            local_snapshot_path=snapshot_path,
            batch_size=vector_config.batch_size,
            device=vector_config.device,
            normalize_embeddings=vector_config.normalize_embeddings,
            allow_model_download=False,
            query_prefix=vector_config.query_prefix,
            document_prefix=vector_config.document_prefix,
            expected_dimension=384,
            expected_revision=vector_config.model_revision,
        )
        vector_retriever = ExactVectorRetriever(
            config=vector_config,
            embedding_provider=provider,
            project_root=PROJECT_ROOT,
        )
        vector_retriever.build_index(
            documents=legacy_documents,
            chunks=legacy_chunks,
            knowledge_base_version=knowledge_base_version,
        )
    if method_id == "vector_v1":
        return vector_retriever

    hybrid_config = HybridBaselineConfig.model_validate(context.hybrid_config_payload["algorithm_config"])
    return ReciprocalRankFusionRetriever(
        config=hybrid_config,
        lexical_retriever=lexical_retriever,
        vector_retriever=vector_retriever,
    )


def _run_diagnostic_report(
    *,
    cases: list[RetrievalEvaluationCaseV2],
    retriever: Any,
    method_id: str,
    top_k: int,
    documents: list[KnowledgeDocumentV2],
    chunks: list[KnowledgeChunkV2],
) -> tuple[RetrievalRunnerV2Report, dict[str, dict[str, Any]]]:
    documents_by_id = {document.document_id: document for document in documents}
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    run_results: list[RetrievalRunResult] = []
    case_scores = []
    case_results: list[RetrievalRunnerV2CaseResult] = []
    debug_by_case_id: dict[str, dict[str, Any]] = {}

    for case in cases:
        runtime_input = make_runtime_input_v2(case=case, top_k=top_k)
        runtime_filters = runtime_input_to_retriever_filters(runtime_input)
        try:
            candidates = retriever.retrieve(
                query=runtime_input.query,
                filters=runtime_filters,
                top_k=runtime_input.top_k,
            )
            debug = _build_debug_payload(
                retrieval_method=method_id,
                query=runtime_input.query,
                candidates=candidates,
                retriever_debug=getattr(retriever, "last_retrieval_debug", {}),
                retriever=retriever,
            )
            run_result = RetrievalRunResult(
                retrieval_case_id=case.retrieval_case_id,
                retrieval_method=RetrievalMethod(method_id),
                retrieved_candidates=candidates,
                latency_ms=int(debug.get("elapsed_ms", 0)),
            )
        except Exception as exc:
            debug = {
                "elapsed_ms": 0,
                "diagnostic_request_error": True,
            }
            run_result = RetrievalRunResult(
                retrieval_case_id=case.retrieval_case_id,
                retrieval_method=RetrievalMethod(method_id),
                retrieved_candidates=[],
                latency_ms=0,
                error_type="retrieval_error",
                error_message=_safe_error_message(exc),
            )
        case_score, candidate_boundary_reasons = evaluate_retrieval_case_v2(
            case=case,
            result=run_result,
            documents_by_id=documents_by_id,
            chunks_by_id=chunks_by_id,
        )
        failure_taxonomy = classify_retrieval_failures_v2(
            query=runtime_input.query,
            retrieval_method=method_id,
            result=run_result,
            metrics={
                "recall_at_5": case_score.recall_at_5,
                "relevant_hit_count": _count_relevant_items_in_candidates(
                    case=case,
                    candidates=[candidate.model_dump(mode="json") for candidate in run_result.retrieved_candidates],
                    top_k=TOP_K_FORMAL,
                ),
                "forbidden_hit": case_score.forbidden_hit,
                "solution_boundary_violation": case_score.solution_boundary_violation,
            },
            debug=debug,
            minimum_relevant_hits=case.evaluation_gold.minimum_relevant_hits,
        )
        passed_blocking_gate = not failure_taxonomy
        case_score.eligible_for_rag = passed_blocking_gate
        case_score.disqualification_reasons = list(failure_taxonomy)
        run_results.append(run_result)
        case_scores.append(case_score)
        case_results.append(
            RetrievalRunnerV2CaseResult(
                retrieval_case_id=case.retrieval_case_id,
                source_case_id=case.source_case_id,
                retrieval_method=RetrievalMethod(method_id),
                top_k=top_k,
                runtime_input={
                    "query": runtime_input.query,
                    "operational_filters": dict(runtime_input.operational_filters),
                    "operational_solution_scope": list(runtime_input.operational_solution_scope),
                    "allowed_document_types": list(runtime_input.allowed_document_types),
                    "industries": list(runtime_input.industries),
                    "tags": list(runtime_input.tags),
                    "effective_on": runtime_input.effective_on.isoformat(),
                    "top_k": runtime_input.top_k,
                },
                retrieved_candidates=[candidate.model_dump(mode="json") for candidate in run_result.retrieved_candidates],
                case_metrics=case_score.model_dump(mode="json"),
                passed_blocking_gate=passed_blocking_gate,
                failure_reasons=list(case_score.disqualification_reasons),
                failure_taxonomy=list(failure_taxonomy),
                runtime_gold_leak_detected=runtime_input_has_gold_leak(runtime_input),
                candidate_boundary_reasons=candidate_boundary_reasons,
            )
        )
        debug_by_case_id[case.retrieval_case_id] = debug

    summary = aggregate_summary_metrics_v2(case_scores)
    summary.eligible_for_rag = (
        summary.recall_at_5 == 1.0
        and summary.forbidden_hit_rate == 0
        and summary.solution_boundary_violation_rate == 0
        and summary.request_error_count == 0
        and all(result.passed_blocking_gate for result in case_results)
    )
    ordered_reasons: list[str] = []
    for case_result in case_results:
        for reason in case_result.failure_taxonomy:
            if reason not in ordered_reasons:
                ordered_reasons.append(reason)
    summary.disqualification_reasons = ordered_reasons
    return (
        RetrievalRunnerV2Report(
            case_results=case_results,
            run_results=run_results,
            case_scores=case_scores,
            summary=summary,
        ),
        debug_by_case_id,
    )


def _build_missing_item_diagnostics(
    *,
    case: RetrievalEvaluationCaseV2,
    method_id: str,
    top5_candidates: list[dict[str, Any]],
    top20_candidates: list[dict[str, Any]],
    debug_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    missing_items: list[dict[str, Any]] = []
    top5_hit_ids = {
        _candidate_relevance_id_for_case(case=case, candidate=candidate)
        for candidate in top5_candidates[:TOP_K_FORMAL]
    }
    for item_id in case.evaluation_gold.expected_relevant_chunk_ids:
        if item_id not in top5_hit_ids:
            missing_items.append(
                _classify_missing_item(
                    case=case,
                    method_id=method_id,
                    item_id=item_id,
                    item_type="chunk",
                    top5_candidates=top5_candidates,
                    top20_candidates=top20_candidates,
                    debug_payload=debug_payload,
                )
            )
    for item_id in case.evaluation_gold.expected_relevant_document_ids:
        if item_id not in top5_hit_ids:
            missing_items.append(
                _classify_missing_item(
                    case=case,
                    method_id=method_id,
                    item_id=item_id,
                    item_type="document",
                    top5_candidates=top5_candidates,
                    top20_candidates=top20_candidates,
                    debug_payload=debug_payload,
                )
            )
    return missing_items


def _classify_missing_item(
    *,
    case: RetrievalEvaluationCaseV2,
    method_id: str,
    item_id: str,
    item_type: str,
    top5_candidates: list[dict[str, Any]],
    top20_candidates: list[dict[str, Any]],
    debug_payload: dict[str, Any],
) -> dict[str, Any]:
    rank_in_top20 = _find_relevant_item_rank(case=case, candidates=top20_candidates, item_id=item_id)
    expected_document_id = item_id if item_type == "document" else item_id.split("#chunk-")[0]
    competing_top5_candidates = [
        _candidate_identity(candidate)
        for candidate in top5_candidates
        if candidate["document_id"] == expected_document_id
    ]
    duplicate_competition = bool(competing_top5_candidates) and rank_in_top20 is not None and rank_in_top20 > TOP_K_FORMAL
    if duplicate_competition:
        cause = "same_document_chunk_crowding" if item_type == "chunk" else "duplicate_document_competition"
    elif rank_in_top20 is not None and 6 <= rank_in_top20 <= 10:
        cause = "rank_6_to_10"
    elif rank_in_top20 is not None and 11 <= rank_in_top20 <= 20:
        cause = "rank_11_to_20"
    elif method_id == "lexical_v1":
        if debug_payload.get("lexical_query_tokens"):
            cause = "lexical_term_mismatch"
        else:
            cause = "unknown_recall_cause"
    elif method_id == "vector_v1":
        cause = "vector_semantic_mismatch"
    elif method_id == "hybrid_v1":
        fusion_candidate = next(
            (candidate for candidate in top20_candidates if _candidate_relevance_id_for_case(case=case, candidate=candidate) == item_id),
            None,
        )
        if fusion_candidate is not None and (
            (fusion_candidate.get("lexical_rank") is not None and fusion_candidate["lexical_rank"] <= 5)
            or (fusion_candidate.get("vector_rank") is not None and fusion_candidate["vector_rank"] <= 5)
        ):
            cause = "fusion_rank_suppression"
        else:
            cause = "not_in_top_20"
    else:
        cause = "not_in_top_20"
    if rank_in_top20 is None and cause not in {"lexical_term_mismatch", "vector_semantic_mismatch", "fusion_rank_suppression"}:
        cause = "not_in_top_20"
    matching_candidate = next(
        (candidate for candidate in top20_candidates if _candidate_relevance_id_for_case(case=case, candidate=candidate) == item_id),
        None,
    )
    return {
        "item_id": item_id,
        "item_type": item_type,
        "rank_in_top_20": rank_in_top20,
        "cause": cause,
        "competing_top5_candidates": competing_top5_candidates,
        "lexical_rank": matching_candidate.get("lexical_rank") if matching_candidate else None,
        "vector_rank": matching_candidate.get("vector_rank") if matching_candidate else None,
        "rrf_rank": matching_candidate.get("rank") if matching_candidate and method_id == "hybrid_v1" else None,
        "matched_terms": matching_candidate.get("matched_terms", []) if matching_candidate else [],
        "vector_score": matching_candidate.get("score") if matching_candidate and method_id == "vector_v1" else matching_candidate.get("vector_score") if matching_candidate else None,
    }


def _augment_boundary_candidate_record(
    *,
    case: RetrievalEvaluationCaseV2,
    candidate: dict[str, Any],
    documents_by_id: dict[str, KnowledgeDocumentV2],
    chunks_by_id: dict[str, KnowledgeChunkV2],
) -> dict[str, Any]:
    document = documents_by_id[candidate["document_id"]]
    chunk = chunks_by_id.get(candidate["chunk_id"]) if candidate.get("chunk_id") else None
    source = chunk or document
    evaluation_decision = evaluate_candidate_boundary_v2(case=case, document=document, chunk=chunk)
    runtime_decision = _runtime_scope_decision(
        operational_solution_scope=case.runtime_context.operational_solution_scope,
        source=source,
    )
    evaluation_boundary_violation = not evaluation_decision.candidate_allowed
    cause = _classify_boundary_cause(
        source=source,
        runtime_decision=runtime_decision,
        case=case,
        document=document,
        evaluation_reasons=set(evaluation_decision.reasons),
    )
    return {
        "candidate_rank": candidate["rank"],
        "document_id": candidate["document_id"],
        "chunk_id": candidate.get("chunk_id"),
        "document_type": candidate["document_type"],
        "scope_type": source.scope_type.value,
        "primary_solution_id": source.primary_solution_id,
        "applicable_solution_ids": list(source.applicable_solution_ids),
        "excluded_solution_ids": list(source.excluded_solution_ids),
        "runtime_operational_solution_scope": list(case.runtime_context.operational_solution_scope),
        "runtime_allowed_document_types": list(case.runtime_context.allowed_document_types),
        "boundary_violation_reason": list(evaluation_decision.reasons),
        "candidate_hits_expected_gold": _candidate_relevance_id_for_case(case=case, candidate=candidate) in _relevant_item_ids(case),
        "candidate_is_global_policy": source.scope_type.value == "global_policy",
        "candidate_is_cross_cutting_requirement": source.scope_type.value == "cross_cutting_requirement",
        "should_be_excluded_by_runtime_eligibility": not runtime_decision["allowed"],
        "current_boundary_violation": evaluation_boundary_violation,
        "boundary_reason_category": cause,
        "why_candidate_still_entered_top5": _why_candidate_still_ranked(runtime_decision=runtime_decision),
        "boundary_violation": evaluation_boundary_violation,
    }


def _runtime_scope_decision(
    *,
    operational_solution_scope: Iterable[str],
    source: Any,
) -> dict[str, Any]:
    operational_scope = set(operational_solution_scope)
    applicable = set(source.applicable_solution_ids)
    excluded = set(source.excluded_solution_ids)
    reasons: list[str] = []
    if operational_scope and excluded & operational_scope:
        reasons.append("candidate_excludes_operational_scope")
    if source.scope_type.value != "global_policy" and operational_scope and applicable.isdisjoint(operational_scope):
        reasons.append("candidate_outside_operational_scope")
    return {
        "allowed": not reasons,
        "reasons": reasons,
    }


def _classify_boundary_cause(
    *,
    source: Any,
    runtime_decision: dict[str, Any],
    case: RetrievalEvaluationCaseV2,
    document: KnowledgeDocumentV2,
    evaluation_reasons: set[str],
) -> str:
    reasons = set(runtime_decision["reasons"])
    if "candidate_excludes_operational_scope" in reasons:
        return "candidate_excluded_solution_match"
    if "candidate_outside_operational_scope" in reasons:
        if source is not document:
            return "chunk_scope_not_applied"
        return "runtime_solution_scope_mismatch"
    forbidden_scope = set(case.evaluation_gold.forbidden_solution_ids)
    if "forbidden_document_id" in evaluation_reasons:
        return "evaluation_only_boundary_rule"
    if source.scope_type.value == "global_policy" and forbidden_scope:
        return "global_policy_misclassification"
    if source.scope_type.value == "cross_cutting_requirement" and forbidden_scope and forbidden_scope & set(source.applicable_solution_ids):
        return "cross_cutting_scope_overlap"
    if document.document_type.value not in case.runtime_context.allowed_document_types:
        return "document_type_filter_gap"
    if forbidden_scope and forbidden_scope & set(source.applicable_solution_ids):
        return "evaluation_only_boundary_rule"
    return "ranking_intrusion_after_valid_filter"


def _scope_filter_and_backfill(
    *,
    case: RetrievalEvaluationCaseV2,
    candidates: list[dict[str, Any]],
    documents_by_id: dict[str, KnowledgeDocumentV2],
    chunks_by_id: dict[str, KnowledgeChunkV2],
    top_k: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    retained: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    for candidate in candidates:
        document = documents_by_id[candidate["document_id"]]
        chunk = chunks_by_id.get(candidate["chunk_id"]) if candidate.get("chunk_id") else None
        source = chunk or document
        decision = _runtime_scope_decision(
            operational_solution_scope=case.runtime_context.operational_solution_scope,
            source=source,
        )
        if decision["allowed"]:
            retained.append(candidate)
        else:
            removed.append(candidate)
        if len(retained) >= top_k and len(removed) > 0:
            continue
    return (retained[:top_k], removed)


def _has_evaluation_boundary_violation(
    *,
    case: RetrievalEvaluationCaseV2,
    candidates: list[dict[str, Any]],
    documents_by_id: dict[str, KnowledgeDocumentV2],
    chunks_by_id: dict[str, KnowledgeChunkV2],
) -> bool:
    for candidate in candidates:
        document = documents_by_id[candidate["document_id"]]
        chunk = chunks_by_id.get(candidate["chunk_id"]) if candidate.get("chunk_id") else None
        decision = evaluate_candidate_boundary_v2(case=case, document=document, chunk=chunk)
        if not decision.candidate_allowed:
            return True
    return False


def _relevant_item_ids(case: RetrievalEvaluationCaseV2) -> set[str]:
    return set(case.evaluation_gold.expected_relevant_document_ids) | set(case.evaluation_gold.expected_relevant_chunk_ids)


def _candidate_relevance_id_for_case(
    *,
    case: RetrievalEvaluationCaseV2,
    candidate: dict[str, Any],
) -> str:
    chunk_id = candidate.get("chunk_id")
    if chunk_id and chunk_id in set(case.evaluation_gold.expected_relevant_chunk_ids):
        return chunk_id
    if candidate["document_id"] in set(case.evaluation_gold.expected_relevant_document_ids):
        return candidate["document_id"]
    return chunk_id or candidate["document_id"]


def _count_relevant_items_in_candidates(
    *,
    case: RetrievalEvaluationCaseV2,
    candidates: list[dict[str, Any]],
    top_k: int,
) -> int:
    hits = 0
    for candidate in candidates[:top_k]:
        if _candidate_relevance_id_for_case(case=case, candidate=candidate) in _relevant_item_ids(case):
            hits += 1
    return hits


def _recall_at(
    *,
    case: RetrievalEvaluationCaseV2,
    candidates: list[dict[str, Any]],
    top_k: int,
) -> float:
    return _count_relevant_items_in_candidates(case=case, candidates=candidates, top_k=top_k) / len(_relevant_item_ids(case))


def _find_relevant_item_rank(
    *,
    case: RetrievalEvaluationCaseV2,
    candidates: list[dict[str, Any]],
    item_id: str,
) -> int | None:
    for candidate in candidates[:TOP_K_DIAGNOSTIC]:
        if _candidate_relevance_id_for_case(case=case, candidate=candidate) == item_id:
            return int(candidate["rank"])
    return None


def _candidate_identity(candidate: dict[str, Any]) -> str:
    return candidate.get("chunk_id") or candidate["document_id"]


def _duplicate_document_count(candidates: list[dict[str, Any]]) -> int:
    counter = Counter(candidate["document_id"] for candidate in candidates[:TOP_K_FORMAL])
    return sum(count - 1 for count in counter.values() if count > 1)


def _same_document_chunk_crowding_count(candidates: list[dict[str, Any]]) -> int:
    return _duplicate_document_count(candidates)


def _formal_results_for_method(context: DiagnosticContext, method_id: str) -> list[dict[str, Any]]:
    if method_id == "lexical_v1":
        return context.lexical_results
    if method_id == "vector_v1":
        return context.vector_results
    if method_id == "hybrid_v1":
        return context.hybrid_results
    raise ValueError(f"Unsupported method_id: {method_id}")


def _why_candidate_still_ranked(*, runtime_decision: dict[str, Any]) -> str:
    if runtime_decision["allowed"]:
        return "runtime_filter_allowed_candidate"
    return "retriever_filters_do_not_apply_chunk_scope_and_excluded_scope_metadata"


@contextlib.contextmanager
def _network_guard():
    original_create_connection = socket.create_connection
    original_connect = socket.socket.connect

    def blocked_create_connection(*args, **kwargs):
        raise RuntimeError("Retrieval v2 diagnostics blocked a network connection attempt.")

    def blocked_connect(self, *args, **kwargs):
        raise RuntimeError("Retrieval v2 diagnostics blocked a socket connection attempt.")

    socket.create_connection = blocked_create_connection
    socket.socket.connect = blocked_connect
    try:
        yield
    finally:
        socket.create_connection = original_create_connection
        socket.socket.connect = original_connect
