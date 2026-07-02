from __future__ import annotations

import contextlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evaluation.retrieval.candidate_generation_v2 import (
    CANDIDATE_GENERATION_OUTPUT_PATH,
    CorpusBundle,
    ExperimentContext,
    _build_document_level_corpus,
    _candidate_recall_at,
    _deduplicate,
    _document_children,
    _evaluate_candidate_list,
    _expected_item_metadata,
    _expand_document_candidates_to_chunks,
    _find_candidate_rank,
    _load_experiment_context,
    _merge_hybrid_candidates,
    _render_document_retrieval_text,
    _render_enriched_chunk_text,
    _renumber_candidates,
    _sha256,
)
from evaluation.retrieval.contracts_v2 import evaluate_candidate_boundary_v2
from evaluation.retrieval.diagnostics_v2 import (
    _candidate_relevance_id_for_case,
    _network_guard,
    compute_formal_result_hashes,
    load_diagnostic_context,
    run_method_diagnostic,
)
from evaluation.retrieval.models import RetrievalCandidate, RetrievalMethod, RetrievalRunResult
from evaluation.retrieval.runner_v2 import (
    evaluate_retrieval_case_v2,
    make_runtime_input_v2,
    runtime_input_to_retriever_filters,
)
from evaluation.retrieval.storage import diff_json_objects, load_json_record, write_json_atomic
from knowledge_base import KnowledgeChunkV2, KnowledgeDocumentV2
from knowledge_base.retrieval.embeddings import (
    DEFAULT_EMBEDDING_REVISION,
    SentenceTransformerEmbeddingProvider,
    huggingface_offline_environment,
    resolve_local_model_snapshot,
)
from knowledge_base.retrieval.hybrid import HybridBaselineConfig
from knowledge_base.retrieval.lexical import LexicalBaselineConfig, WeightedBM25Retriever
from knowledge_base.retrieval.tokenizer import tokenize_lexical_text
from knowledge_base.retrieval.vector import ExactVectorRetriever, VectorBaselineConfig
from knowledge_base.models import KnowledgeChunk, KnowledgeDocument


SEPARABILITY_OUTPUT_PATH = Path("data/evaluation/retrieval/retrieval_v2_separability_analysis.json")
SEPARABILITY_DOC_PATH = Path("docs/31_Retrieval_V2_Runtime_Separability.md")
BENCHMARK_CONFIG_PATH = Path("data/evaluation/retrieval/retrieval_benchmark_config.v2.json")

METHOD_IDS = ("lexical_v1", "vector_v1", "hybrid_v1")
RUNTIME_RULE_IDS = ("R0", "R1", "R2", "R3", "R4", "R5")
FOCUS_CASE_IDS = ("RET2-015", "RET2-016")
MISSED_CASE_IDS = ("RET2-005", "RET2-010", "RET2-015", "RET2-016")
QUERY_VARIANT_IDS = ("Q0", "Q1", "Q2_scope", "Q2_document_types", "Q2_all", "Q3")
FIELD_VARIANT_IDS = ("F0", "F1", "F2", "F3", "F4")
COMBINED_VARIANTS = (
    ("R2", "Q0", "F1"),
    ("R3", "Q0", "F1"),
    ("R3", "Q1", "F1"),
    ("R3", "Q2_all", "F1"),
    ("R3", "Q3", "F1"),
    ("R3", "Q2_all", "F2"),
    ("R3", "Q2_all", "F3"),
    ("R3", "Q2_all", "F4"),
)
TOP_LEVEL_CHECK_DEPTHS = (5, 10, 20)
STOPWORDS = {
    "需要",
    "希望",
    "一个",
    "以及",
    "并且",
    "同时",
    "但是",
    "为了",
    "我们",
    "客户",
    "方案",
    "项目",
}


@dataclass(frozen=True)
class StrategyRunContext:
    query_variant_id: str
    field_variant_id: str
    queries: tuple[str, ...]
    candidates_by_method: dict[str, list[dict[str, Any]]]


def build_plan_payload() -> dict[str, Any]:
    benchmark_config = load_json_record(BENCHMARK_CONFIG_PATH)
    return {
        "mode": "plan",
        "analysis_version": "retrieval_v2_runtime_separability_v1",
        "diagnostic_only": True,
        "benchmark_version": benchmark_config["benchmark_version"],
        "methods": list(METHOD_IDS),
        "runtime_rules": list(RUNTIME_RULE_IDS),
        "query_variants": list(QUERY_VARIANT_IDS),
        "field_variants": list(FIELD_VARIANT_IDS),
        "combined_variants": [
            {"rule_id": rule_id, "query_variant_id": query_variant_id, "field_variant_id": field_variant_id}
            for rule_id, query_variant_id, field_variant_id in COMBINED_VARIANTS
        ],
        "focus_case_ids": list(FOCUS_CASE_IDS),
        "formal_result_hashes": compute_formal_result_hashes(),
        "candidate_generation_analysis_hash": _sha256(CANDIDATE_GENERATION_OUTPUT_PATH),
        "planned_outputs": {
            "json": str(SEPARABILITY_OUTPUT_PATH),
            "doc": str(SEPARABILITY_DOC_PATH),
        },
    }


