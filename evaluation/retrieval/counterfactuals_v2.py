from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from evaluation.retrieval.contracts_v2 import RetrievalEvaluationCaseV2, evaluate_candidate_boundary_v2
from evaluation.retrieval.diagnostics_v2 import (
    DIAGNOSIS_OUTPUT_PATH,
    TOP_K_DIAGNOSTIC,
    _candidate_relevance_id_for_case,
    _count_relevant_items_in_candidates,
    compute_formal_result_hashes,
    load_diagnostic_context,
    run_method_diagnostic,
)
from evaluation.retrieval.failure_taxonomy import classify_retrieval_failures_v2
from evaluation.retrieval.models import RetrievalCandidate, RetrievalMethod, RetrievalRunResult
from evaluation.retrieval.runner_v2 import (
    aggregate_summary_metrics_v2,
    evaluate_retrieval_case_v2,
    make_runtime_input_v2,
)
from evaluation.retrieval.storage import diff_json_objects, load_json_record, write_json_atomic
from knowledge_base import KnowledgeChunkV2, KnowledgeDocumentV2


COUNTERFACTUAL_OUTPUT_PATH = Path("data/evaluation/retrieval/retrieval_v2_counterfactual_matrix.json")
COUNTERFACTUAL_DOC_PATH = Path("docs/29_Retrieval_V2_Design_Decision.md")
BENCHMARK_CONFIG_PATH = Path("data/evaluation/retrieval/retrieval_benchmark_config.v2.json")

METHOD_IDS = ("lexical_v1", "vector_v1", "hybrid_v1")
RUNTIME_SAFE_STRATEGIES = ("S0", "S1", "S2", "S3")
ALL_STRATEGIES = ("S0", "S1", "S2", "S3", "S4")
POOL_SIZES = (5, 10, 20)
DIVERSITY_MODES = ("no_diversity", "max_2_chunks_per_document", "max_1_chunk_per_document")
RERANK_MODES = ("original_rank", "runtime_scope_fit")
STRATEGY_ORDER = {name: index for index, name in enumerate(ALL_STRATEGIES)}
DIVERSITY_ORDER = {
    "no_diversity": 0,
    "max_2_chunks_per_document": 1,
    "max_1_chunk_per_document": 2,
}
SCOPE_SPECIFICITY_ORDER = {
    "solution_specific": 0,
    "multi_solution": 1,
    "cross_cutting_requirement": 2,
    "global_policy": 3,
}
MAX_CANDIDATES_PER_DOCUMENT = {
    "no_diversity": None,
    "max_2_chunks_per_document": 2,
    "max_1_chunk_per_document": 1,
}


@dataclass(frozen=True)
class CounterfactualMethodRun:
    method_id: str
    case_results: list[dict[str, Any]]
    case_results_by_id: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class CandidateSourceView:
    candidate_id: str
    document_id: str
    chunk_id: str | None
    document_type: str
    score: float
    original_rank: int
    lexical_rank: int | None
    vector_rank: int | None
    lexical_score: float | None
    vector_score: float | None
    rrf_score: float | None
    scope_type: str
    primary_solution_id: str | None
    applicable_solution_ids: tuple[str, ...]
    excluded_solution_ids: tuple[str, ...]
    industries: tuple[str, ...]
    tags: tuple[str, ...]
    effective_from: date | None
    effective_until: date | None
    citation_label: str
    document: KnowledgeDocumentV2
    chunk: KnowledgeChunkV2 | None


def build_plan_payload() -> dict[str, Any]:
    benchmark_config = load_json_record(BENCHMARK_CONFIG_PATH)
    diagnosis_payload = load_json_record(DIAGNOSIS_OUTPUT_PATH)
    return {
        "mode": "plan",
        "analysis_version": "retrieval_v2_counterfactual_matrix_v1",
        "diagnostic_only": True,
        "benchmark_version": benchmark_config["benchmark_version"],
        "case_count": benchmark_config["case_count"],
        "methods": list(METHOD_IDS),
        "runtime_safe_strategies": list(RUNTIME_SAFE_STRATEGIES),
        "all_strategies": list(ALL_STRATEGIES),
        "pool_sizes": list(POOL_SIZES),
        "diversity_modes": list(DIVERSITY_MODES),
        "rerank_modes": list(RERANK_MODES),
        "formal_result_hashes": compute_formal_result_hashes(),
        "diagnosis_hash": _sha256(DIAGNOSIS_OUTPUT_PATH),
        "diagnosis_version": diagnosis_payload["diagnosis_version"],
        "planned_outputs": {
            "json": str(COUNTERFACTUAL_OUTPUT_PATH),
            "doc": str(COUNTERFACTUAL_DOC_PATH),
        },
        "note": "Failure diagnosis artifact does not store complete top-20 candidate lists, so check/write modes reuse offline diagnostic top-20 replays.",
    }


def build_counterfactual_payload() -> dict[str, Any]:
    context = load_diagnostic_context()
    diagnosis_payload = load_json_record(DIAGNOSIS_OUTPUT_PATH)
    benchmark_config = load_json_record(BENCHMARK_CONFIG_PATH)
    runtime_inputs = {case.retrieval_case_id: make_runtime_input_v2(case=case, top_k=5) for case in context.cases}
    documents_by_id = {document.document_id: document for document in context.documents}
    chunks_by_id = {chunk.chunk_id: chunk for chunk in context.chunks}

    method_runs = {
        method_id: _build_method_run(
            method_id=method_id,
            case_results=run_method_diagnostic(context=context, method_id=method_id, top_k=TOP_K_DIAGNOSTIC).formal_case_results,
        )
        for method_id in METHOD_IDS
    }

    boundary_candidate_analysis, executability_summary = _build_boundary_candidate_analysis(
        diagnosis_payload=diagnosis_payload,
        cases=context.cases,
        runtime_inputs=runtime_inputs,
        documents_by_id=documents_by_id,
        chunks_by_id=chunks_by_id,
    )

    matrix_results: list[dict[str, Any]] = []
    for method_id in METHOD_IDS:
        method_run = method_runs[method_id]
        for strategy in ALL_STRATEGIES:
            for pool_size in POOL_SIZES:
                for diversity_mode in DIVERSITY_MODES:
                    for rerank_mode in RERANK_MODES:
                        matrix_results.append(
                            _evaluate_counterfactual_combo(
                                method_id=method_id,
                                method_run=method_run,
                                cases=context.cases,
                                runtime_inputs=runtime_inputs,
                                documents_by_id=documents_by_id,
                                chunks_by_id=chunks_by_id,
                                strategy=strategy,
                                pool_size=pool_size,
                                diversity_mode=diversity_mode,
                                rerank_mode=rerank_mode,
                                blocking_gate=benchmark_config["blocking_gate"],
                            )
                        )

    best_runtime_safe_by_method = {
        method_id: _select_best_entry(
            [entry for entry in matrix_results if entry["method_id"] == method_id and not entry["oracle_only"]]
        )
        for method_id in METHOD_IDS
    }
    runtime_safe_entries = [entry for entry in matrix_results if not entry["oracle_only"]]
    best_runtime_safe_strategy = _select_best_entry(runtime_safe_entries)
    zero_boundary_runtime_safe_entries = [
        entry for entry in runtime_safe_entries if entry["solution_boundary_violation_rate"] == 0.0
    ]
    best_zero_boundary_runtime_safe_strategy = (
        _select_best_entry(zero_boundary_runtime_safe_entries) if zero_boundary_runtime_safe_entries else None
    )
    oracle_upper_bound = _select_best_entry([entry for entry in matrix_results if entry["oracle_only"]])
    unresolved_recall_cases = _build_unresolved_recall_cases(diagnosis_payload)
    unresolved_boundary_cases = _build_unresolved_boundary_cases(best_runtime_safe_strategy)
    document_diversity_supported = _document_diversity_supported(matrix_results)

    oracle_boundary = oracle_upper_bound["solution_boundary_violation_rate"]
    runtime_contract_upgrade_required = (
        executability_summary["evaluation_only_boundary_candidates"] > 0
        or (not zero_boundary_runtime_safe_entries and oracle_boundary == 0.0)
    )
    candidate_generation_upgrade_required = any(unresolved_recall_cases.values())
    retriever_v2_ready = bool(best_runtime_safe_strategy["eligible_for_rag"])

    if retriever_v2_ready:
        recommended_next_step = "implement_retriever_v2_runtime_safe_strategy"
    elif best_zero_boundary_runtime_safe_strategy is not None and candidate_generation_upgrade_required:
        recommended_next_step = "implement_runtime_safe_scope_control_and_upgrade_candidate_generation"
    elif runtime_contract_upgrade_required and candidate_generation_upgrade_required:
        recommended_next_step = "upgrade_runtime_boundary_contract_and_candidate_generation"
    elif candidate_generation_upgrade_required:
        recommended_next_step = "upgrade_candidate_generation_before_runtime_rerank"
    elif runtime_contract_upgrade_required:
        recommended_next_step = "upgrade_runtime_boundary_contract_before_retriever_v2"
    else:
        recommended_next_step = "implement_runtime_safe_scope_control_then_re-benchmark"

    payload = {
        "analysis_version": "retrieval_v2_counterfactual_matrix_v1",
        "diagnostic_only": True,
        "formal_result_hashes": compute_formal_result_hashes(),
        "diagnosis_hash": _sha256(DIAGNOSIS_OUTPUT_PATH),
        "diagnosis_version": diagnosis_payload["diagnosis_version"],
        "runtime_boundary_executability": executability_summary,
        "boundary_candidate_analysis": boundary_candidate_analysis,
        "strategy_definitions": _strategy_definitions(),
        "matrix_results": matrix_results,
        "best_runtime_safe_strategy_by_method": best_runtime_safe_by_method,
        "best_runtime_safe_strategy": best_runtime_safe_strategy,
        "best_zero_boundary_runtime_safe_strategy": best_zero_boundary_runtime_safe_strategy,
        "oracle_upper_bound": oracle_upper_bound,
        "unresolved_recall_cases": unresolved_recall_cases,
        "unresolved_boundary_cases": unresolved_boundary_cases,
        "recommended_next_step": recommended_next_step,
        "retriever_v2_ready_for_implementation": retriever_v2_ready,
        "runtime_contract_upgrade_required": runtime_contract_upgrade_required,
        "candidate_generation_upgrade_required": candidate_generation_upgrade_required,
        "document_diversity_supported": document_diversity_supported,
        "embedding_change_supported": False,
        "architecture_c_status": "blocked",
        "limitations": [
            "This analysis reuses the frozen v2 benchmark inputs and frozen retriever parameters.",
            "Top-20 candidates are regenerated offline from the existing diagnostic path because the tracked diagnosis artifact stores summaries instead of full top-20 candidates.",
            "S4 is an oracle-only upper bound and must not be used as a production recommendation.",
            "This matrix evaluates deterministic filtering, diversity, and rerank policy only; it does not modify formal results or production retrievers.",
        ],
    }
    return payload