def build_separability_payload() -> dict[str, Any]:
    context = _load_experiment_context()
    runner = SeparabilityExperimentRunner(context=context)

    runtime_filter_false_exclusion_analysis = runner.build_runtime_filter_false_exclusion_analysis()
    runtime_rule_matrix = runner.build_runtime_rule_matrix()
    ret2_015_separability = runner.build_case_separability("RET2-015")
    ret2_016_separability = runner.build_case_separability("RET2-016")
    query_strategy_results = runner.build_query_strategy_results()
    field_strategy_results = runner.build_field_strategy_results()
    combined_strategy_results = runner.build_combined_strategy_results()
    best_runtime_safe_strategy = _select_best_strategy(combined_strategy_results)
    unresolved_cases = sorted(
        {
            case_id
            for entry in combined_strategy_results
            for case_id in entry["unresolved_case_ids"]
        }
    )

    strict_false_exclusions = sum(
        item["incorrectly_filtered_relevant_candidates"]
        for item in runtime_filter_false_exclusion_analysis.values()
    )
    zero_false_exclusion_possible = any(
        entry["boundary_violation_rate"] == 0.0
        and entry["forbidden_hit_rate"] == 0.0
        and entry["false_positive_count"] == 0
        for entry in runtime_rule_matrix
        if not entry["oracle_only"]
    )
    runtime_contract_upgrade_required = not zero_false_exclusion_possible
    knowledge_metadata_upgrade_required = any(
        detail["classification"] == "knowledge_metadata_gap"
        for detail in (ret2_015_separability, ret2_016_separability)
    )
    benchmark_case_upgrade_required = any(
        detail["classification"] == "gold_semantic_overconstraint"
        for detail in (ret2_015_separability, ret2_016_separability)
    )
    deterministic_query_strategy_supported = any(
        entry["query_variant_id"] in {"Q1", "Q2_scope", "Q2_document_types", "Q2_all", "Q3"}
        and entry["candidate_recall_at_20"] > field_strategy_results["F0"]["best_method"]["candidate_recall_at_20"]
        for entry in combined_strategy_results
    )
    llm_query_rewrite_supported = not any(
        entry["candidate_recall_at_20"] == 1.0 and entry["boundary_violation_rate"] == 0.0
        for entry in combined_strategy_results
    )
    retriever_v2_ready_for_implementation = (
        best_runtime_safe_strategy["candidate_recall_at_20"] == 1.0
        and best_runtime_safe_strategy["boundary_violation_rate"] == 0.0
        and best_runtime_safe_strategy["forbidden_hit_rate"] == 0.0
    )

    if retriever_v2_ready_for_implementation:
        recommended_next_step = "implement_candidate_generation_v2"
    elif benchmark_case_upgrade_required:
        recommended_next_step = "version_benchmark_case_before_retriever_upgrade"
    elif knowledge_metadata_upgrade_required or runtime_contract_upgrade_required:
        recommended_next_step = "upgrade_runtime_or_knowledge_metadata_contracts_before_retriever_v2"
    elif deterministic_query_strategy_supported:
        recommended_next_step = "design_candidate_generation_v2_with_runtime_separable_query_and_field_strategy"
    else:
        recommended_next_step = "continue_non_llm_candidate_generation_diagnosis_before_query_rewrite"

    return {
        "analysis_version": "retrieval_v2_runtime_separability_v1",
        "diagnostic_only": True,
        "formal_result_hashes": compute_formal_result_hashes(),
        "candidate_generation_analysis_hash": _sha256(CANDIDATE_GENERATION_OUTPUT_PATH),
        "runtime_filter_false_exclusion_analysis": runtime_filter_false_exclusion_analysis,
        "runtime_rule_matrix": runtime_rule_matrix,
        "ret2_015_separability": ret2_015_separability,
        "ret2_016_separability": ret2_016_separability,
        "query_strategy_results": query_strategy_results,
        "field_strategy_results": field_strategy_results,
        "combined_strategy_results": combined_strategy_results,
        "best_runtime_safe_strategy": best_runtime_safe_strategy,
        "unresolved_cases": unresolved_cases,
        "retriever_v2_ready_for_implementation": retriever_v2_ready_for_implementation,
        "runtime_contract_upgrade_required": runtime_contract_upgrade_required,
        "knowledge_metadata_upgrade_required": knowledge_metadata_upgrade_required,
        "benchmark_case_upgrade_required": benchmark_case_upgrade_required,
        "deterministic_query_strategy_supported": deterministic_query_strategy_supported,
        "llm_query_rewrite_supported": llm_query_rewrite_supported,
        "embedding_change_supported": False,
        "architecture_c_status": "blocked",
        "recommended_next_step": recommended_next_step,
        "limitations": [
            "This analysis is offline and deterministic only; it does not modify frozen v2 retriever configs or formal artifacts.",
            "Gold is used only for evaluation and oracle diagnosis, never for candidate generation, filtering, query construction, or ranking in non-oracle variants.",
            "Vector experiments reuse the frozen embedding model and strict offline snapshot loading.",
            "The benchmark remains a synthetic 16-case / 40-chunk diagnostic environment and is not an Architecture C runtime recommendation.",
        ],
    }


def render_separability_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Retrieval V2 Runtime Separability")
    lines.append("")
    lines.append("## Runtime可识别与可分离的区别")
    lines.append("")
    lines.append("- `24/24` 个违规候选可由 Runtime 字段识别，并不自动意味着 Relevant Gold 可以零误伤保留。")
    lines.append(f"- runtime_contract_upgrade_required: {str(payload['runtime_contract_upgrade_required']).lower()}")
    lines.append("")
    lines.append("## Strict Filter误伤分析")
    lines.append("")
    for rule_id, summary in payload["runtime_filter_false_exclusion_analysis"].items():
        lines.append(
            f"- {rule_id}: total_filtered={summary['total_filtered_candidates']}, "
            f"correctly_filtered_boundary={summary['correctly_filtered_boundary_candidates']}, "
            f"incorrectly_filtered_relevant={summary['incorrectly_filtered_relevant_candidates']}, "
            f"retention={summary['relevant_candidate_retention_rate']}, "
            f"boundary_removal={summary['boundary_candidate_removal_rate']}"
        )
    lines.append("")
    lines.append("## 通用Runtime规则R0-R5")
    lines.append("")
    for entry in payload["runtime_rule_matrix"]:
        lines.append(
            f"- {entry['rule_id']} / {entry['method_id']}: recall@20={entry['candidate_recall_at_20']}, "
            f"boundary={entry['boundary_violation_rate']}, forbidden={entry['forbidden_hit_rate']}, "
            f"false_positive={entry['false_positive_count']}, false_negative={entry['false_negative_count']}"
        )
    lines.append("")
    for case_key in ("ret2_015_separability", "ret2_016_separability"):
        detail = payload[case_key]
        lines.append(f"## {detail['case_id']}语义可分离性")
        lines.append("")
        lines.append(f"- classification: {detail['classification']}")
        lines.append(f"- expected_ranks_by_method: {detail['expected_ranks_by_method']}")
        lines.append(f"- top_non_gold_candidate_ids: {detail['top_non_gold_candidate_ids']}")
        lines.append("")
    lines.append("## Query Clause Decomposition结果")
    lines.append("")
    for strategy_id, details in payload["query_strategy_results"].items():
        lines.append(
            f"- {strategy_id}: best_method={details['best_method']['method_id']}, "
            f"recall@20={details['best_method']['candidate_recall_at_20']}, "
            f"boundary={details['best_method']['boundary_violation_rate']}"
        )
    lines.append("")
    lines.append("## Runtime Context Augmentation结果")
    lines.append("")
    for strategy_id in ("Q2_scope", "Q2_document_types", "Q2_all", "Q3"):
        details = payload["query_strategy_results"][strategy_id]
        lines.append(
            f"- {strategy_id}: best_method={details['best_method']['method_id']}, "
            f"RET2-015_rank={details['ret2_rank_changes']['RET2-015']}, "
            f"RET2-016_rank={details['ret2_rank_changes']['RET2-016']}"
        )
    lines.append("")
    lines.append("## Field-aware检索结果")
    lines.append("")
    for strategy_id, details in payload["field_strategy_results"].items():
        lines.append(
            f"- {strategy_id}: best_method={details['best_method']['method_id']}, "
            f"recall@20={details['best_method']['candidate_recall_at_20']}, "
            f"boundary={details['best_method']['boundary_violation_rate']}"
        )
    lines.append("")
    lines.append("## Parent-child / Sibling扩展结果")
    lines.append("")
    parent_child = payload["field_strategy_results"]["F3"]
    lines.append(
        f"- F3 best_method={parent_child['best_method']['method_id']}, "
        f"RET2-015_rank={parent_child['ret2_rank_changes']['RET2-015']}, "
        f"RET2-016_rank={parent_child['ret2_rank_changes']['RET2-016']}"
    )
    lines.append("")
    lines.append("## Document-type Partition结果")
    lines.append("")
    partition = payload["field_strategy_results"]["F4"]
    lines.append(
        f"- F4 best_method={partition['best_method']['method_id']}, "
        f"recall@20={partition['best_method']['candidate_recall_at_20']}, "
        f"boundary={partition['best_method']['boundary_violation_rate']}"
    )
    lines.append("")
    lines.append("## 最佳通用组合")
    lines.append("")
    best = payload["best_runtime_safe_strategy"]
    lines.append(
        f"- {best['rule_id']} + {best['query_variant_id']} + {best['field_variant_id']} / {best['method_id']}: "
        f"recall@20={best['candidate_recall_at_20']}, boundary={best['boundary_violation_rate']}, forbidden={best['forbidden_hit_rate']}"
    )
    lines.append("")
    lines.append("## 是否达到Candidate Recall@20=1")
    lines.append("")
    lines.append(f"- retriever_v2_ready_for_implementation: {str(payload['retriever_v2_ready_for_implementation']).lower()}")
    lines.append("")
    lines.append("## 是否Boundary=0")
    lines.append("")
    lines.append(f"- best boundary rate: {best['boundary_violation_rate']}")
    lines.append("")
    lines.append("## 是否需要Metadata v2.1")
    lines.append("")
    lines.append(f"- knowledge_metadata_upgrade_required: {str(payload['knowledge_metadata_upgrade_required']).lower()}")
    lines.append("")
    lines.append("## 是否需要Benchmark Case v2.1")
    lines.append("")
    lines.append(f"- benchmark_case_upgrade_required: {str(payload['benchmark_case_upgrade_required']).lower()}")
    lines.append("")
    lines.append("## 是否支持确定性Query策略")
    lines.append("")
    lines.append(f"- deterministic_query_strategy_supported: {str(payload['deterministic_query_strategy_supported']).lower()}")
    lines.append("")
    lines.append("## 是否支持LLM Query Rewrite")
    lines.append("")
    lines.append(f"- llm_query_rewrite_supported: {str(payload['llm_query_rewrite_supported']).lower()}")
    lines.append("")
    lines.append("## 为什么仍不更换Embedding")
    lines.append("")
    lines.append("- 当前没有跨 case 证据表明 embedding model / revision 是主瓶颈。")
    lines.append("- 当前主要矛盾仍是 runtime separability、query under-specification 和 field representation gap。")
    lines.append("")
    lines.append("## Retriever v2是否可实现")
    lines.append("")
    lines.append(f"- recommended_next_step: {payload['recommended_next_step']}")
    lines.append("")
    lines.append("## Architecture C状态")
    lines.append("")
    lines.append(f"- architecture_c_status: {payload['architecture_c_status']}")
    lines.append("")
    return "\n".join(lines)


def write_separability_outputs(payload: dict[str, Any]) -> None:
    write_json_atomic(SEPARABILITY_OUTPUT_PATH, payload)
    SEPARABILITY_DOC_PATH.write_text(render_separability_markdown(payload), encoding="utf-8")


def check_separability_outputs() -> tuple[bool, list[str]]:
    recomputed = build_separability_payload()
    differences: list[str] = []

    if not SEPARABILITY_OUTPUT_PATH.exists():
        differences.append(f"Missing tracked JSON output: {SEPARABILITY_OUTPUT_PATH}")
    else:
        tracked_json = load_json_record(SEPARABILITY_OUTPUT_PATH)
        differences.extend(diff_json_objects(tracked_json, recomputed))

    rendered_markdown = render_separability_markdown(recomputed)
    if not SEPARABILITY_DOC_PATH.exists():
        differences.append(f"Missing tracked Markdown output: {SEPARABILITY_DOC_PATH}")
    else:
        tracked_markdown = SEPARABILITY_DOC_PATH.read_text(encoding="utf-8")
        if tracked_markdown != rendered_markdown:
            differences.append(f"Markdown output drifted: {SEPARABILITY_DOC_PATH}")

    return (not differences, differences)


class SeparabilityExperimentRunner:
    def __init__(self, *, context: ExperimentContext) -> None:
        self._context = context
        self._vector_provider: SentenceTransformerEmbeddingProvider | None = None
        self._candidate_cache: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        self._retriever_cache: dict[tuple[str, str], Any] = {}
        self._single_query_cache: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        diagnostic_context = load_diagnostic_context()
        self._diagnostic_runs = {
            method_id: run_method_diagnostic(context=diagnostic_context, method_id=method_id, top_k=20)
            for method_id in METHOD_IDS
        }
        self._field_bundles = self._build_field_bundles()
        self._document_level_bundle = self._build_document_level_bundle()

    def build_runtime_filter_false_exclusion_analysis(self) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        for rule_id in ("S1", "S2", "S3"):
            filtered_details: list[dict[str, Any]] = []
            total_filtered = 0
            correctly_filtered_boundary = 0
            incorrectly_filtered_relevant = 0
            total_relevant_in_pool = 0
            total_boundary_in_pool = 0
            retained_relevant = 0
            removed_boundary = 0

            mapped_rule = {"S1": "R1", "S2": "R2", "S3": "R3"}[rule_id]

            for method_id in METHOD_IDS:
                for case in self._context.cases:
                    current_candidates = self._get_strategy_candidates(
                        case=case,
                        method_id=method_id,
                        query_variant_id="Q0",
                        field_variant_id="F0",
                    )[:20]
                    runtime_input = self._context.runtime_inputs[case.retrieval_case_id]
                    for candidate in current_candidates:
                        view = self._candidate_view(candidate)
                        boundary_decision = evaluate_candidate_boundary_v2(case=case, document=view["document"], chunk=view["chunk"])
                        relevant = _candidate_relevance_id_for_case(case=case, candidate=candidate) in _relevant_ids(case)
                        if relevant:
                            total_relevant_in_pool += 1
                        if not boundary_decision.candidate_allowed:
                            total_boundary_in_pool += 1
                        decision = _evaluate_runtime_rule(
                            rule_id=mapped_rule,
                            case=case,
                            runtime_input=runtime_input,
                            document=view["document"],
                            chunk=view["chunk"],
                        )
                        if decision["allowed"]:
                            if relevant:
                                retained_relevant += 1
                            continue
                        total_filtered += 1
                        category = (
                            "relevant_gold_candidate"
                            if relevant
                            else "boundary_violating_candidate"
                            if not boundary_decision.candidate_allowed
                            else "irrelevant_safe_candidate"
                        )
                        if category == "boundary_violating_candidate":
                            correctly_filtered_boundary += 1
                            removed_boundary += 1
                        if category == "relevant_gold_candidate":
                            incorrectly_filtered_relevant += 1
                        filtered_details.append(
                            {
                                "case_id": case.retrieval_case_id,
                                "method_id": method_id,
                                "document_id": candidate["document_id"],
                                "chunk_id": candidate.get("chunk_id"),
                                "scope_type": view["chunk"].scope_type.value if view["chunk"] is not None else view["document"].scope_type.value,
                                "primary_solution_id": view["candidate"].primary_solution_id,
                                "applicable_solution_ids": list(view["candidate"].applicable_solution_ids),
                                "excluded_solution_ids": list(view["candidate"].excluded_solution_ids),
                                "operational_solution_scope": list(runtime_input.operational_solution_scope),
                                "allowed_document_types": list(runtime_input.allowed_document_types),
                                "industries": list(runtime_input.industries),
                                "tags": list(runtime_input.tags),
                                "effective_on": runtime_input.effective_on.isoformat(),
                                "filtered_category": category,
                                "filtered_by_rule": list(decision["reasons"]),
                                "why_evaluation_relevant_and_boundary_safe": (
                                    "Expected gold item and evaluate_candidate_boundary_v2 returns candidate_allowed=true."
                                    if relevant and boundary_decision.candidate_allowed
                                    else None
                                ),
                                "distinguishable_with_current_runtime_fields": category != "relevant_gold_candidate",
                            }
                        )

            output[rule_id] = {
                "filtered_candidates": filtered_details,
                "total_filtered_candidates": total_filtered,
                "correctly_filtered_boundary_candidates": correctly_filtered_boundary,
                "incorrectly_filtered_relevant_candidates": incorrectly_filtered_relevant,
                "filter_precision": (correctly_filtered_boundary / total_filtered) if total_filtered else 1.0,
                "relevant_candidate_retention_rate": (retained_relevant / total_relevant_in_pool) if total_relevant_in_pool else 1.0,
                "boundary_candidate_removal_rate": (removed_boundary / total_boundary_in_pool) if total_boundary_in_pool else 1.0,
                "zero_false_exclusion_separable": incorrectly_filtered_relevant == 0,
                "runtime_identifiable_implies_separable": incorrectly_filtered_relevant == 0,
            }
        return output

    def build_runtime_rule_matrix(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for rule_id in RUNTIME_RULE_IDS:
            for method_id in METHOD_IDS:
                case_results: list[dict[str, Any]] = []
                retained = 0
                relevant_total = 0
                boundary_total = 0
                boundary_removed = 0
                false_positive = 0
                false_negative = 0
                for case in self._context.cases:
                    candidates = self._apply_runtime_rule(
                        case=case,
                        method_id=method_id,
                        rule_id=rule_id,
                        candidates=self._get_strategy_candidates(
                            case=case,
                            method_id=method_id,
                            query_variant_id="Q0",
                            field_variant_id="F0",
                        ),
                    )
                    for current in self._get_strategy_candidates(case=case, method_id=method_id, query_variant_id="Q0", field_variant_id="F0")[:20]:
                        view = self._candidate_view(current)
                        boundary = evaluate_candidate_boundary_v2(case=case, document=view["document"], chunk=view["chunk"])
                        relevant = _candidate_relevance_id_for_case(case=case, candidate=current) in _relevant_ids(case)
                        allowed = _evaluate_runtime_rule(rule_id=rule_id, case=case, runtime_input=self._context.runtime_inputs[case.retrieval_case_id], document=view["document"], chunk=view["chunk"])["allowed"]
                        if relevant:
                            relevant_total += 1
                            if allowed:
                                retained += 1
                            else:
                                false_positive += 1
                        if not boundary.candidate_allowed:
                            boundary_total += 1
                            if not allowed:
                                boundary_removed += 1
                            else:
                                false_negative += 1
                    result = _evaluate_candidate_list(
                        case=case,
                        candidates=candidates,
                        documents_by_id=self._context.documents_by_id,
                        chunks_by_id=self._context.chunks_by_id,
                    )
                    case_results.append({"case_id": case.retrieval_case_id, **result})
                summary = _summarize_case_results(case_results)
                entries.append(
                    {
                        "rule_id": rule_id,
                        "method_id": method_id,
                        "oracle_only": rule_id == "R5",
                        **summary,
                        "relevant_candidate_retention_rate": (retained / relevant_total) if relevant_total else 1.0,
                        "boundary_candidate_removal_rate": (boundary_removed / boundary_total) if boundary_total else 1.0,
                        "false_positive_count": false_positive,
                        "false_negative_count": false_negative,
                    }
                )
        return entries

    def build_case_separability(self, case_id: str) -> dict[str, Any]:
        case = next(item for item in self._context.cases if item.retrieval_case_id == case_id)
        runtime_input = self._context.runtime_inputs[case_id]
        expected_ids = sorted(_relevant_ids(case))
        expected_ranks: dict[str, dict[str, int | None]] = {}
        top_non_gold_candidate_ids: dict[str, list[str]] = {}
        query_tokens = tokenize_lexical_text(case.query)
        expected_overlaps: list[dict[str, Any]] = []

        for method_id in METHOD_IDS:
            candidates = self._get_strategy_candidates(case=case, method_id=method_id, query_variant_id="Q0", field_variant_id="F0")
            top_non_gold_candidate_ids[method_id] = [
                candidate.get("chunk_id") or candidate["document_id"]
                for candidate in candidates[:5]
                if _candidate_relevance_id_for_case(case=case, candidate=candidate) not in expected_ids
            ]
            expected_ranks[method_id] = {}
            for expected_id in expected_ids:
                expected_ranks[method_id][expected_id] = _find_candidate_rank(candidates, case=case, item_id=expected_id)

        for expected_id in expected_ids:
            meta = _expected_item_metadata(
                expected_id=expected_id,
                documents_by_id=self._context.documents_by_id,
                chunks_by_id=self._context.chunks_by_id,
            )
            expected_overlaps.append(
                {
                    "expected_item_id": expected_id,
                    "query_overlap_with_title": sorted(set(query_tokens) & set(tokenize_lexical_text(meta["document_title"]))),
                    "query_overlap_with_summary": sorted(set(query_tokens) & set(tokenize_lexical_text(meta["document_summary"]))),
                    "query_overlap_with_content": sorted(set(query_tokens) & set(tokenize_lexical_text(meta["chunk_content"]))),
                }
            )

        classification = _classify_case_separability(
            case=case,
            expected_overlaps=expected_overlaps,
            expected_ranks=expected_ranks,
            runtime_input=runtime_input,
        )
        return {
            "case_id": case.retrieval_case_id,
            "source_case_id": case.source_case_id,
            "query": case.query,
            "runtime_context": {
                "operational_solution_scope": list(runtime_input.operational_solution_scope),
                "allowed_document_types": list(runtime_input.allowed_document_types),
                "industries": list(runtime_input.industries),
                "tags": list(runtime_input.tags),
            },
            "expected_document_ids": list(case.evaluation_gold.expected_relevant_document_ids),
            "expected_chunk_ids": list(case.evaluation_gold.expected_relevant_chunk_ids),
            "expected_ranks_by_method": expected_ranks,
            "top_non_gold_candidate_ids": top_non_gold_candidate_ids,
            "expected_overlap_analysis": expected_overlaps,
            "classification": classification,
        }

    def build_query_strategy_results(self) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        for query_variant_id in QUERY_VARIANT_IDS:
            method_entries: list[dict[str, Any]] = []
            ret2_rank_changes: dict[str, dict[str, int | None]] = {}
            for method_id in METHOD_IDS:
                case_results = []
                for case in self._context.cases:
                    candidates = self._get_strategy_candidates(
                        case=case,
                        method_id=method_id,
                        query_variant_id=query_variant_id,
                        field_variant_id="F0",
                    )
                    filtered = self._apply_runtime_rule(case=case, method_id=method_id, rule_id="R3", candidates=candidates)
                    result = _evaluate_candidate_list(
                        case=case,
                        candidates=filtered,
                        documents_by_id=self._context.documents_by_id,
                        chunks_by_id=self._context.chunks_by_id,
                    )
                    case_results.append({"case_id": case.retrieval_case_id, **result})
                summary = _summarize_case_results(case_results)
                method_entries.append({"method_id": method_id, **summary})
                ret2_rank_changes[method_id] = {
                    case_id: _find_candidate_rank(
                        self._apply_runtime_rule(
                            case=next(item for item in self._context.cases if item.retrieval_case_id == case_id),
                            method_id=method_id,
                            rule_id="R3",
                            candidates=self._get_strategy_candidates(
                                case=next(item for item in self._context.cases if item.retrieval_case_id == case_id),
                                method_id=method_id,
                                query_variant_id=query_variant_id,
                                field_variant_id="F0",
                            ),
                        ),
                        case=next(item for item in self._context.cases if item.retrieval_case_id == case_id),
                        item_id=_focus_expected_id(next(item for item in self._context.cases if item.retrieval_case_id == case_id)),
                    )
                    for case_id in FOCUS_CASE_IDS
                }
            best = _best_method_entry(method_entries)
            output[query_variant_id] = {
                "methods": method_entries,
                "best_method": best,
                "ret2_rank_changes": {
                    case_id: {method_id: ranks[case_id] for method_id, ranks in ret2_rank_changes.items()}
                    for case_id in FOCUS_CASE_IDS
                },
            }
        return output

    def build_field_strategy_results(self) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        for field_variant_id in FIELD_VARIANT_IDS:
            method_entries: list[dict[str, Any]] = []
            ret2_rank_changes: dict[str, dict[str, int | None]] = {}
            for method_id in METHOD_IDS:
                case_results = []
                for case in self._context.cases:
                    candidates = self._get_strategy_candidates(
                        case=case,
                        method_id=method_id,
                        query_variant_id="Q0",
                        field_variant_id=field_variant_id,
                    )
                    filtered = self._apply_runtime_rule(case=case, method_id=method_id, rule_id="R3", candidates=candidates)
                    result = _evaluate_candidate_list(
                        case=case,
                        candidates=filtered,
                        documents_by_id=self._context.documents_by_id,
                        chunks_by_id=self._context.chunks_by_id,
                    )
                    case_results.append({"case_id": case.retrieval_case_id, **result})
                summary = _summarize_case_results(case_results)
                method_entries.append({"method_id": method_id, **summary})
                ret2_rank_changes[method_id] = {
                    case_id: _find_candidate_rank(
                        self._apply_runtime_rule(
                            case=next(item for item in self._context.cases if item.retrieval_case_id == case_id),
                            method_id=method_id,
                            rule_id="R3",
                            candidates=self._get_strategy_candidates(
                                case=next(item for item in self._context.cases if item.retrieval_case_id == case_id),
                                method_id=method_id,
                                query_variant_id="Q0",
                                field_variant_id=field_variant_id,
                            ),
                        ),
                        case=next(item for item in self._context.cases if item.retrieval_case_id == case_id),
                        item_id=_focus_expected_id(next(item for item in self._context.cases if item.retrieval_case_id == case_id)),
                    )
                    for case_id in FOCUS_CASE_IDS
                }
            best = _best_method_entry(method_entries)
            output[field_variant_id] = {
                "methods": method_entries,
                "best_method": best,
                "ret2_rank_changes": {
                    case_id: {method_id: ranks[case_id] for method_id, ranks in ret2_rank_changes.items()}
                    for case_id in FOCUS_CASE_IDS
                },
            }
        return output

    def build_combined_strategy_results(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for rule_id, query_variant_id, field_variant_id in COMBINED_VARIANTS:
            for method_id in METHOD_IDS:
                case_results = []
                for case in self._context.cases:
                    candidates = self._get_strategy_candidates(
                        case=case,
                        method_id=method_id,
                        query_variant_id=query_variant_id,
                        field_variant_id=field_variant_id,
                    )
                    filtered = self._apply_runtime_rule(case=case, method_id=method_id, rule_id=rule_id, candidates=candidates)
                    result = _evaluate_candidate_list(
                        case=case,
                        candidates=filtered,
                        documents_by_id=self._context.documents_by_id,
                        chunks_by_id=self._context.chunks_by_id,
                    )
                    case_results.append({"case_id": case.retrieval_case_id, **result})
                summary = _summarize_case_results(case_results)
                results.append(
                    {
                        "rule_id": rule_id,
                        "query_variant_id": query_variant_id,
                        "field_variant_id": field_variant_id,
                        "method_id": method_id,
                        **summary,
                    }
                )
        return results

    def _build_field_bundles(self) -> dict[str, CorpusBundle]:
        docs = self._context.documents_v2
        chunks = self._context.chunks_v2
        docs_by_id = {document.document_id: document for document in docs}

        bundles: dict[str, CorpusBundle] = {"F0": self._context.enriched_chunk_bundle}
        for field_name in ("title", "summary", "section", "content"):
            new_chunks: list[KnowledgeChunkV2] = []
            for chunk in chunks:
                document = docs_by_id[chunk.document_id]
                section_title = ""
                if isinstance(chunk.metadata, dict):
                    section_title = str(chunk.metadata.get("section_title", "") or "")
                if field_name == "title":
                    content = document.title
                elif field_name == "summary":
                    content = document.summary
                elif field_name == "section":
                    content = section_title or chunk.citation_label
                else:
                    content = chunk.content
                payload = chunk.model_dump(mode="json")
                payload["content"] = content
                new_chunks.append(KnowledgeChunkV2.model_validate(payload))
            legacy_docs = self._context.current_chunk_bundle.legacy_documents
            from evaluation.retrieval.runner_v2 import project_v2_chunks_to_legacy_runtime_inputs

            legacy_chunks = project_v2_chunks_to_legacy_runtime_inputs(new_chunks)
            bundles[f"field:{field_name}"] = CorpusBundle(
                documents_v2=docs,
                chunks_v2=new_chunks,
                legacy_documents=legacy_docs,
                legacy_chunks=legacy_chunks,
                document_children=_document_children(new_chunks),
            )
        return bundles

    def _get_strategy_candidates(
        self,
        *,
        case: Any,
        method_id: str,
        query_variant_id: str,
        field_variant_id: str,
    ) -> list[dict[str, Any]]:
        cache_key = (case.retrieval_case_id, method_id, query_variant_id, field_variant_id)
        if cache_key in self._candidate_cache:
            return self._candidate_cache[cache_key]

        queries = _queries_for_variant(case=case, runtime_input=self._context.runtime_inputs[case.retrieval_case_id], query_variant_id=query_variant_id)
        if field_variant_id == "F0":
            candidates = self._retrieve_with_bundle_queries(
                case=case,
                method_id=method_id,
                bundle=self._context.enriched_chunk_bundle,
                bundle_key="bundle:enriched",
                queries=queries,
            )
        elif field_variant_id == "F1":
            candidates = self._retrieve_independent_field_candidates(case=case, method_id=method_id, queries=queries)
        elif field_variant_id == "F2":
            candidates = self._retrieve_max_field_candidates(case=case, method_id=method_id, queries=queries)
        elif field_variant_id == "F3":
            candidates = self._retrieve_parent_child_candidates(case=case, method_id=method_id, queries=queries)
        elif field_variant_id == "F4":
            candidates = self._retrieve_partitioned_by_doc_type(case=case, method_id=method_id, queries=queries)
        else:
            raise ValueError(f"Unsupported field_variant_id: {field_variant_id}")

        self._candidate_cache[cache_key] = candidates
        return candidates

    def _retrieve_with_bundle_queries(
        self,
        *,
        case: Any,
        method_id: str,
        bundle: CorpusBundle,
        bundle_key: str,
        queries: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        query_runs = [
            self._retrieve_single_query(
                case=case,
                method_id=method_id,
                bundle=bundle,
                bundle_key=bundle_key,
                query_text=query_text,
                query_label=f"{method_id}:{query_text}",
            )
            for query_text in queries
        ]
        if len(query_runs) == 1:
            return query_runs[0]
        return _merge_multi_ranked_lists(query_runs)

    def _retrieve_single_query(
        self,
        *,
        case: Any,
        method_id: str,
        bundle: CorpusBundle,
        bundle_key: str,
        query_text: str,
        query_label: str,
    ) -> list[dict[str, Any]]:
        cache_key = (case.retrieval_case_id, method_id, bundle_key, query_text)
        if cache_key in self._single_query_cache:
            return [dict(item) for item in self._single_query_cache[cache_key]]

        runtime_input = self._context.runtime_inputs[case.retrieval_case_id]
        retriever_filters = runtime_input_to_retriever_filters(runtime_input)
        if method_id == "hybrid_v1":
            lexical = self._retrieve_single_query(
                case=case,
                method_id="lexical_v1",
                bundle=bundle,
                bundle_key=f"{bundle_key}:lexical",
                query_text=query_text,
                query_label=f"{query_label}:lexical",
            )
            vector = self._retrieve_single_query(
                case=case,
                method_id="vector_v1",
                bundle=bundle,
                bundle_key=f"{bundle_key}:vector",
                query_text=query_text,
                query_label=f"{query_label}:vector",
            )
            return _merge_hybrid_candidates(
                lexical_candidates=lexical,
                vector_candidates=vector,
                config=self._context.hybrid_config,
                source_label=query_label,
            )

        retriever = self._get_retriever(method_id=method_id, bundle=bundle, bundle_key=bundle_key)
        candidates = [
            candidate.model_dump(mode="json")
            for candidate in retriever.retrieve(
                query=query_text,
                filters=retriever_filters,
                top_k=max(1, len(bundle.legacy_chunks)),
            )
        ]
        for candidate in candidates:
            candidate["candidate_sources"] = [query_label]
        self._single_query_cache[cache_key] = [dict(item) for item in candidates]
        return candidates

    def _get_retriever(self, *, method_id: str, bundle: CorpusBundle, bundle_key: str) -> Any:
        cache_key = (method_id, bundle_key)
        if cache_key in self._retriever_cache:
            return self._retriever_cache[cache_key]

        if method_id == "lexical_v1":
            retriever = WeightedBM25Retriever(config=self._context.lexical_config)
            retriever.build_index(documents=bundle.legacy_documents, chunks=bundle.legacy_chunks)
        elif method_id == "vector_v1":
            retriever = ExactVectorRetriever(
                config=self._context.vector_config,
                embedding_provider=self._vector_provider_instance(),
                project_root=Path.cwd(),
            )
            retriever.build_index(
                documents=bundle.legacy_documents,
                chunks=bundle.legacy_chunks,
                knowledge_base_version=f"{self._context.knowledge_base_version}:{bundle_key}",
            )
        else:
            raise ValueError(f"Unsupported method_id for retriever cache: {method_id}")

        self._retriever_cache[cache_key] = retriever
        return retriever

    def _build_document_level_bundle(self) -> CorpusBundle:
        document_docs, document_chunks, document_children = _build_document_level_corpus(
            current_docs=self._context.documents_v2,
            current_chunks=self._context.chunks_v2,
        )
        from evaluation.retrieval.runner_v2 import (
            project_v2_chunks_to_legacy_runtime_inputs,
            project_v2_documents_to_legacy_runtime_inputs,
        )

        return CorpusBundle(
            documents_v2=document_docs,
            chunks_v2=document_chunks,
            legacy_documents=project_v2_documents_to_legacy_runtime_inputs(document_docs),
            legacy_chunks=project_v2_chunks_to_legacy_runtime_inputs(document_chunks),
            document_children=document_children,
        )

    def _retrieve_independent_field_candidates(
        self,
        *,
        case: Any,
        method_id: str,
        queries: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        ranked_lists: list[list[dict[str, Any]]] = []
        for field_name in ("title", "summary", "section", "content"):
            ranked_lists.append(
                self._retrieve_with_bundle_queries(
                    case=case,
                    method_id=method_id,
                    bundle=self._field_bundles[f"field:{field_name}"],
                    bundle_key=f"bundle:field:{field_name}",
                    queries=queries,
                )
            )
        return _merge_multi_ranked_lists(ranked_lists)

    def _retrieve_max_field_candidates(
        self,
        *,
        case: Any,
        method_id: str,
        queries: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        ranked_lists = [
            self._retrieve_with_bundle_queries(
                case=case,
                method_id=method_id,
                bundle=self._field_bundles[f"field:{field_name}"],
                bundle_key=f"bundle:field:{field_name}",
                queries=queries,
            )
            for field_name in ("title", "summary", "section", "content")
        ]
        merged: dict[str, dict[str, Any]] = {}
        for ranked in ranked_lists:
            for candidate in ranked:
                candidate_id = candidate.get("chunk_id") or candidate["document_id"]
                existing = merged.get(candidate_id)
                if existing is None or candidate["rank"] < existing["rank"]:
                    payload = dict(candidate)
                    payload.setdefault("candidate_sources", [])
                    merged[candidate_id] = payload
                merged[candidate_id]["candidate_sources"] = _deduplicate(
                    merged[candidate_id].get("candidate_sources", []) + list(candidate.get("candidate_sources", []))
                )
        ordered = sorted(
            merged.values(),
            key=lambda item: (item["rank"], item["document_id"], item.get("chunk_id") or ""),
        )
        return _renumber_candidates(ordered)

    def _retrieve_parent_child_candidates(
        self,
        *,
        case: Any,
        method_id: str,
        queries: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        doc_candidates = self._retrieve_with_bundle_queries(
            case=case,
            method_id=method_id,
            bundle=self._document_level_bundle,
            bundle_key="bundle:document_level",
            queries=queries,
        )
        child_rank_source = self._retrieve_with_bundle_queries(
            case=case,
            method_id=method_id,
            bundle=self._context.enriched_chunk_bundle,
            bundle_key="bundle:enriched",
            queries=queries,
        )
        expanded = _expand_document_candidates_to_chunks(
            document_candidates=doc_candidates,
            child_chunk_ids=self._document_level_bundle.document_children,
            child_rank_source=child_rank_source,
            chunks_by_id=self._context.chunks_by_id,
        )
        limited: list[dict[str, Any]] = []
        per_doc: Counter[str] = Counter()
        for candidate in expanded:
            if per_doc[candidate["document_id"]] >= 2:
                continue
            limited.append(candidate)
            per_doc[candidate["document_id"]] += 1
        return _renumber_candidates(limited)

    def _retrieve_partitioned_by_doc_type(
        self,
        *,
        case: Any,
        method_id: str,
        queries: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        allowed = tuple(case.runtime_context.allowed_document_types) or tuple(sorted({doc.document_type.value for doc in self._context.documents_v2}))
        ranked_lists: list[list[dict[str, Any]]] = []
        for document_type in allowed:
            docs = [doc for doc in self._context.documents_v2 if doc.document_type.value == document_type]
            doc_ids = {doc.document_id for doc in docs}
            chunks = [chunk for chunk in self._context.enriched_chunk_bundle.chunks_v2 if chunk.document_id in doc_ids]
            from evaluation.retrieval.runner_v2 import (
                project_v2_chunks_to_legacy_runtime_inputs,
                project_v2_documents_to_legacy_runtime_inputs,
            )
            bundle = CorpusBundle(
                documents_v2=docs,
                chunks_v2=chunks,
                legacy_documents=project_v2_documents_to_legacy_runtime_inputs(docs),
                legacy_chunks=project_v2_chunks_to_legacy_runtime_inputs(chunks),
                document_children=_document_children(chunks),
            )
            ranked_lists.append(
                self._retrieve_with_bundle_queries(
                    case=case,
                    method_id=method_id,
                    bundle=bundle,
                    bundle_key=f"bundle:doctype:{document_type}",
                    queries=queries,
                )
            )
        return _merge_multi_ranked_lists(ranked_lists)

    def _apply_runtime_rule(
        self,
        *,
        case: Any,
        method_id: str,
        rule_id: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        runtime_input = self._context.runtime_inputs[case.retrieval_case_id]
        annotated: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
        for candidate in candidates:
            view = self._candidate_view(candidate)
            decision = _evaluate_runtime_rule(
                rule_id=rule_id,
                case=case,
                runtime_input=runtime_input,
                document=view["document"],
                chunk=view["chunk"],
            )
            if decision["allowed"]:
                annotated.append((candidate, view, decision))
        if rule_id == "R4":
            annotated.sort(
                key=lambda item: (
                    item[2]["priority"],
                    item[0]["rank"],
                    item[0]["document_id"],
                    item[0].get("chunk_id") or "",
                )
            )
        else:
            annotated.sort(key=lambda item: (item[0]["rank"], item[0]["document_id"], item[0].get("chunk_id") or ""))
        return _renumber_candidates([dict(candidate) for candidate, _, _ in annotated])

    def _candidate_view(self, candidate: dict[str, Any]) -> dict[str, Any]:
        chunk = self._context.chunks_by_id.get(candidate["chunk_id"]) if candidate.get("chunk_id") else None
        document = self._context.documents_by_id[candidate["document_id"]]
        return {
            "document": document,
            "chunk": chunk,
            "candidate": chunk or document,
        }

    def _vector_provider_instance(self) -> SentenceTransformerEmbeddingProvider:
        if self._vector_provider is not None:
            return self._vector_provider
        with _network_guard(), huggingface_offline_environment():
            snapshot_path = resolve_local_model_snapshot(
                repo_id=self._context.vector_config.model_name_or_path,
                revision=self._context.vector_config.model_revision or DEFAULT_EMBEDDING_REVISION,
            )
            self._vector_provider = SentenceTransformerEmbeddingProvider(
                model_name_or_path=self._context.vector_config.model_name_or_path,
                local_snapshot_path=snapshot_path,
                batch_size=self._context.vector_config.batch_size,
                device=self._context.vector_config.device,
                normalize_embeddings=self._context.vector_config.normalize_embeddings,
                allow_model_download=False,
                query_prefix=self._context.vector_config.query_prefix,
                document_prefix=self._context.vector_config.document_prefix,
                expected_dimension=384,
                expected_revision=self._context.vector_config.model_revision,
            )
        return self._vector_provider


def _evaluate_runtime_rule(
    *,
    rule_id: str,
    case: Any,
    runtime_input: Any,
    document: KnowledgeDocumentV2,
    chunk: KnowledgeChunkV2 | None,
) -> dict[str, Any]:
    candidate = chunk or document
    operational_scope = set(runtime_input.operational_solution_scope)
    applicable = set(candidate.applicable_solution_ids)
    excluded = set(candidate.excluded_solution_ids)
    reasons: list[str] = []

    if not document.is_active(as_of=runtime_input.effective_on):
        reasons.append("inactive_document")
    if runtime_input.allowed_document_types and document.document_type.value not in set(runtime_input.allowed_document_types):
        reasons.append("document_type_not_allowed")
    if runtime_input.industries and document.industries and set(document.industries).isdisjoint(set(runtime_input.industries)):
        reasons.append("industry_not_allowed")
    if runtime_input.tags and document.tags and set(document.tags).isdisjoint(set(runtime_input.tags)):
        reasons.append("tag_not_allowed")
    if excluded & operational_scope:
        reasons.append("candidate_excludes_operational_scope")

    priority = 99

    if rule_id == "R0":
        boundary = evaluate_candidate_boundary_v2(case=case, document=document, chunk=chunk)
        allowed = not reasons and boundary.candidate_allowed
        return {"allowed": allowed, "reasons": reasons + list(boundary.reasons), "priority": priority, "oracle_only": False}

    if rule_id == "R1":
        if candidate.scope_type.value != "global_policy" and not applicable.issubset(operational_scope):
            reasons.append("strict_subset_mismatch")
        if candidate.scope_type.value == "global_policy":
            priority = 4
        return {"allowed": not reasons, "reasons": reasons, "priority": priority, "oracle_only": False}

    if rule_id == "R2":
        if candidate.scope_type.value == "solution_specific":
            if candidate.primary_solution_id not in operational_scope:
                reasons.append("primary_solution_not_in_operational_scope")
            else:
                priority = 0
        elif candidate.scope_type.value == "multi_solution":
            if candidate.primary_solution_id not in operational_scope:
                reasons.append("primary_solution_not_in_operational_scope")
            else:
                priority = 2
        elif candidate.scope_type.value == "cross_cutting_requirement":
            if applicable.isdisjoint(operational_scope):
                reasons.append("cross_cutting_without_scope_overlap")
            else:
                priority = 3
        elif candidate.scope_type.value == "global_policy":
            priority = 4
        return {"allowed": not reasons, "reasons": reasons, "priority": priority, "oracle_only": False}

    if rule_id == "R3":
        channel: str | None = None
        if candidate.scope_type.value == "solution_specific" and candidate.primary_solution_id in operational_scope:
            channel = "solution_evidence"
            priority = 0
        elif candidate.scope_type.value in {"cross_cutting_requirement", "global_policy"} and applicable & operational_scope:
            channel = "cross_cutting_evidence"
            priority = 4 if candidate.scope_type.value == "global_policy" else 3
        elif candidate.scope_type.value == "global_policy":
            channel = "cross_cutting_evidence"
            priority = 4
        else:
            reasons.append("no_runtime_safe_channel")
        return {"allowed": not reasons, "reasons": reasons, "priority": priority, "channel": channel, "oracle_only": False}

    if rule_id == "R4":
        if candidate.scope_type.value == "solution_specific" and candidate.primary_solution_id in operational_scope:
            priority = 0
        elif candidate.scope_type.value == "multi_solution" and candidate.primary_solution_id in operational_scope:
            priority = 2
        elif candidate.scope_type.value == "cross_cutting_requirement" and applicable & operational_scope:
            priority = 3
        elif candidate.scope_type.value == "global_policy":
            priority = 4
        else:
            reasons.append("no_scope_specific_priority_match")
        return {"allowed": not reasons, "reasons": reasons, "priority": priority, "oracle_only": False}

    if rule_id == "R5":
        boundary = evaluate_candidate_boundary_v2(case=case, document=document, chunk=chunk)
        return {"allowed": not reasons and boundary.candidate_allowed, "reasons": reasons + list(boundary.reasons), "priority": priority, "oracle_only": True}

    raise ValueError(f"Unsupported rule_id: {rule_id}")


def _queries_for_variant(*, case: Any, runtime_input: Any, query_variant_id: str) -> tuple[str, ...]:
    if query_variant_id == "Q0":
        return (case.query,)
    if query_variant_id == "Q1":
        return _decompose_query(case.query)
    if query_variant_id == "Q2_scope":
        return (_augment_query_with_runtime(case.query, runtime_input=runtime_input, include_scope=True, include_document_types=False, include_taxonomy=False),)
    if query_variant_id == "Q2_document_types":
        return (_augment_query_with_runtime(case.query, runtime_input=runtime_input, include_scope=False, include_document_types=True, include_taxonomy=False),)
    if query_variant_id == "Q2_all":
        return (_augment_query_with_runtime(case.query, runtime_input=runtime_input, include_scope=True, include_document_types=True, include_taxonomy=True),)
    if query_variant_id == "Q3":
        augmented = _augment_query_with_runtime(case.query, runtime_input=runtime_input, include_scope=True, include_document_types=True, include_taxonomy=True)
        return _decompose_query(augmented)
    raise ValueError(f"Unsupported query_variant_id: {query_variant_id}")


def _decompose_query(query: str) -> tuple[str, ...]:
    parts = re.split(r"[，,；;。.!?]|以及|并且|同时|但是|需要|希望", query)
    clauses: list[str] = []
    for part in parts:
        cleaned = " ".join(part.strip().split())
        if len(cleaned) < 3:
            continue
        tokens = [token for token in tokenize_lexical_text(cleaned) if token not in STOPWORDS]
        if not tokens:
            continue
        candidate = " ".join(tokens)
        if len(candidate) >= 3:
            clauses.append(candidate)
    return tuple(_deduplicate(clauses or [query]))


def _augment_query_with_runtime(
    query: str,
    *,
    runtime_input: Any,
    include_scope: bool,
    include_document_types: bool,
    include_taxonomy: bool,
) -> str:
    parts = [query.strip()]
    if include_scope and runtime_input.operational_solution_scope:
        parts.append("solution_scope " + " ".join(runtime_input.operational_solution_scope))
    if include_document_types and runtime_input.allowed_document_types:
        parts.append("document_types " + " ".join(runtime_input.allowed_document_types))
    if include_taxonomy and runtime_input.industries:
        parts.append("industries " + " ".join(runtime_input.industries))
    if include_taxonomy and runtime_input.tags:
        parts.append("tags " + " ".join(runtime_input.tags))
    return " | ".join(part for part in parts if part)


def _merge_multi_ranked_lists(ranked_lists: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for list_index, ranked in enumerate(ranked_lists):
        for rank, candidate in enumerate(ranked, start=1):
            candidate_id = candidate.get("chunk_id") or candidate["document_id"]
            payload = merged.setdefault(candidate_id, dict(candidate))
            payload.setdefault("candidate_sources", [])
            payload["candidate_sources"] = _deduplicate(payload["candidate_sources"] + [f"list_{list_index}"])
            payload[f"rrf_rank_{list_index}"] = rank
    scored: list[dict[str, Any]] = []
    for item in merged.values():
        score = 0.0
        for key, value in item.items():
            if key.startswith("rrf_rank_") and isinstance(value, int):
                score += 1.0 / (60 + value)
        item["score"] = round(score, 8)
        scored.append(item)
    scored.sort(key=lambda item: (-item["score"], item["document_id"], item.get("chunk_id") or ""))
    return _renumber_candidates(scored)


def _relevant_ids(case: Any) -> set[str]:
    return set(case.evaluation_gold.expected_relevant_document_ids) | set(case.evaluation_gold.expected_relevant_chunk_ids)


def _focus_expected_id(case: Any) -> str:
    return sorted(_relevant_ids(case))[0]


def _summarize_case_results(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "candidate_recall_at_5": sum(item["candidate_recall_at_5"] for item in case_results) / len(case_results),
        "candidate_recall_at_10": sum(item["candidate_recall_at_10"] for item in case_results) / len(case_results),
        "candidate_recall_at_20": sum(item["candidate_recall_at_20"] for item in case_results) / len(case_results),
        "full_recall_case_count": sum(1 for item in case_results if item["candidate_recall_at_20"] == 1.0),
        "boundary_violation_rate": sum(1 for item in case_results if item["boundary_violation_at_20"]) / len(case_results),
        "forbidden_hit_rate": sum(1 for item in case_results if item["forbidden_hit_at_20"]) / len(case_results),
        "unresolved_case_ids": sorted(item["case_id"] for item in case_results if item["candidate_recall_at_20"] < 1.0),
    }


def _best_method_entry(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(
        entries,
        key=lambda item: (
            item["candidate_recall_at_20"],
            -item["boundary_violation_rate"],
            -item["forbidden_hit_rate"],
            item["candidate_recall_at_5"],
            -len(item["unresolved_case_ids"]),
        ),
        reverse=True,
    )[0]


def _select_best_strategy(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(
        entries,
        key=lambda item: (
            item["candidate_recall_at_20"],
            -item["boundary_violation_rate"],
            -item["forbidden_hit_rate"],
            item["candidate_recall_at_5"],
            -len(item["unresolved_case_ids"]),
        ),
        reverse=True,
    )[0]


def _classify_case_separability(
    *,
    case: Any,
    expected_overlaps: list[dict[str, Any]],
    expected_ranks: dict[str, dict[str, int | None]],
    runtime_input: Any,
) -> str:
    if all(not item["query_overlap_with_content"] and not item["query_overlap_with_title"] and not item["query_overlap_with_summary"] for item in expected_overlaps):
        return "query_under_specified"
    if any(item["query_overlap_with_title"] or item["query_overlap_with_summary"] for item in expected_overlaps) and all(
        not item["query_overlap_with_content"] for item in expected_overlaps
    ):
        return "field_representation_gap"
    all_missing = all(
        all(rank is None for rank in method_expected_ranks.values())
        for method_expected_ranks in expected_ranks.values()
    )
    if runtime_input.operational_solution_scope and all_missing:
        return "runtime_context_not_used"
    if case.evaluation_gold.expected_relevant_document_ids and not case.query.strip():
        return "gold_semantic_overconstraint"
    return "unknown"