def render_counterfactual_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Retrieval V2 Design Decision")
    lines.append("")
    lines.append("## 为什么不能直接实现 Hard Filter")
    lines.append("")
    lines.append(
        "- 当前正式 Recall@5 分别为 Lexical 0.8854166666666666、Vector 0.8697916666666666、Hybrid 0.8854166666666666。"
    )
    lines.append("- Top-20 上界显示：Lexical 只有 13/16 个 case 在 Top-20 达到 full recall；Vector 和 Hybrid 也只有 15/16。")
    lines.append("- 因此即使在 Top-20 内做完美无 Gold Rerank，也无法让全部方法通过 recall gate。")
    lines.append("")
    lines.append("## Top-20 上界说明")
    lines.append("")
    for method_id, summary in payload["best_runtime_safe_strategy_by_method"].items():
        lines.append(
            f"- {method_id}: best_runtime_safe_recall_at_5={summary['recall_at_5']}, "
            f"boundary_rate={summary['solution_boundary_violation_rate']}, "
            f"strategy={summary['strategy_id']}, pool={summary['pool_size']}, "
            f"diversity={summary['diversity_mode']}, rerank={summary['rerank_mode']}"
        )
    lines.append("")
    lines.append("## Boundary Runtime 可执行性")
    lines.append("")
    boundary = payload["runtime_boundary_executability"]
    lines.append(f"- total_boundary_violating_candidates: {boundary['total_boundary_violating_candidates']}")
    lines.append(f"- runtime_identifiable_boundary_candidates: {boundary['runtime_identifiable_boundary_candidates']}")
    lines.append(f"- evaluation_only_boundary_candidates: {boundary['evaluation_only_boundary_candidates']}")
    lines.append(f"- metadata_error_candidates: {boundary['metadata_error_candidates']}")
    lines.append(f"- ranking_only_boundary_candidates: {boundary['ranking_only_boundary_candidates']}")
    lines.append(
        f"- cross_cutting_scope_overlap can use applicable_solution_ids + operational_solution_scope only: {str(boundary['cross_cutting_scope_overlap_runtime_identifiable']).lower()}"
    )
    lines.append(f"- recommended eligibility semantics: {boundary['recommended_scope_semantics']}")
    lines.append(f"- benchmark_has_runtime_inexecutable_boundary: {str(boundary['benchmark_has_runtime_inexecutable_boundary']).lower()}")
    lines.append("")
    lines.append("## evaluation-only 规则问题")
    lines.append("")
    lines.append(
        f"- evaluation_only dependency fields: {', '.join(boundary['evaluation_only_dependency_fields']) or 'none'}"
    )
    lines.append(
        f"- missing runtime-equivalent fields: {', '.join(boundary['runtime_equivalent_fields_missing']) or 'none'}"
    )
    lines.append("")
    lines.append("## Scope 策略 S0-S4")
    lines.append("")
    for strategy_id, details in payload["strategy_definitions"].items():
        lines.append(f"### {strategy_id}")
        lines.append("")
        lines.append(f"- oracle_only: {str(details['oracle_only']).lower()}")
        lines.append(f"- summary: {details['summary']}")
        lines.append("")
    lines.append("## Candidate Pool 矩阵")
    lines.append("")
    for pool_size in POOL_SIZES:
        entries = [entry for entry in payload["matrix_results"] if entry["pool_size"] == pool_size and not entry["oracle_only"]]
        best = _select_best_entry(entries)
        lines.append(
            f"- pool_{pool_size}: best={best['method_id']} / {best['strategy_id']} / {best['diversity_mode']} / {best['rerank_mode']} "
            f"(recall_at_5={best['recall_at_5']}, boundary={best['solution_boundary_violation_rate']})"
        )
    lines.append("")
    lines.append("## Document Diversity 矩阵")
    lines.append("")
    for diversity_mode in DIVERSITY_MODES:
        entries = [entry for entry in payload["matrix_results"] if entry["diversity_mode"] == diversity_mode and not entry["oracle_only"]]
        best = _select_best_entry(entries)
        lines.append(
            f"- {diversity_mode}: best={best['method_id']} / {best['strategy_id']} / pool_{best['pool_size']} / {best['rerank_mode']} "
            f"(recall_at_5={best['recall_at_5']}, boundary={best['solution_boundary_violation_rate']})"
        )
    lines.append("")
    lines.append("## Runtime Scope Fit Rerank 结果")
    lines.append("")
    lines.append(
        f"- runtime_scope_fit_rerank materially supported: {str(payload['document_diversity_supported']).lower()}"
    )
    lines.append(
        f"- best runtime-safe strategy: {payload['best_runtime_safe_strategy']['method_id']} / {payload['best_runtime_safe_strategy']['strategy_id']} / "
        f"pool_{payload['best_runtime_safe_strategy']['pool_size']} / {payload['best_runtime_safe_strategy']['diversity_mode']} / "
        f"{payload['best_runtime_safe_strategy']['rerank_mode']}"
    )
    lines.append("")
    lines.append("## 最佳 Runtime-safe 组合")
    lines.append("")
    best = payload["best_runtime_safe_strategy"]
    lines.append(f"- recall_at_5: {best['recall_at_5']}")
    lines.append(f"- solution_boundary_violation_rate: {best['solution_boundary_violation_rate']}")
    lines.append(f"- failed_case_ids: {', '.join(best['failed_case_ids']) or 'none'}")
    lines.append(f"- eligible_for_rag: {str(best['eligible_for_rag']).lower()}")
    zero_boundary = payload.get("best_zero_boundary_runtime_safe_strategy")
    if zero_boundary is not None:
        lines.append(
            f"- best_zero_boundary_runtime_safe: {zero_boundary['method_id']} / {zero_boundary['strategy_id']} / "
            f"pool_{zero_boundary['pool_size']} / {zero_boundary['diversity_mode']} / {zero_boundary['rerank_mode']} "
            f"(recall_at_5={zero_boundary['recall_at_5']}, boundary={zero_boundary['solution_boundary_violation_rate']})"
        )
    lines.append("")
    lines.append("## Oracle 上界")
    lines.append("")
    oracle = payload["oracle_upper_bound"]
    lines.append(
        f"- {oracle['method_id']} / {oracle['strategy_id']} / pool_{oracle['pool_size']} / {oracle['diversity_mode']} / {oracle['rerank_mode']}"
    )
    lines.append(f"- recall_at_5: {oracle['recall_at_5']}")
    lines.append(f"- solution_boundary_violation_rate: {oracle['solution_boundary_violation_rate']}")
    lines.append(f"- eligible_for_rag: {str(oracle['eligible_for_rag']).lower()}")
    lines.append("")
    lines.append("## 无法通过 Rerank 解决的 Case")
    lines.append("")
    for method_id, cases in payload["unresolved_recall_cases"].items():
        lines.append(f"### {method_id}")
        lines.append("")
        for item in cases:
            lines.append(
                f"- {item['case_id']}: recall_at_20={item['recall_at_20']}, missing_items={', '.join(item['missing_item_ids'])}, causes={', '.join(item['causes'])}"
            )
        lines.append("")
    lines.append("## 是否需要 Runtime 合同 v2.1")
    lines.append("")
    lines.append(f"- runtime_contract_upgrade_required: {str(payload['runtime_contract_upgrade_required']).lower()}")
    lines.append("")
    lines.append("## 是否需要 Candidate Generation v2")
    lines.append("")
    lines.append(f"- candidate_generation_upgrade_required: {str(payload['candidate_generation_upgrade_required']).lower()}")
    lines.append("")
    lines.append("## 是否支持 Document Diversity")
    lines.append("")
    lines.append(f"- document_diversity_supported: {str(payload['document_diversity_supported']).lower()}")
    lines.append("")
    lines.append("## 为什么不换 Embedding")
    lines.append("")
    lines.append("- 当前没有证据表明更换 embedding 模型是跨 case 主瓶颈。")
    lines.append("- Top-20 gap 主要由 candidate generation 缺口、同文档拥挤和 boundary 资格控制共同造成。")
    lines.append("")
    lines.append("## Retriever v2 最小实现范围")
    lines.append("")
    lines.append(f"- recommended_next_step: {payload['recommended_next_step']}")
    lines.append(f"- retriever_v2_ready_for_implementation: {str(payload['retriever_v2_ready_for_implementation']).lower()}")
    lines.append("")
    lines.append("## Architecture C 仍被阻断")
    lines.append("")
    lines.append(f"- architecture_c_status: {payload['architecture_c_status']}")
    lines.append("")
    lines.append("## 合成数据和小样本限制")
    lines.append("")
    for limitation in payload["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


def write_counterfactual_outputs(payload: dict[str, Any]) -> None:
    write_json_atomic(COUNTERFACTUAL_OUTPUT_PATH, payload)
    COUNTERFACTUAL_DOC_PATH.write_text(render_counterfactual_markdown(payload), encoding="utf-8")


def check_counterfactual_outputs() -> tuple[bool, list[str]]:
    recomputed = build_counterfactual_payload()
    differences: list[str] = []

    if not COUNTERFACTUAL_OUTPUT_PATH.exists():
        differences.append(f"Missing tracked JSON output: {COUNTERFACTUAL_OUTPUT_PATH}")
    else:
        tracked_json = load_json_record(COUNTERFACTUAL_OUTPUT_PATH)
        differences.extend(diff_json_objects(tracked_json, recomputed))

    rendered_markdown = render_counterfactual_markdown(recomputed)
    if not COUNTERFACTUAL_DOC_PATH.exists():
        differences.append(f"Missing tracked Markdown output: {COUNTERFACTUAL_DOC_PATH}")
    else:
        tracked_markdown = COUNTERFACTUAL_DOC_PATH.read_text(encoding="utf-8")
        if tracked_markdown != rendered_markdown:
            differences.append(f"Markdown output drifted: {COUNTERFACTUAL_DOC_PATH}")

    return (not differences, differences)


def _build_method_run(
    *,
    method_id: str,
    case_results: list[dict[str, Any]],
) -> CounterfactualMethodRun:
    return CounterfactualMethodRun(
        method_id=method_id,
        case_results=case_results,
        case_results_by_id={item["retrieval_case_id"]: item for item in case_results},
    )


def _build_boundary_candidate_analysis(
    *,
    diagnosis_payload: dict[str, Any],
    cases: list[RetrievalEvaluationCaseV2],
    runtime_inputs: dict[str, Any],
    documents_by_id: dict[str, KnowledgeDocumentV2],
    chunks_by_id: dict[str, KnowledgeChunkV2],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    case_by_id = {case.retrieval_case_id: case for case in cases}
    output: dict[str, list[dict[str, Any]]] = {}
    total = 0
    runtime_identifiable = 0
    evaluation_only = 0
    metadata_errors = 0
    ranking_only = 0
    cross_cutting_runtime_identifiable = True
    runtime_equivalent_missing: set[str] = set()
    evaluation_only_dependency_fields: set[str] = set()

    for case_id, details in diagnosis_payload["boundary_violation_diagnostics"].items():
        case = case_by_id[case_id]
        runtime_input = runtime_inputs[case_id]
        case_items: list[dict[str, Any]] = []
        for method_id, candidates in details["violating_candidates_by_method"].items():
            for candidate in candidates:
                total += 1
                source_view = _candidate_view_from_boundary_record(
                    candidate=candidate,
                    documents_by_id=documents_by_id,
                    chunks_by_id=chunks_by_id,
                )
                runtime_outcomes = {
                    strategy: _evaluate_scope_strategy(
                        strategy=strategy,
                        case=case,
                        runtime_input=runtime_input,
                        source_view=source_view,
                    )
                    for strategy in RUNTIME_SAFE_STRATEGIES
                }
                runtime_filtering_strategies = [
                    strategy for strategy, decision in runtime_outcomes.items() if not decision["allowed"]
                ]
                can_filter_without_gold = bool(runtime_filtering_strategies)
                if can_filter_without_gold:
                    runtime_identifiable += 1
                if candidate["boundary_reason_category"] == "cross_cutting_scope_overlap" and not can_filter_without_gold:
                    cross_cutting_runtime_identifiable = False
                if not can_filter_without_gold and candidate["boundary_reason_category"] == "evaluation_only_boundary_rule":
                    evaluation_only += 1
                    evaluation_only_dependency_fields.add("forbidden_solution_ids")
                    runtime_equivalent_missing.add("runtime_forbidden_solution_scope")
                if candidate["boundary_reason_category"] in {"chunk_scope_not_applied", "global_policy_misclassification"}:
                    metadata_errors += 1
                if candidate["boundary_reason_category"] == "ranking_intrusion_after_valid_filter":
                    ranking_only += 1

                preferred_strategy = runtime_filtering_strategies[0] if runtime_filtering_strategies else None
                required_fields = _required_fields_for_strategy(preferred_strategy or "S1")
                currently_present = _fields_currently_present(
                    required_fields=required_fields,
                    runtime_input=runtime_input,
                    source_view=source_view,
                )
                missing_fields = [field for field in required_fields if field not in currently_present]
                would_filter_expected = _candidate_hits_gold(case=case, candidate_record=candidate)
                false_positive_risk = _false_positive_risk(source_view=source_view, would_filter_expected=would_filter_expected)
                false_negative_risk = "low" if can_filter_without_gold else "high"

                case_items.append(
                    {
                        "method_id": method_id,
                        "candidate_id": source_view.candidate_id,
                        "violation_reason": list(candidate["boundary_violation_reason"]),
                        "violation_reason_category": candidate["boundary_reason_category"],
                        "candidate_scope_type": source_view.scope_type,
                        "candidate_primary_solution_id": source_view.primary_solution_id,
                        "candidate_applicable_solution_ids": list(source_view.applicable_solution_ids),
                        "candidate_excluded_solution_ids": list(source_view.excluded_solution_ids),
                        "runtime_operational_solution_scope": list(runtime_input.operational_solution_scope),
                        "runtime_allowed_document_types": list(runtime_input.allowed_document_types),
                        "runtime_industries": list(runtime_input.industries),
                        "runtime_tags": list(runtime_input.tags),
                        "runtime_effective_on": runtime_input.effective_on.isoformat(),
                        "runtime_identifiable": can_filter_without_gold,
                        "required_runtime_fields": required_fields,
                        "runtime_fields_currently_present": currently_present,
                        "runtime_fields_missing": missing_fields,
                        "can_filter_without_gold": can_filter_without_gold,
                        "would_filter_expected_candidate": would_filter_expected,
                        "false_positive_risk": false_positive_risk,
                        "false_negative_risk": false_negative_risk,
                        "runtime_filtering_strategies": runtime_filtering_strategies,
                    }
                )
        output[case_id] = case_items

    summary = {
        "total_boundary_violating_candidates": total,
        "runtime_identifiable_boundary_candidates": runtime_identifiable,
        "evaluation_only_boundary_candidates": evaluation_only,
        "metadata_error_candidates": metadata_errors,
        "ranking_only_boundary_candidates": ranking_only,
        "cross_cutting_scope_overlap_runtime_identifiable": cross_cutting_runtime_identifiable,
        "recommended_scope_semantics": "strict_applicable_subset_with_global_policy_exception",
        "evaluation_only_dependency_fields": sorted(evaluation_only_dependency_fields),
        "runtime_equivalent_fields_missing": sorted(runtime_equivalent_missing),
        "benchmark_has_runtime_inexecutable_boundary": evaluation_only > 0,
    }
    return output, summary


def _evaluate_counterfactual_combo(
    *,
    method_id: str,
    method_run: CounterfactualMethodRun,
    cases: list[RetrievalEvaluationCaseV2],
    runtime_inputs: dict[str, Any],
    documents_by_id: dict[str, KnowledgeDocumentV2],
    chunks_by_id: dict[str, KnowledgeChunkV2],
    strategy: str,
    pool_size: int,
    diversity_mode: str,
    rerank_mode: str,
    blocking_gate: dict[str, Any],
) -> dict[str, Any]:
    case_results: list[dict[str, Any]] = []
    case_scores = []
    runner_case_results = []
    filtered_count = 0
    backfilled_count = 0
    diversity_skipped_count = 0

    for case in cases:
        runtime_input = runtime_inputs[case.retrieval_case_id]
        diagnostic_case = method_run.case_results_by_id[case.retrieval_case_id]
        selected_candidates, case_stats = _select_counterfactual_top5(
            case=case,
            runtime_input=runtime_input,
            candidates=diagnostic_case["candidates"],
            documents_by_id=documents_by_id,
            chunks_by_id=chunks_by_id,
            strategy=strategy,
            pool_size=pool_size,
            diversity_mode=diversity_mode,
            rerank_mode=rerank_mode,
        )
        filtered_count += case_stats["filtered_candidate_count"]
        backfilled_count += case_stats["backfilled_candidate_count"]
        diversity_skipped_count += case_stats["diversity_skipped_candidate_count"]

        run_result = RetrievalRunResult(
            retrieval_case_id=case.retrieval_case_id,
            retrieval_method=RetrievalMethod(method_id),
            retrieved_candidates=[
                _to_retrieval_candidate(
                    method_id=method_id,
                    candidate=selected,
                    source_view=_candidate_view_from_ranked_candidate(
                        candidate=selected,
                        documents_by_id=documents_by_id,
                        chunks_by_id=chunks_by_id,
                    ),
                )
                for selected in selected_candidates
            ],
            latency_ms=0,
        )
        case_score, _ = evaluate_retrieval_case_v2(
            case=case,
            result=run_result,
            documents_by_id=documents_by_id,
            chunks_by_id=chunks_by_id,
        )
        debug_payload = _counterfactual_debug_payload(
            method_id=method_id,
            query=case.query,
            selected_candidates=selected_candidates,
        )
        failure_taxonomy = classify_retrieval_failures_v2(
            query=case.query,
            retrieval_method=method_id,
            result=run_result,
            metrics={
                "recall_at_5": case_score.recall_at_5,
                "relevant_hit_count": _count_relevant_items_in_candidates(
                    case=case,
                    candidates=selected_candidates,
                    top_k=5,
                ),
                "forbidden_hit": case_score.forbidden_hit,
                "solution_boundary_violation": case_score.solution_boundary_violation,
            },
            debug=debug_payload,
            minimum_relevant_hits=case.evaluation_gold.minimum_relevant_hits,
        )
        passed = not failure_taxonomy
        case_score.eligible_for_rag = passed
        case_score.disqualification_reasons = list(failure_taxonomy)
        case_scores.append(case_score)
        runner_case_results.append(
            {
                "retrieval_case_id": case.retrieval_case_id,
                "passed_blocking_gate": passed,
                "failure_taxonomy": list(failure_taxonomy),
            }
        )
        case_results.append(
            {
                "case_id": case.retrieval_case_id,
                "source_case_id": case.source_case_id,
                "recall_at_5": case_score.recall_at_5,
                "precision_at_5": case_score.precision_at_5,
                "solution_boundary_violation": case_score.solution_boundary_violation,
                "forbidden_hit": case_score.forbidden_hit,
                "passed_blocking_gate": passed,
                "failure_reasons": list(failure_taxonomy),
                "selected_candidate_ids": [
                    candidate.get("chunk_id") or candidate["document_id"] for candidate in selected_candidates
                ],
                "filtered_candidate_count": case_stats["filtered_candidate_count"],
                "backfilled_candidate_count": case_stats["backfilled_candidate_count"],
                "diversity_skipped_candidate_count": case_stats["diversity_skipped_candidate_count"],
            }
        )

    summary = aggregate_summary_metrics_v2(case_scores)
    failed_case_ids = [item["retrieval_case_id"] for item in runner_case_results if not item["passed_blocking_gate"]]
    failure_taxonomy_counter: Counter[str] = Counter()
    for item in case_results:
        for reason in item["failure_reasons"]:
            failure_taxonomy_counter[reason] += 1

    summary_gate = _summary_gate_status(
        summary=summary.model_dump(mode="json"),
        failed_case_ids=failed_case_ids,
        blocking_gate=blocking_gate,
    )
    eligible_for_rag = summary_gate["all_gates_passed"]

    return {
        "method_id": method_id,
        "strategy_id": strategy,
        "oracle_only": strategy == "S4",
        "pool_size": pool_size,
        "diversity_mode": diversity_mode,
        "rerank_mode": rerank_mode,
        "use_runtime_scope_fit_rerank": rerank_mode == "runtime_scope_fit",
        "recall_at_1": summary.recall_at_1,
        "recall_at_3": summary.recall_at_3,
        "recall_at_5": summary.recall_at_5,
        "precision_at_3": summary.precision_at_3,
        "precision_at_5": summary.precision_at_5,
        "mean_reciprocal_rank": summary.mean_reciprocal_rank,
        "forbidden_hit_rate": summary.forbidden_hit_rate,
        "solution_boundary_violation_rate": summary.solution_boundary_violation_rate,
        "failed_case_ids": failed_case_ids,
        "failure_taxonomy": dict(sorted(failure_taxonomy_counter.items())),
        "eligible_for_rag": eligible_for_rag,
        "summary_gate": summary_gate,
        "filtered_candidate_count": filtered_count,
        "backfilled_candidate_count": backfilled_count,
        "diversity_skipped_candidate_count": diversity_skipped_count,
        "cases_with_full_recall": sum(1 for item in case_results if item["recall_at_5"] == 1.0),
        "cases_with_zero_boundary": sum(1 for item in case_results if not item["solution_boundary_violation"]),
        "case_results": case_results,
    }


def _select_counterfactual_top5(
    *,
    case: RetrievalEvaluationCaseV2,
    runtime_input: Any,
    candidates: list[dict[str, Any]],
    documents_by_id: dict[str, KnowledgeDocumentV2],
    chunks_by_id: dict[str, KnowledgeChunkV2],
    strategy: str,
    pool_size: int,
    diversity_mode: str,
    rerank_mode: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    pool_candidates = list(candidates[:pool_size])
    annotated: list[tuple[dict[str, Any], CandidateSourceView, dict[str, Any]]] = []
    for candidate in pool_candidates:
        source_view = _candidate_view_from_ranked_candidate(
            candidate=candidate,
            documents_by_id=documents_by_id,
            chunks_by_id=chunks_by_id,
        )
        decision = _evaluate_scope_strategy(
            strategy=strategy,
            case=case,
            runtime_input=runtime_input,
            source_view=source_view,
        )
        annotated.append((candidate, source_view, decision))

    if rerank_mode == "runtime_scope_fit":
        annotated = sorted(
            annotated,
            key=lambda item: _runtime_scope_fit_key(
                runtime_input=runtime_input,
                source_view=item[1],
                decision=item[2],
            ),
        )
    else:
        annotated = sorted(annotated, key=lambda item: (item[0]["rank"], item[1].candidate_id))

    selected: list[dict[str, Any]] = []
    filtered_count = 0
    backfilled_count = 0
    diversity_skipped_count = 0
    doc_counts: Counter[str] = Counter()
    max_per_document = MAX_CANDIDATES_PER_DOCUMENT[diversity_mode]

    for candidate, source_view, decision in annotated:
        if not decision["allowed"]:
            filtered_count += 1
            continue
        if max_per_document is not None and doc_counts[source_view.document_id] >= max_per_document:
            diversity_skipped_count += 1
            continue
        renumbered = dict(candidate)
        renumbered["rank"] = len(selected) + 1
        selected.append(renumbered)
        doc_counts[source_view.document_id] += 1
        if source_view.original_rank > 5:
            backfilled_count += 1
        if len(selected) >= 5:
            break

    return selected, {
        "filtered_candidate_count": filtered_count,
        "backfilled_candidate_count": backfilled_count,
        "diversity_skipped_candidate_count": diversity_skipped_count,
    }


def _evaluate_scope_strategy(
    *,
    strategy: str,
    case: RetrievalEvaluationCaseV2,
    runtime_input: Any,
    source_view: CandidateSourceView,
) -> dict[str, Any]:
    operational_scope = set(runtime_input.operational_solution_scope)
    applicable = set(source_view.applicable_solution_ids)
    excluded = set(source_view.excluded_solution_ids)
    reasons: list[str] = []

    if strategy == "S4":
        decision = evaluate_candidate_boundary_v2(case=case, document=source_view.document, chunk=source_view.chunk)
        return {
            "allowed": decision.candidate_allowed,
            "reasons": list(decision.reasons),
            "oracle_only": True,
        }

    if excluded & operational_scope:
        reasons.append("candidate_excludes_operational_scope")

    if strategy == "S0":
        if source_view.scope_type != "global_policy" and operational_scope and applicable.isdisjoint(operational_scope):
            reasons.append("candidate_outside_operational_scope")
    elif strategy == "S1":
        if source_view.scope_type != "global_policy" and operational_scope and not applicable.issubset(operational_scope):
            reasons.append("candidate_applicable_scope_not_subset_of_operational_scope")
    elif strategy == "S2":
        if source_view.scope_type == "solution_specific":
            if source_view.primary_solution_id not in operational_scope:
                reasons.append("primary_solution_not_in_operational_scope")
        elif source_view.scope_type == "multi_solution":
            if source_view.primary_solution_id not in operational_scope:
                reasons.append("primary_solution_not_in_operational_scope")
            if operational_scope and not applicable.issubset(operational_scope):
                reasons.append("candidate_applicable_scope_not_subset_of_operational_scope")
        elif source_view.scope_type == "cross_cutting_requirement":
            if operational_scope and not applicable.issubset(operational_scope):
                reasons.append("candidate_applicable_scope_not_subset_of_operational_scope")
    elif strategy == "S3":
        if source_view.scope_type != "global_policy" and operational_scope and not applicable.issubset(operational_scope):
            reasons.append("candidate_applicable_scope_not_subset_of_operational_scope")
        if runtime_input.allowed_document_types and source_view.document_type not in set(runtime_input.allowed_document_types):
            reasons.append("document_type_not_allowed")
        if runtime_input.industries and source_view.industries and set(source_view.industries).isdisjoint(set(runtime_input.industries)):
            reasons.append("industry_not_allowed")
        if runtime_input.tags and source_view.tags and set(source_view.tags).isdisjoint(set(runtime_input.tags)):
            reasons.append("tag_not_allowed")
        if not source_view.document.is_active(as_of=runtime_input.effective_on):
            reasons.append("document_not_active")
    else:
        raise ValueError(f"Unsupported strategy: {strategy}")

    return {
        "allowed": not reasons,
        "reasons": reasons,
        "oracle_only": False,
    }


def _runtime_scope_fit_key(*, runtime_input: Any, source_view: CandidateSourceView, decision: dict[str, Any]) -> tuple[Any, ...]:
    primary_match = source_view.primary_solution_id in set(runtime_input.operational_solution_scope)
    specificity = SCOPE_SPECIFICITY_ORDER[source_view.scope_type]
    return (
        0 if decision["allowed"] else 1,
        0 if primary_match else 1,
        specificity,
        source_view.original_rank,
        source_view.candidate_id,
    )


def _summary_gate_status(
    *,
    summary: dict[str, Any],
    failed_case_ids: list[str],
    blocking_gate: dict[str, Any],
) -> dict[str, Any]:
    recall_required = float(blocking_gate["summary_recall_at_5_equals"])
    forbidden_required = float(blocking_gate["summary_forbidden_hit_rate_equals"])
    boundary_required = float(blocking_gate["summary_solution_boundary_violation_rate_equals"])
    request_error_required = int(blocking_gate["summary_request_error_count_equals"])

    recall_gate_passed = float(summary["recall_at_5"]) == recall_required
    forbidden_gate_passed = float(summary["forbidden_hit_rate"]) == forbidden_required
    boundary_gate_passed = float(summary["solution_boundary_violation_rate"]) == boundary_required
    request_error_gate_passed = int(summary["request_error_count"]) == request_error_required
    all_cases_gate_passed = not failed_case_ids
    all_gates_passed = (
        recall_gate_passed
        and forbidden_gate_passed
        and boundary_gate_passed
        and request_error_gate_passed
        and all_cases_gate_passed
    )
    summary_failure_reasons: list[str] = []
    if not recall_gate_passed:
        summary_failure_reasons.append("summary_recall_at_5")
    if not forbidden_gate_passed:
        summary_failure_reasons.append("forbidden_hit_rate")
    if not boundary_gate_passed:
        summary_failure_reasons.append("solution_boundary_violation_rate")
    if not request_error_gate_passed:
        summary_failure_reasons.append("request_error_count")
    if not all_cases_gate_passed:
        summary_failure_reasons.append("all_cases_pass_blocking_gate")
    return {
        "recall_at_5_gate_required_value": recall_required,
        "actual_recall_at_5": summary["recall_at_5"],
        "recall_gate_passed": recall_gate_passed,
        "forbidden_gate_passed": forbidden_gate_passed,
        "boundary_gate_passed": boundary_gate_passed,
        "request_error_gate_passed": request_error_gate_passed,
        "all_cases_gate_passed": all_cases_gate_passed,
        "all_gates_passed": all_gates_passed,
        "summary_failure_reasons": summary_failure_reasons,
    }


def _build_unresolved_recall_cases(diagnosis_payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    outputs: dict[str, list[dict[str, Any]]] = {}
    unresolved_causes = {"not_in_top_20", "lexical_term_mismatch", "vector_semantic_mismatch"}
    for method_id, items in diagnosis_payload["per_method_case_diagnostics"].items():
        outputs[method_id] = [
            {
                "case_id": item["case_id"],
                "source_case_id": item["source_case_id"],
                "recall_at_20": item["recall_at_20"],
                "missing_item_ids": [
                    missing["item_id"] for missing in item["missing_items"] if missing["cause"] in unresolved_causes
                ],
                "causes": sorted({missing["cause"] for missing in item["missing_items"] if missing["cause"] in unresolved_causes}),
            }
            for item in items
            if any(missing["cause"] in unresolved_causes for missing in item["missing_items"])
        ]
    return outputs


def _build_unresolved_boundary_cases(best_runtime_safe_strategy: dict[str, Any]) -> list[str]:
    return [
        item["case_id"]
        for item in best_runtime_safe_strategy["case_results"]
        if item["solution_boundary_violation"]
    ]


def _document_diversity_supported(matrix_results: list[dict[str, Any]]) -> bool:
    indexed = {
        (
            entry["method_id"],
            entry["strategy_id"],
            entry["pool_size"],
            entry["rerank_mode"],
            entry["diversity_mode"],
            entry["oracle_only"],
        ): entry
        for entry in matrix_results
    }
    for entry in matrix_results:
        if entry["oracle_only"] or entry["diversity_mode"] == "no_diversity":
            continue
        baseline = indexed.get(
            (
                entry["method_id"],
                entry["strategy_id"],
                entry["pool_size"],
                entry["rerank_mode"],
                "no_diversity",
                entry["oracle_only"],
            )
        )
        if baseline is None:
            continue
        if _entry_rank_key(entry) > _entry_rank_key(baseline):
            return True
    return False


def _select_best_entry(entries: list[dict[str, Any]]) -> dict[str, Any]:
    if not entries:
        raise ValueError("Expected at least one counterfactual entry.")
    return sorted(entries, key=_entry_rank_key, reverse=True)[0]


def _entry_rank_key(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        1 if entry["eligible_for_rag"] else 0,
        float(entry["recall_at_5"]),
        -float(entry["solution_boundary_violation_rate"]),
        -len(entry["failed_case_ids"]),
        int(entry["cases_with_zero_boundary"]),
        -int(entry["use_runtime_scope_fit_rerank"]),
        -DIVERSITY_ORDER[entry["diversity_mode"]],
        -entry["pool_size"],
        -STRATEGY_ORDER[entry["strategy_id"]],
    )


def _strategy_definitions() -> dict[str, dict[str, Any]]:
    return {
        "S0": {
            "oracle_only": False,
            "summary": "Current runtime eligibility: exclude explicit excluded-scope overlap and disjoint non-global candidates.",
        },
        "S1": {
            "oracle_only": False,
            "summary": "Strict applicable subset with global-policy exception.",
        },
        "S2": {
            "oracle_only": False,
            "summary": "Primary-solution match for solution-specific/multi-solution plus strict subset for cross-cutting requirements.",
        },
        "S3": {
            "oracle_only": False,
            "summary": "S1 plus runtime document type, industry, tag, and effective-date checks.",
        },
        "S4": {
            "oracle_only": True,
            "summary": "Evaluation-only oracle using benchmark gold boundary rules. For theoretical upper bound only.",
        },
    }


def _candidate_view_from_ranked_candidate(
    *,
    candidate: dict[str, Any],
    documents_by_id: dict[str, KnowledgeDocumentV2],
    chunks_by_id: dict[str, KnowledgeChunkV2],
) -> CandidateSourceView:
    document = documents_by_id[candidate["document_id"]]
    chunk = chunks_by_id.get(candidate.get("chunk_id")) if candidate.get("chunk_id") else None
    source = chunk or document
    return CandidateSourceView(
        candidate_id=candidate.get("chunk_id") or candidate["document_id"],
        document_id=candidate["document_id"],
        chunk_id=candidate.get("chunk_id"),
        document_type=candidate["document_type"],
        score=float(candidate["score"]),
        original_rank=int(candidate["rank"]),
        lexical_rank=candidate.get("lexical_rank"),
        vector_rank=candidate.get("vector_rank"),
        lexical_score=candidate.get("lexical_score"),
        vector_score=candidate.get("vector_score"),
        rrf_score=candidate.get("rrf_score"),
        scope_type=source.scope_type.value,
        primary_solution_id=source.primary_solution_id,
        applicable_solution_ids=tuple(source.applicable_solution_ids),
        excluded_solution_ids=tuple(source.excluded_solution_ids),
        industries=tuple(source.industries),
        tags=tuple(source.tags),
        effective_from=document.effective_from,
        effective_until=document.effective_until,
        citation_label=chunk.citation_label if chunk is not None else document.document_id,
        document=document,
        chunk=chunk,
    )


def _candidate_view_from_boundary_record(
    *,
    candidate: dict[str, Any],
    documents_by_id: dict[str, KnowledgeDocumentV2],
    chunks_by_id: dict[str, KnowledgeChunkV2],
) -> CandidateSourceView:
    document = documents_by_id[candidate["document_id"]]
    chunk = chunks_by_id.get(candidate.get("chunk_id")) if candidate.get("chunk_id") else None
    source = chunk or document
    return CandidateSourceView(
        candidate_id=candidate.get("chunk_id") or candidate["document_id"],
        document_id=candidate["document_id"],
        chunk_id=candidate.get("chunk_id"),
        document_type=candidate["document_type"],
        score=0.0,
        original_rank=int(candidate["candidate_rank"]),
        lexical_rank=None,
        vector_rank=None,
        lexical_score=None,
        vector_score=None,
        rrf_score=None,
        scope_type=candidate["scope_type"],
        primary_solution_id=source.primary_solution_id,
        applicable_solution_ids=tuple(candidate["applicable_solution_ids"]),
        excluded_solution_ids=tuple(candidate["excluded_solution_ids"]),
        industries=tuple(source.industries),
        tags=tuple(source.tags),
        effective_from=document.effective_from,
        effective_until=document.effective_until,
        citation_label=chunk.citation_label if chunk is not None else document.document_id,
        document=document,
        chunk=chunk,
    )


def _required_fields_for_strategy(strategy: str) -> list[str]:
    base = ["operational_solution_scope", "scope_type", "applicable_solution_ids", "excluded_solution_ids"]
    if strategy == "S2":
        return base + ["primary_solution_id"]
    if strategy == "S3":
        return base + [
            "allowed_document_types",
            "document_type",
            "industries",
            "tags",
            "effective_on",
            "effective_from",
            "effective_until",
        ]
    return base


def _fields_currently_present(*, required_fields: list[str], runtime_input: Any, source_view: CandidateSourceView) -> list[str]:
    output: list[str] = []
    for field_name in required_fields:
        if field_name == "operational_solution_scope" and runtime_input.operational_solution_scope:
            output.append(field_name)
        elif field_name == "scope_type" and source_view.scope_type:
            output.append(field_name)
        elif field_name == "applicable_solution_ids" and source_view.applicable_solution_ids:
            output.append(field_name)
        elif field_name == "excluded_solution_ids":
            output.append(field_name)
        elif field_name == "primary_solution_id" and source_view.primary_solution_id:
            output.append(field_name)
        elif field_name == "allowed_document_types" and runtime_input.allowed_document_types:
            output.append(field_name)
        elif field_name == "document_type" and source_view.document_type:
            output.append(field_name)
        elif field_name == "industries":
            output.append(field_name)
        elif field_name == "tags":
            output.append(field_name)
        elif field_name == "effective_on" and runtime_input.effective_on:
            output.append(field_name)
        elif field_name == "effective_from":
            output.append(field_name)
        elif field_name == "effective_until":
            output.append(field_name)
    return output


def _candidate_hits_gold(*, case: RetrievalEvaluationCaseV2, candidate_record: dict[str, Any]) -> bool:
    return _candidate_relevance_id_for_case(case=case, candidate={"document_id": candidate_record["document_id"], "chunk_id": candidate_record.get("chunk_id")}) in (
        set(case.evaluation_gold.expected_relevant_document_ids) | set(case.evaluation_gold.expected_relevant_chunk_ids)
    )


def _false_positive_risk(*, source_view: CandidateSourceView, would_filter_expected: bool) -> str:
    if would_filter_expected:
        return "high"
    if source_view.scope_type in {"multi_solution", "cross_cutting_requirement"}:
        return "medium"
    return "low"


def _counterfactual_debug_payload(
    *,
    method_id: str,
    query: str,
    selected_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    candidate_count = len(selected_candidates)
    payload: dict[str, Any] = {
        "raw_query_present": bool(query),
        "normalized_query_present": bool("".join(query.split())),
        "candidate_count": candidate_count,
        "retrieval_method": method_id,
        "operational_filter_excluded_all": False,
    }
    if method_id == "lexical_v1":
        payload["lexical_query_tokens"] = [token for token in query.split() if token]
    elif method_id == "vector_v1":
        payload["query_embedding_generated"] = True
        payload["embedding_dimension"] = 384
    elif method_id == "hybrid_v1":
        payload["lexical_candidate_count"] = candidate_count
        payload["vector_candidate_count"] = candidate_count
        payload["fused_candidate_count"] = candidate_count
    return payload


def _to_retrieval_candidate(
    *,
    method_id: str,
    candidate: dict[str, Any],
    source_view: CandidateSourceView,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        rank=int(candidate["rank"]),
        document_id=candidate["document_id"],
        chunk_id=candidate.get("chunk_id"),
        score=float(candidate["score"]),
        retrieval_method=RetrievalMethod(method_id),
        matched_terms=list(candidate.get("matched_terms", [])),
        metadata={},
        citation_label=source_view.citation_label,
        solution_ids=list(source_view.applicable_solution_ids),
    )


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
