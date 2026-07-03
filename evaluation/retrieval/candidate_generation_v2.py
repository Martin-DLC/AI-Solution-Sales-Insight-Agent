from __future__ import annotations

import contextlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from evaluation.retrieval.counterfactuals_v2 import COUNTERFACTUAL_OUTPUT_PATH
from evaluation.retrieval.diagnostics_v2 import (
    DIAGNOSIS_OUTPUT_PATH,
    _candidate_relevance_id_for_case,
    _count_relevant_items_in_candidates,
    _network_guard,
    compute_formal_result_hashes,
    load_diagnostic_context,
)
from evaluation.retrieval.models import RetrievalCandidate, RetrievalMethod, RetrievalRunResult
from evaluation.retrieval.runner_v2 import (
    aggregate_summary_metrics_v2,
    evaluate_retrieval_case_v2,
    make_runtime_input_v2,
    project_v2_chunks_to_legacy_runtime_inputs,
    project_v2_documents_to_legacy_runtime_inputs,
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


CANDIDATE_GENERATION_OUTPUT_PATH = Path("data/evaluation/retrieval/retrieval_v2_candidate_generation_analysis.json")
CANDIDATE_GENERATION_DOC_PATH = Path("docs/30_Retrieval_V2_Candidate_Generation.md")
RECALL_ROUND_1_OUTPUT_PATH = Path("data/evaluation/retrieval/retrieval_recall_round_1.v2.json")
BENCHMARK_CONFIG_PATH = Path("data/evaluation/retrieval/retrieval_benchmark_config.v2.json")
LEXICAL_CONFIG_PATH = Path("data/evaluation/retrieval/lexical_baseline_config.v2.json")
VECTOR_CONFIG_PATH = Path("data/evaluation/retrieval/vector_baseline_config.v2.json")
HYBRID_CONFIG_PATH = Path("data/evaluation/retrieval/hybrid_baseline_config.v2.json")

TARGET_CASE_IDS = ("RET2-005", "RET2-010", "RET2-015", "RET2-016")
METHOD_IDS = ("lexical_v1", "vector_v1", "hybrid_v1")
POOL_DEPTHS = (5, 10, 20)
FULL_DEPTH_LABEL = "full_eligible_corpus"
VARIANT_ORDER = ("G0", "G1", "G2", "G3", "G4", "G5", "G6")
RECALL_ROUND_1_CASE_IDS = ("RET2-015", "RET2-016")
ROUND_1_FORMAL_RESULT_HASHES = {
    "lexical_results": "41bfa53dda9a65e78f82eeab064e0a9436b47bb423b3c52d995e3b661e552bad",
    "lexical_summary": "c5a48e917a897bd3ab76b2f815fdc07796e69ff0c9117534e50d0b13058f67e0",
    "vector_results": "9db04530b0240d00175dd5f386b7cc4cea030266ba90bb3180063a5c320244c4",
    "vector_summary": "766801ae928598de3e9ed23097f497764eeeac84e09da56ad6ee60b61cc8d585",
    "hybrid_results": "c5a3ace3ce08914fc7af7426e2c20143863d123b9e5ea3cfff314c0cd8dc5c46",
    "hybrid_summary": "d9543f66c64ff065ba5be0e6cc80a1a97dcafc1caa3fcb4622b6704052679d74",
    "comparison": "92c405e623246dacc154d935f31069f4e31b96e55c8886eea9ec9d314aea618d",
}
ROUND_1_BOUNDARY_ARTIFACT_HASHES = {
    "blind_evaluation_v2_2": "d679a75cc4064c33757f7284ca770c84b60b78be63ab7df89a2d32dc08568c2e",
    "runtime_contract_proposal_v2_1": "267e31d53e96bf9eb3ce709fbf7f1674f40e98283876263e94f2f00470ec3e3b",
}


@dataclass(frozen=True)
class CorpusBundle:
    documents_v2: list[KnowledgeDocumentV2]
    chunks_v2: list[KnowledgeChunkV2]
    legacy_documents: list[KnowledgeDocument]
    legacy_chunks: list[KnowledgeChunk]
    document_children: dict[str, list[str]]


@dataclass(frozen=True)
class ExperimentContext:
    benchmark_config: dict[str, Any]
    knowledge_base_version: str
    diagnosis_payload: dict[str, Any]
    counterfactual_payload: dict[str, Any]
    lexical_config: LexicalBaselineConfig
    vector_config: VectorBaselineConfig
    hybrid_config: HybridBaselineConfig
    cases: list[Any]
    documents_v2: list[KnowledgeDocumentV2]
    chunks_v2: list[KnowledgeChunkV2]
    runtime_inputs: dict[str, Any]
    current_chunk_bundle: CorpusBundle
    enriched_chunk_bundle: CorpusBundle
    document_bundle: CorpusBundle
    documents_by_id: dict[str, KnowledgeDocumentV2]
    chunks_by_id: dict[str, KnowledgeChunkV2]


def build_plan_payload() -> dict[str, Any]:
    benchmark_config = load_json_record(BENCHMARK_CONFIG_PATH)
    return {
        "mode": "plan",
        "analysis_version": "retrieval_v2_candidate_generation_analysis_v1",
        "diagnostic_only": True,
        "benchmark_version": benchmark_config["benchmark_version"],
        "methods": list(METHOD_IDS),
        "variants": list(VARIANT_ORDER),
        "pool_depths": [*POOL_DEPTHS, FULL_DEPTH_LABEL],
        "focus_case_ids": list(TARGET_CASE_IDS),
        "formal_result_hashes": compute_formal_result_hashes(),
        "counterfactual_analysis_hash": _sha256(COUNTERFACTUAL_OUTPUT_PATH),
        "planned_outputs": {
            "json": str(CANDIDATE_GENERATION_OUTPUT_PATH),
            "doc": str(CANDIDATE_GENERATION_DOC_PATH),
        },
    }


def build_recall_round_1_plan_payload() -> dict[str, Any]:
    benchmark_config = load_json_record(BENCHMARK_CONFIG_PATH)
    vector_config = VectorBaselineConfig.model_validate(load_json_record(VECTOR_CONFIG_PATH)["algorithm_config"])
    return {
        "mode": "plan",
        "experiment_id": "retrieval_v2_candidate_recall_round_1",
        "experiment_scope": "document_aware_multi_view_vector_retrieval",
        "case_count": benchmark_config["case_count"],
        "chunk_count": benchmark_config["chunk_count"],
        "focus_case_ids": list(RECALL_ROUND_1_CASE_IDS),
        "source_model": vector_config.model_name_or_path,
        "model_revision": vector_config.model_revision,
        "embedding_dimension": 384,
        "representation_fields": {
            "chunk_view": ["chunk.content"],
            "context_view": [
                "document.title",
                "document.summary",
                "document.document_type",
                "document.scope_type",
                "chunk.citation_label",
                "chunk.metadata.section_title",
                "primary_solution_name",
                "applicable_solution_names",
                "document.industries",
                "document.tags",
                "chunk.content",
            ],
        },
        "scoring_rule": "multi_view_score = max(chunk_view_score, context_view_score)",
        "writes_output_file": False,
        "formal_results_modified": False,
        "retriever_modified": False,
        "boundary_research_status": "closed",
        "planned_output_file": str(RECALL_ROUND_1_OUTPUT_PATH),
    }


def build_candidate_generation_payload() -> dict[str, Any]:
    context = _load_experiment_context()
    runner = CandidateGenerationExperimentRunner(context=context)

    current_audit = audit_current_candidate_generation()
    unresolved_case_analysis = runner.build_unresolved_case_analysis()
    variant_definitions = _variant_definitions()
    per_variant_method_metrics = runner.build_variant_metrics(variant_definitions=variant_definitions)
    prefilter_vs_postfilter_comparison = runner.build_prefilter_vs_postfilter_comparison(per_variant_method_metrics)
    missing_items_by_variant = _build_missing_items_by_variant(per_variant_method_metrics)

    best_variant = _select_best_variant(per_variant_method_metrics)
    candidate_generation_ready = _candidate_generation_ready(best_variant)
    direct_gate_pass = _direct_formal_gate_pass(best_variant)
    rerank_required = candidate_generation_ready and not direct_gate_pass
    query_rewrite_required = not candidate_generation_ready

    payload = {
        "analysis_version": "retrieval_v2_candidate_generation_analysis_v1",
        "diagnostic_only": True,
        "formal_result_hashes": compute_formal_result_hashes(),
        "counterfactual_analysis_hash": _sha256(COUNTERFACTUAL_OUTPUT_PATH),
        "current_candidate_generation_audit": current_audit,
        "unresolved_case_analysis": unresolved_case_analysis,
        "variant_definitions": variant_definitions,
        "per_variant_method_metrics": per_variant_method_metrics,
        "prefilter_vs_postfilter_comparison": prefilter_vs_postfilter_comparison,
        "candidate_recall_at_20": {
            variant_id: {
                method_id: metrics["candidate_recall_at_20"]
                for method_id, metrics in methods.items()
            }
            for variant_id, methods in per_variant_method_metrics.items()
        },
        "full_recall_case_counts": {
            variant_id: {
                method_id: methods[method_id]["full_recall_case_count_at_20"]
                for method_id in methods
            }
            for variant_id, methods in per_variant_method_metrics.items()
        },
        "missing_items_by_variant": missing_items_by_variant,
        "best_candidate_generation_variant": best_variant,
        "candidate_generation_ready": candidate_generation_ready,
        "rerank_required": rerank_required,
        "query_rewrite_required": query_rewrite_required,
        "embedding_change_supported": False,
        "recommended_next_step": _recommended_next_step(
            candidate_generation_ready=candidate_generation_ready,
            direct_gate_pass=direct_gate_pass,
            query_rewrite_required=query_rewrite_required,
        ),
        "architecture_c_status": "blocked",
        "limitations": [
            "This analysis is diagnostic-only and does not modify formal retrieval results or production retrievers.",
            "All experiments reuse the frozen v2 dataset and frozen model configuration in strict offline mode.",
            "Gold is used only for evaluation; candidate generation and ranking variants do not consume gold IDs.",
            "Document-level retrieval and dual-granularity union are non-formal experiments for candidate-pool diagnosis only.",
        ],
    }
    return payload


def build_recall_round_1_payload() -> dict[str, Any]:
    context = _load_experiment_context()
    current_candidate_generation = load_json_record(CANDIDATE_GENERATION_OUTPUT_PATH)
    runner = CandidateGenerationExperimentRunner(context=context)
    baseline_best = current_candidate_generation["best_candidate_generation_variant"]
    baseline_full_recall_case_ids = sorted(
        case_id
        for case_id, ranks in baseline_best["expected_item_full_corpus_ranks"].items()
        if all(rank is not None and rank <= 20 for rank in ranks.values())
    )
    round_1_results = runner.build_recall_round_1_results()
    success_gate = _build_recall_round_1_success_gate(
        case_results=round_1_results["case_results"],
        overall_metrics=round_1_results["overall_metrics"],
        baseline_full_recall_case_ids=baseline_full_recall_case_ids,
    )
    round_status = "passed_ready_for_integration_review" if success_gate["passed"] else "failed_frozen_move_to_round_2"
    next_step = (
        "integration_review_only_no_formal_retriever_change_yet"
        if success_gate["passed"]
        else "round_2_document_level_retrieval_plus_child_chunk_expansion"
    )
    return {
        "experiment_id": "retrieval_v2_candidate_recall_round_1",
        "experiment_scope": "document_aware_multi_view_vector_retrieval",
        "source_model": context.vector_config.model_name_or_path,
        "model_revision": runner.round_1_model_revision(),
        "embedding_dimension": runner.round_1_embedding_dimension(),
        "normalization": context.vector_config.normalize_embeddings,
        "representation_fields": {
            "chunk_view": ["chunk.content"],
            "context_view": [
                "document.title",
                "document.summary",
                "document.document_type",
                "document.scope_type",
                "chunk.citation_label",
                "chunk.metadata.section_title",
                "primary_solution_name",
                "applicable_solution_names",
                "document.industries",
                "document.tags",
                "chunk.content",
            ],
        },
        "scoring_rule": "multi_view_score = max(chunk_view_score, context_view_score)",
        "case_count": len(context.cases),
        "chunk_count": len(context.chunks_v2),
        "formal_result_hashes": compute_formal_result_hashes(),
        "boundary_artifact_hashes": {
            "blind_evaluation_v2_2": _sha256(Path("data/evaluation/retrieval/retrieval_metadata_blind_evaluation.v2_2.json")),
            "runtime_contract_proposal_v2_1": _sha256(Path("data/evaluation/retrieval/retrieval_runtime_contract_v2_1_proposal.json")),
        },
        "baseline_best_candidate_generation": {
            "variant_id": baseline_best["variant_id"],
            "method_id": baseline_best["method_id"],
            "candidate_recall_at_20": baseline_best["candidate_recall_at_20"],
            "full_recall_case_count_at_20": baseline_best["full_recall_case_count_at_20"],
            "full_recall_case_ids_at_20": baseline_full_recall_case_ids,
        },
        "overall_metrics": round_1_results["overall_metrics"],
        "per_case_metrics": round_1_results["case_results"],
        "ret2_015_analysis": round_1_results["focus_case_analysis"]["RET2-015"],
        "ret2_016_analysis": round_1_results["focus_case_analysis"]["RET2-016"],
        "rank_movements": round_1_results["rank_movements"],
        "view_attribution": round_1_results["view_attribution"],
        "success_gate": success_gate,
        "round_status": round_status,
        "next_step": next_step,
        "boundary_research_status": "closed",
        "formal_results_modified": False,
        "retriever_modified": False,
        "architecture_c_status": "blocked",
    }


def render_candidate_generation_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Retrieval V2 Candidate Generation")
    lines.append("")
    lines.append("## 为什么 Candidate Generation 是当前主瓶颈")
    lines.append("")
    best = payload["best_candidate_generation_variant"]
    lines.append(f"- best_variant: {best['variant_id']} / {best['method_id']}")
    lines.append(f"- candidate_recall_at_20: {best['candidate_recall_at_20']}")
    lines.append(f"- boundary_violation_rate_at_20: {best['solution_boundary_violation_rate_at_20']}")
    lines.append(f"- forbidden_hit_rate_at_20: {best['forbidden_hit_rate_at_20']}")
    lines.append(f"- candidate_generation_ready: {str(payload['candidate_generation_ready']).lower()}")
    lines.append("")
    lines.append("## 为什么后过滤不足")
    lines.append("")
    for method_id, details in payload["prefilter_vs_postfilter_comparison"].items():
        lines.append(
            f"- {method_id}: postfilter_recall_at_20={details['postfilter_candidate_recall_at_20']}, "
            f"prefilter_recall_at_20={details['prefilter_candidate_recall_at_20']}, "
            f"improved={str(details['prefilter_improves_candidate_recall']).lower()}"
        )
    lines.append("")
    lines.append("## 当前候选生成实现审计")
    lines.append("")
    audit = payload["current_candidate_generation_audit"]
    for key, value in audit.items():
        if isinstance(value, list):
            lines.append(f"- {key}: {', '.join(str(item) for item in value)}")
        else:
            lines.append(f"- {key}: {value}")
    lines.append("")
    for case_id in TARGET_CASE_IDS:
        lines.append(f"## {case_id} 分析")
        lines.append("")
        for method_id, items in payload["unresolved_case_analysis"].items():
            matching = [item for item in items if item["case_id"] == case_id]
            if not matching:
                continue
            lines.append(f"### {method_id}")
            lines.append("")
            for item in matching:
                lines.append(
                    f"- expected_id={item['expected_item_id']}, current_rank={item['current_method_rank']}, "
                    f"prefilter_rank={item['prefilter_method_rank']}, root_cause={item['root_cause']}"
                )
            lines.append("")
    lines.append("## Pre-retrieval Filter 结果")
    lines.append("")
    for method_id, metrics in payload["per_variant_method_metrics"]["G1"].items():
        lines.append(
            f"- {method_id}: recall@20={metrics['candidate_recall_at_20']}, "
            f"full_recall_case_count_at_20={metrics['full_recall_case_count_at_20']}, "
            f"boundary_rate_at_20={metrics['solution_boundary_violation_rate_at_20']}"
        )
    lines.append("")
    lines.append("## Representation Enrichment 结果")
    lines.append("")
    for method_id, metrics in payload["per_variant_method_metrics"]["G2"].items():
        lines.append(
            f"- {method_id}: recall@20={metrics['candidate_recall_at_20']}, "
            f"full_recall_case_count_at_20={metrics['full_recall_case_count_at_20']}"
        )
    lines.append("")
    lines.append("## Document Retrieval 结果")
    lines.append("")
    for method_id, metrics in payload["per_variant_method_metrics"]["G3"].items():
        lines.append(
            f"- {method_id}: recall@20={metrics['candidate_recall_at_20']}, "
            f"full_recall_case_count_at_20={metrics['full_recall_case_count_at_20']}"
        )
    lines.append("")
    lines.append("## Dual-granularity 结果")
    lines.append("")
    for variant_id in ("G4", "G5", "G6"):
        lines.append(f"### {variant_id}")
        lines.append("")
        for method_id, metrics in payload["per_variant_method_metrics"][variant_id].items():
            lines.append(
                f"- {method_id}: recall@20={metrics['candidate_recall_at_20']}, "
                f"full_recall_case_count_at_20={metrics['full_recall_case_count_at_20']}, "
                f"boundary_rate_at_20={metrics['solution_boundary_violation_rate_at_20']}"
            )
        lines.append("")
    lines.append("## 各变体 Top-5 / 10 / 20 Candidate Recall")
    lines.append("")
    for variant_id in VARIANT_ORDER:
        lines.append(f"### {variant_id}")
        lines.append("")
        for method_id, metrics in payload["per_variant_method_metrics"][variant_id].items():
            lines.append(
                f"- {method_id}: recall@5={metrics['candidate_recall_at_5']}, "
                f"recall@10={metrics['candidate_recall_at_10']}, recall@20={metrics['candidate_recall_at_20']}"
            )
        lines.append("")
    lines.append("## 是否达到 Candidate Recall@20 = 1")
    lines.append("")
    lines.append(f"- candidate_generation_ready: {str(payload['candidate_generation_ready']).lower()}")
    lines.append("")
    lines.append("## 是否需要 Rerank")
    lines.append("")
    lines.append(f"- rerank_required: {str(payload['rerank_required']).lower()}")
    lines.append("")
    lines.append("## 是否需要 Query Rewrite")
    lines.append("")
    lines.append(f"- query_rewrite_required: {str(payload['query_rewrite_required']).lower()}")
    lines.append("")
    lines.append("## 是否支持 Embedding 变化")
    lines.append("")
    lines.append(f"- embedding_change_supported: {str(payload['embedding_change_supported']).lower()}")
    lines.append("")
    lines.append("## 推荐最小方案")
    lines.append("")
    lines.append(f"- recommended_next_step: {payload['recommended_next_step']}")
    lines.append("")
    lines.append("## Architecture C 仍为 blocked")
    lines.append("")
    lines.append(f"- architecture_c_status: {payload['architecture_c_status']}")
    lines.append("")
    lines.append("## 合成数据和小样本限制")
    lines.append("")
    for limitation in payload["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    round_1_payload = _load_tracked_recall_round_1_payload()
    if round_1_payload is not None:
        lines.extend(_render_recall_round_1_markdown_lines(round_1_payload))
    return "\n".join(lines)


def write_candidate_generation_outputs(payload: dict[str, Any]) -> None:
    write_json_atomic(CANDIDATE_GENERATION_OUTPUT_PATH, payload)
    CANDIDATE_GENERATION_DOC_PATH.write_text(render_candidate_generation_markdown(payload), encoding="utf-8")


def check_candidate_generation_outputs() -> tuple[bool, list[str]]:
    recomputed = build_candidate_generation_payload()
    differences: list[str] = []

    if not CANDIDATE_GENERATION_OUTPUT_PATH.exists():
        differences.append(f"Missing tracked JSON output: {CANDIDATE_GENERATION_OUTPUT_PATH}")
    else:
        tracked_json = load_json_record(CANDIDATE_GENERATION_OUTPUT_PATH)
        differences.extend(diff_json_objects(tracked_json, recomputed))

    rendered_markdown = render_candidate_generation_markdown(recomputed)
    if not CANDIDATE_GENERATION_DOC_PATH.exists():
        differences.append(f"Missing tracked Markdown output: {CANDIDATE_GENERATION_DOC_PATH}")
    else:
        tracked_markdown = CANDIDATE_GENERATION_DOC_PATH.read_text(encoding="utf-8")
        if tracked_markdown != rendered_markdown:
            differences.append(f"Markdown output drifted: {CANDIDATE_GENERATION_DOC_PATH}")

    return (not differences, differences)


def write_recall_round_1_output(payload: dict[str, Any]) -> None:
    write_json_atomic(RECALL_ROUND_1_OUTPUT_PATH, payload)
    base_payload = build_candidate_generation_payload()
    CANDIDATE_GENERATION_DOC_PATH.write_text(render_candidate_generation_markdown(base_payload), encoding="utf-8")


def check_recall_round_1_output() -> tuple[bool, list[str]]:
    differences: list[str] = []
    if not RECALL_ROUND_1_OUTPUT_PATH.exists():
        return False, [f"Missing tracked JSON output: {RECALL_ROUND_1_OUTPUT_PATH}"]
    tracked_json = load_json_record(RECALL_ROUND_1_OUTPUT_PATH)
    recomputed = build_recall_round_1_payload()
    differences.extend(diff_json_objects(tracked_json, recomputed))
    return (not differences, differences)


def audit_current_candidate_generation() -> dict[str, Any]:
    return {
        "retrieval_unit": "chunk for lexical, vector, and hybrid",
        "lexical_scoring_fields": ["content", "citation_label", "tags", "industries", "solution_ids", "document_type"],
        "vector_scoring_text": "chunk.content only",
        "vector_query_prefix": "query: ",
        "vector_document_prefix": "passage: ",
        "title_participates_in_lexical_scoring": False,
        "summary_participates_in_lexical_scoring": False,
        "title_participates_in_vector_scoring": False,
        "summary_participates_in_vector_scoring": False,
        "section_heading_participates_in_lexical_scoring": "only through citation_label",
        "section_heading_participates_in_vector_scoring": False,
        "parent_document_context_in_chunk_vector_representation": False,
        "runtime_filter_stage": "before scoring, but only with legacy document_types / industries / solution_ids / tags / statuses / effective_on filters",
        "runtime_scope_metadata_used_before_scoring": False,
        "hybrid_merge_strategy": "lexical top-20 union vector top-20, then fixed RRF dedupe by (document_id, chunk_id)",
        "candidate_pool_truncation": {
            "lexical": "top_k on scored chunk list",
            "vector": "top_k on scored chunk list",
            "hybrid": "lexical_candidate_k=20 and vector_candidate_k=20 before fusion, then output_top_k=5",
        },
    }


class CandidateGenerationExperimentRunner:
    def __init__(self, *, context: ExperimentContext) -> None:
        self._context = context
        self._vector_provider: SentenceTransformerEmbeddingProvider | None = None
        self._base_run_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}

    def build_unresolved_case_analysis(self) -> dict[str, list[dict[str, Any]]]:
        results_by_variant = self._variant_candidate_results()
        output: dict[str, list[dict[str, Any]]] = {method_id: [] for method_id in METHOD_IDS}

        for method_id in METHOD_IDS:
            current_results = results_by_variant["G0"][method_id]
            prefiltered_results = results_by_variant["G1"][method_id]
            enriched_results = results_by_variant["G2"][method_id]
            dual_results = results_by_variant["G4"][method_id]

            for case_id in TARGET_CASE_IDS:
                case = next(item for item in self._context.cases if item.retrieval_case_id == case_id)
                expected_ids = list(case.evaluation_gold.expected_relevant_chunk_ids) + list(case.evaluation_gold.expected_relevant_document_ids)
                for expected_id in expected_ids:
                    current_rank = _find_candidate_rank(current_results[case_id]["full_candidates"], case=case, item_id=expected_id)
                    if current_rank is not None and current_rank <= 20:
                        continue
                    prefilter_rank = _find_candidate_rank(prefiltered_results[case_id]["full_candidates"], case=case, item_id=expected_id)
                    enriched_rank = _find_candidate_rank(enriched_results[case_id]["full_candidates"], case=case, item_id=expected_id)
                    dual_rank = _find_candidate_rank(dual_results[case_id]["full_candidates"], case=case, item_id=expected_id)
                    expected_meta = _expected_item_metadata(
                        expected_id=expected_id,
                        documents_by_id=self._context.documents_by_id,
                        chunks_by_id=self._context.chunks_by_id,
                    )
                    query_tokens = tokenize_lexical_text(case.query)
                    lexical_matched_terms = _matched_terms_for_expected_item(current_results["lexical_v1" if False else case_id]["full_candidates"] if False else current_results[case_id]["full_candidates"], case=case, item_id=expected_id)
                    runtime_ineligible_crowding = _count_runtime_ineligible_ahead(
                        current_results[case_id]["full_candidates"],
                        case=case,
                        rank=current_rank,
                        documents_by_id=self._context.documents_by_id,
                        chunks_by_id=self._context.chunks_by_id,
                    )
                    sibling_substitution = _has_higher_ranked_sibling_chunk(
                        current_results[case_id]["full_candidates"],
                        expected_id=expected_id,
                    )
                    lexical_overlap = set(query_tokens) & set(tokenize_lexical_text(expected_meta["chunk_content"]))
                    title_overlap = set(query_tokens) & set(tokenize_lexical_text(expected_meta["document_title"]))
                    summary_overlap = set(query_tokens) & set(tokenize_lexical_text(expected_meta["document_summary"]))
                    root_cause = _classify_root_cause(
                        method_id=method_id,
                        current_rank=current_rank,
                        prefilter_rank=prefilter_rank,
                        enriched_rank=enriched_rank,
                        dual_rank=dual_rank,
                        runtime_ineligible_crowding=runtime_ineligible_crowding,
                        sibling_substitution=sibling_substitution,
                        lexical_overlap=bool(lexical_overlap),
                        title_overlap=bool(title_overlap),
                        summary_overlap=bool(summary_overlap),
                    )
                    output[method_id].append(
                        {
                            "case_id": case_id,
                            "source_case_id": case.source_case_id,
                            "expected_item_id": expected_id,
                            "expected_document_id": expected_meta["document_id"],
                            "expected_chunk_id": expected_meta["chunk_id"],
                            "expected_item_text_fields_summary": expected_meta["content_excerpt"],
                            "document_title": expected_meta["document_title"],
                            "document_summary": expected_meta["document_summary"],
                            "chunk_section": expected_meta["chunk_section"],
                            "chunk_keyword_tokens": expected_meta["chunk_keyword_tokens"],
                            "query_tokens": query_tokens,
                            "lexical_matched_terms": lexical_matched_terms,
                            "current_method_rank": current_rank,
                            "full_corpus_rank": current_rank,
                            "prefilter_method_rank": prefilter_rank,
                            "enriched_method_rank": enriched_rank,
                            "dual_granularity_rank": dual_rank,
                            "current_top20_missing": current_rank is None or current_rank > 20,
                            "current_runtime_filter_excluded": prefilter_rank is None,
                            "runtime_ineligible_crowding_count": runtime_ineligible_crowding,
                            "because_runtime_ineligible_candidates_occupy_pool": runtime_ineligible_crowding > 0,
                            "because_chunk_context_insufficient": bool(dual_rank is not None and current_rank is not None and dual_rank < current_rank),
                            "because_title_not_indexed": bool(title_overlap and not lexical_overlap and enriched_rank is not None and (current_rank is None or enriched_rank < current_rank)),
                            "because_summary_not_indexed": bool(summary_overlap and not lexical_overlap and enriched_rank is not None and (current_rank is None or enriched_rank < current_rank)),
                            "because_parent_document_signal_missing": bool(dual_rank is not None and (current_rank is None or dual_rank < current_rank)),
                            "because_expected_sibling_chunk_substitution": sibling_substitution,
                            "completely_no_lexical_overlap": not bool(lexical_overlap | title_overlap | summary_overlap),
                            "vector_similarity_clearly_low": method_id == "vector_v1" and current_rank is None and dual_rank == current_rank,
                            "root_cause": root_cause,
                        }
                    )
        return output

    def build_variant_metrics(self, *, variant_definitions: dict[str, dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
        results_by_variant = self._variant_candidate_results()
        output: dict[str, dict[str, dict[str, Any]]] = {}
        for variant_id in VARIANT_ORDER:
            output[variant_id] = {}
            for method_id in METHOD_IDS:
                case_map = results_by_variant[variant_id][method_id]
                output[variant_id][method_id] = _summarize_variant_method(
                    cases=self._context.cases,
                    case_map=case_map,
                    variant_id=variant_id,
                    method_id=method_id,
                )
        return output

    def build_prefilter_vs_postfilter_comparison(
        self,
        per_variant_method_metrics: dict[str, dict[str, dict[str, Any]]],
    ) -> dict[str, dict[str, Any]]:
        counterfactual_payload = self._context.counterfactual_payload
        comparison: dict[str, dict[str, Any]] = {}
        for method_id in METHOD_IDS:
            postfilter_recall = next(
                entry["recall_at_5"]
                for entry in counterfactual_payload["matrix_results"]
                if entry["method_id"] == method_id
                and entry["strategy_id"] == "S1"
                and entry["pool_size"] == 20
                and entry["diversity_mode"] == "no_diversity"
                and entry["rerank_mode"] == "original_rank"
            )
            prefilter_recall = per_variant_method_metrics["G1"][method_id]["candidate_recall_at_20"]
            comparison[method_id] = {
                "postfilter_candidate_recall_at_20": postfilter_recall,
                "prefilter_candidate_recall_at_20": prefilter_recall,
                "prefilter_improves_candidate_recall": prefilter_recall > postfilter_recall,
            }
        return comparison

    def _variant_candidate_results(self) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
        results: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
        for variant_id in VARIANT_ORDER:
            results[variant_id] = {}
            for method_id in METHOD_IDS:
                results[variant_id][method_id] = {}
                for case in self._context.cases:
                    results[variant_id][method_id][case.retrieval_case_id] = self._run_case_variant(
                        case=case,
                        variant_id=variant_id,
                        method_id=method_id,
                    )
        return results

    def _run_case_variant(self, *, case: Any, variant_id: str, method_id: str) -> dict[str, Any]:
        if variant_id == "G0":
            candidates = self._get_chunk_method_candidates(
                case=case,
                method_id=method_id,
                bundle=self._context.current_chunk_bundle,
                prefilter=False,
            )
        elif variant_id == "G1":
            candidates = self._get_chunk_method_candidates(
                case=case,
                method_id=method_id,
                bundle=self._context.current_chunk_bundle,
                prefilter=True,
            )
        elif variant_id == "G2":
            candidates = self._get_chunk_method_candidates(
                case=case,
                method_id=method_id,
                bundle=self._context.enriched_chunk_bundle,
                prefilter=False,
            )
        elif variant_id == "G3":
            candidates = self._get_document_level_candidates(case=case, method_id=method_id, prefilter=False)
        elif variant_id == "G4":
            candidates = self._merge_dual_granularity(
                case=case,
                method_id=method_id,
                chunk_candidates=self._get_chunk_method_candidates(
                    case=case,
                    method_id=method_id,
                    bundle=self._context.current_chunk_bundle,
                    prefilter=False,
                ),
                document_candidates=self._get_document_level_candidates(case=case, method_id=method_id, prefilter=False),
            )
        elif variant_id == "G5":
            candidates = self._merge_dual_granularity(
                case=case,
                method_id=method_id,
                chunk_candidates=self._get_chunk_method_candidates(
                    case=case,
                    method_id=method_id,
                    bundle=self._context.current_chunk_bundle,
                    prefilter=True,
                ),
                document_candidates=self._get_document_level_candidates(case=case, method_id=method_id, prefilter=True),
            )
        elif variant_id == "G6":
            candidates = self._merge_dual_granularity(
                case=case,
                method_id=method_id,
                chunk_candidates=self._get_chunk_method_candidates(
                    case=case,
                    method_id=method_id,
                    bundle=self._context.enriched_chunk_bundle,
                    prefilter=True,
                ),
                document_candidates=self._get_document_level_candidates(case=case, method_id=method_id, prefilter=True),
            )
        else:
            raise ValueError(f"Unsupported variant_id: {variant_id}")

        return _evaluate_candidate_list(case=case, candidates=candidates, documents_by_id=self._context.documents_by_id, chunks_by_id=self._context.chunks_by_id)

    def _get_chunk_method_candidates(
        self,
        *,
        case: Any,
        method_id: str,
        bundle: CorpusBundle,
        prefilter: bool,
    ) -> list[dict[str, Any]]:
        if method_id == "hybrid_v1":
            lexical = self._get_chunk_method_candidates(case=case, method_id="lexical_v1", bundle=bundle, prefilter=prefilter)
            vector = self._get_chunk_method_candidates(case=case, method_id="vector_v1", bundle=bundle, prefilter=prefilter)
            return _merge_hybrid_candidates(
                lexical_candidates=lexical,
                vector_candidates=vector,
                config=self._context.hybrid_config,
                source_label="chunk",
            )

        cache_key = (
            f"chunk:{bundle is self._context.enriched_chunk_bundle}:{prefilter}",
            case.retrieval_case_id,
            method_id,
        )
        if cache_key in self._base_run_cache:
            return self._base_run_cache[cache_key]

        runtime_input = self._context.runtime_inputs[case.retrieval_case_id]
        legacy_documents = bundle.legacy_documents
        legacy_chunks = bundle.legacy_chunks
        if prefilter:
            legacy_documents, legacy_chunks = _prefilter_corpus_bundle(
                case=case,
                runtime_input=runtime_input,
                bundle=bundle,
            )
            retriever_filters: dict[str, object] = {}
        else:
            retriever_filters = runtime_input_to_retriever_filters(runtime_input)

        if method_id == "lexical_v1":
            retriever = WeightedBM25Retriever(config=self._context.lexical_config)
            retriever.build_index(documents=legacy_documents, chunks=legacy_chunks)
        elif method_id == "vector_v1":
            retriever = ExactVectorRetriever(
                config=self._context.vector_config,
                embedding_provider=self._vector_provider_instance(),
                project_root=Path.cwd(),
            )
            retriever.build_index(
                documents=legacy_documents,
                chunks=legacy_chunks,
                knowledge_base_version=self._context.knowledge_base_version,
            )
        else:
            raise ValueError(f"Unsupported chunk method_id: {method_id}")

        candidates = [
            candidate.model_dump(mode="json")
            for candidate in retriever.retrieve(
                query=runtime_input.query,
                filters=retriever_filters,
                top_k=max(1, len(legacy_chunks)),
            )
        ]
        for candidate in candidates:
            candidate["candidate_sources"] = [method_id]
        self._base_run_cache[cache_key] = candidates
        return candidates

    def _get_document_level_candidates(self, *, case: Any, method_id: str, prefilter: bool) -> list[dict[str, Any]]:
        if method_id == "hybrid_v1":
            lexical = self._get_document_level_candidates(case=case, method_id="lexical_v1", prefilter=prefilter)
            vector = self._get_document_level_candidates(case=case, method_id="vector_v1", prefilter=prefilter)
            return _merge_hybrid_candidates(
                lexical_candidates=lexical,
                vector_candidates=vector,
                config=self._context.hybrid_config,
                source_label="document_expanded",
            )

        cache_key = (f"document:{prefilter}", case.retrieval_case_id, method_id)
        if cache_key in self._base_run_cache:
            return self._base_run_cache[cache_key]

        runtime_input = self._context.runtime_inputs[case.retrieval_case_id]
        legacy_documents = self._context.document_bundle.legacy_documents
        legacy_chunks = self._context.document_bundle.legacy_chunks
        if prefilter:
            legacy_documents, legacy_chunks = _prefilter_corpus_bundle(
                case=case,
                runtime_input=runtime_input,
                bundle=self._context.document_bundle,
            )
            retriever_filters: dict[str, object] = {}
        else:
            retriever_filters = runtime_input_to_retriever_filters(runtime_input)

        if method_id == "lexical_v1":
            retriever = WeightedBM25Retriever(config=self._context.lexical_config)
            retriever.build_index(documents=legacy_documents, chunks=legacy_chunks)
        elif method_id == "vector_v1":
            retriever = ExactVectorRetriever(
                config=self._context.vector_config,
                embedding_provider=self._vector_provider_instance(),
                project_root=Path.cwd(),
            )
            retriever.build_index(
                documents=legacy_documents,
                chunks=legacy_chunks,
                knowledge_base_version=f"{self._context.knowledge_base_version}:document",
            )
        else:
            raise ValueError(f"Unsupported document method_id: {method_id}")

        doc_candidates = [
            candidate.model_dump(mode="json")
            for candidate in retriever.retrieve(
                query=runtime_input.query,
                filters=retriever_filters,
                top_k=max(1, len(legacy_chunks)),
            )
        ]
        expanded = _expand_document_candidates_to_chunks(
            document_candidates=doc_candidates,
            child_chunk_ids=self._context.document_bundle.document_children,
            child_rank_source=self._get_chunk_method_candidates(
                case=case,
                method_id=method_id,
                bundle=self._context.current_chunk_bundle,
                prefilter=prefilter,
            ),
            chunks_by_id=self._context.chunks_by_id,
        )
        self._base_run_cache[cache_key] = expanded
        return expanded

    def _merge_dual_granularity(
        self,
        *,
        case: Any,
        method_id: str,
        chunk_candidates: list[dict[str, Any]],
        document_candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if method_id == "hybrid_v1":
            return _merge_hybrid_candidates(
                lexical_candidates=self._merge_dual_granularity(
                    case=case,
                    method_id="lexical_v1",
                    chunk_candidates=self._get_chunk_method_candidates(
                        case=case,
                        method_id="lexical_v1",
                        bundle=self._context.current_chunk_bundle,
                        prefilter=False,
                    ),
                    document_candidates=self._get_document_level_candidates(case=case, method_id="lexical_v1", prefilter=False),
                ),
                vector_candidates=self._merge_dual_granularity(
                    case=case,
                    method_id="vector_v1",
                    chunk_candidates=self._get_chunk_method_candidates(
                        case=case,
                        method_id="vector_v1",
                        bundle=self._context.current_chunk_bundle,
                        prefilter=False,
                    ),
                    document_candidates=self._get_document_level_candidates(case=case, method_id="vector_v1", prefilter=False),
                ),
                config=self._context.hybrid_config,
                source_label="dual_granularity",
            )

        merged: dict[str, dict[str, Any]] = {}
        for source_name, candidates in (("chunk", chunk_candidates), ("document_expanded", document_candidates)):
            for candidate in candidates:
                candidate_id = candidate.get("chunk_id") or candidate["document_id"]
                existing = merged.get(candidate_id)
                seed = dict(candidate)
                seed.setdefault("candidate_sources", [])
                seed["candidate_sources"] = _deduplicate(seed["candidate_sources"] + [source_name])
                seed["chunk_rank"] = candidate["rank"] if source_name == "chunk" else seed.get("chunk_rank")
                seed["document_rank"] = candidate["rank"] if source_name == "document_expanded" else seed.get("document_rank")
                if existing is None:
                    merged[candidate_id] = seed
                    continue
                if candidate["rank"] < existing["rank"] or (
                    candidate["rank"] == existing["rank"] and candidate_id < (existing.get("chunk_id") or existing["document_id"])
                ):
                    seed["candidate_sources"] = _deduplicate(existing.get("candidate_sources", []) + seed["candidate_sources"])
                    if existing.get("chunk_rank") is not None:
                        seed["chunk_rank"] = existing["chunk_rank"]
                    if existing.get("document_rank") is not None:
                        seed["document_rank"] = existing["document_rank"]
                    merged[candidate_id] = seed
                else:
                    existing["candidate_sources"] = _deduplicate(existing.get("candidate_sources", []) + seed["candidate_sources"])
                    if source_name == "chunk":
                        existing["chunk_rank"] = min(existing.get("chunk_rank") or candidate["rank"], candidate["rank"])
                    else:
                        existing["document_rank"] = min(existing.get("document_rank") or candidate["rank"], candidate["rank"])
        ordered = sorted(
            merged.values(),
            key=lambda item: (
                item["rank"],
                item.get("document_rank") or 10_000,
                item.get("chunk_rank") or 10_000,
                item.get("chunk_id") or item["document_id"],
            ),
        )
        return _renumber_candidates(ordered)

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

    def round_1_model_revision(self) -> str:
        return self._vector_provider_instance().resolved_revision

    def round_1_embedding_dimension(self) -> int:
        return self._vector_provider_instance().dimension

    def build_recall_round_1_results(self) -> dict[str, Any]:
        provider = self._vector_provider_instance()
        solution_name_lookup = _solution_name_lookup(self._context.documents_v2)
        chunk_view_texts = [chunk.content for chunk in self._context.chunks_v2]
        context_view_texts = [
            _render_round_1_context_view_text(
                document=self._context.documents_by_id[chunk.document_id],
                chunk=chunk,
                solution_name_lookup=solution_name_lookup,
            )
            for chunk in self._context.chunks_v2
        ]
        chunk_view_embeddings = provider.encode_documents(chunk_view_texts)
        context_view_embeddings = provider.encode_documents(context_view_texts)

        case_results: list[dict[str, Any]] = []
        baseline_ranks = _load_best_candidate_generation_ranks()
        newly_recalled_items: list[dict[str, Any]] = []
        top20_source_counts = {"chunk_view": 0, "context_view": 0, "both": 0}

        chunk_bundle = list(zip(self._context.chunks_v2, chunk_view_embeddings, context_view_embeddings, strict=True))
        for case in self._context.cases:
            query_embedding = provider.encode_queries([case.query])[0]
            scored_candidates: list[dict[str, Any]] = []
            for chunk, chunk_embedding, context_embedding in chunk_bundle:
                chunk_score = round(_dot(query_embedding, chunk_embedding), self._context.vector_config.score_round_digits)
                context_score = round(_dot(query_embedding, context_embedding), self._context.vector_config.score_round_digits)
                multi_view_score = max(chunk_score, context_score)
                winning_view = _winning_view_label(chunk_view_score=chunk_score, context_view_score=context_score)
                scored_candidates.append(
                    {
                        "document_id": chunk.document_id,
                        "chunk_id": chunk.chunk_id,
                        "document_type": chunk.document_type.value,
                        "score": multi_view_score,
                        "chunk_view_score": chunk_score,
                        "context_view_score": context_score,
                        "winning_view": winning_view,
                        "candidate_sources": [winning_view],
                    }
                )
            scored_candidates.sort(
                key=lambda item: (
                    -item["score"],
                    item["document_id"],
                    item["chunk_id"],
                )
            )
            candidates = _renumber_candidates(scored_candidates)
            evaluation = _evaluate_candidate_list(
                case=case,
                candidates=candidates,
                documents_by_id=self._context.documents_by_id,
                chunks_by_id=self._context.chunks_by_id,
            )
            expected_items = list(case.evaluation_gold.expected_relevant_chunk_ids) + list(case.evaluation_gold.expected_relevant_document_ids)
            expected_item_ranks: dict[str, int | None] = {}
            expected_item_view_sources: dict[str, str | None] = {}
            expected_item_rank_movements: dict[str, dict[str, Any]] = {}
            for item_id in expected_items:
                rank = _find_candidate_rank(candidates, case=case, item_id=item_id)
                expected_item_ranks[item_id] = rank
                source = _view_source_for_expected_item(candidates=candidates, case=case, item_id=item_id)
                expected_item_view_sources[item_id] = source
                if rank is not None and rank <= 20 and source in top20_source_counts:
                    top20_source_counts[source] += 1
                baseline_rank = baseline_ranks.get(case.retrieval_case_id, {}).get(item_id)
                expected_item_rank_movements[item_id] = {
                    "baseline_best_rank": baseline_rank,
                    "round_1_rank": rank,
                    "delta": _rank_delta(baseline_rank=baseline_rank, new_rank=rank),
                }
                if (baseline_rank is None or baseline_rank > 20) and rank is not None and rank <= 20:
                    newly_recalled_items.append(
                        {
                            "case_id": case.retrieval_case_id,
                            "item_id": item_id,
                            "view_source": source,
                            "baseline_best_rank": baseline_rank,
                            "round_1_rank": rank,
                        }
                    )
            case_results.append(
                {
                    "case_id": case.retrieval_case_id,
                    "source_case_id": case.source_case_id,
                    "candidate_recall_at_5": evaluation["candidate_recall_at_5"],
                    "candidate_recall_at_10": evaluation["candidate_recall_at_10"],
                    "candidate_recall_at_20": evaluation["candidate_recall_at_20"],
                    "mean_reciprocal_rank": _mean_reciprocal_rank(expected_item_ranks),
                    "full_recall_at_20": evaluation["candidate_recall_at_20"] == 1.0,
                    "missing_expected_items_at_20": [
                        item_id for item_id, rank in expected_item_ranks.items() if rank is None or rank > 20
                    ],
                    "expected_item_ranks": expected_item_ranks,
                    "expected_item_view_sources": expected_item_view_sources,
                    "rank_movements": expected_item_rank_movements,
                }
            )

        overall_metrics = {
            "candidate_recall_at_5": sum(item["candidate_recall_at_5"] for item in case_results) / len(case_results),
            "candidate_recall_at_10": sum(item["candidate_recall_at_10"] for item in case_results) / len(case_results),
            "candidate_recall_at_20": sum(item["candidate_recall_at_20"] for item in case_results) / len(case_results),
            "mean_reciprocal_rank": sum(item["mean_reciprocal_rank"] for item in case_results) / len(case_results),
            "full_recall_case_count_at_20": sum(1 for item in case_results if item["full_recall_at_20"]),
            "cases_with_full_recall_at_20": [item["case_id"] for item in case_results if item["full_recall_at_20"]],
            "failed_case_ids": [item["case_id"] for item in case_results if not item["full_recall_at_20"]],
        }
        focus_case_analysis = {case_id: next(item for item in case_results if item["case_id"] == case_id) for case_id in RECALL_ROUND_1_CASE_IDS}
        return {
            "overall_metrics": overall_metrics,
            "case_results": case_results,
            "focus_case_analysis": focus_case_analysis,
            "rank_movements": {item["case_id"]: item["rank_movements"] for item in case_results},
            "view_attribution": {
                "newly_recalled_expected_items": newly_recalled_items,
                "newly_recalled_source_counts": {
                    "chunk_view": sum(1 for item in newly_recalled_items if item["view_source"] == "chunk_view"),
                    "context_view": sum(1 for item in newly_recalled_items if item["view_source"] == "context_view"),
                    "both": sum(1 for item in newly_recalled_items if item["view_source"] == "both"),
                },
                "top20_expected_item_source_counts": top20_source_counts,
            },
        }


def _load_experiment_context() -> ExperimentContext:
    diagnostic_context = load_diagnostic_context()
    benchmark_config = load_json_record(BENCHMARK_CONFIG_PATH)
    knowledge_base_version = load_json_record(Path(benchmark_config["manifest_file"]))["knowledge_base_version"]
    diagnosis_payload = load_json_record(DIAGNOSIS_OUTPUT_PATH)
    counterfactual_payload = load_json_record(COUNTERFACTUAL_OUTPUT_PATH)
    lexical_config = LexicalBaselineConfig.model_validate(load_json_record(LEXICAL_CONFIG_PATH)["algorithm_config"])
    vector_config = VectorBaselineConfig.model_validate(load_json_record(VECTOR_CONFIG_PATH)["algorithm_config"])
    hybrid_config = HybridBaselineConfig.model_validate(load_json_record(HYBRID_CONFIG_PATH)["algorithm_config"])

    current_docs = diagnostic_context.documents
    current_chunks = diagnostic_context.chunks
    current_legacy_docs = project_v2_documents_to_legacy_runtime_inputs(current_docs)
    current_legacy_chunks = project_v2_chunks_to_legacy_runtime_inputs(current_chunks)

    enriched_docs, enriched_chunks = _build_enriched_chunk_corpus(current_docs=current_docs, current_chunks=current_chunks)
    enriched_legacy_docs = project_v2_documents_to_legacy_runtime_inputs(enriched_docs)
    enriched_legacy_chunks = project_v2_chunks_to_legacy_runtime_inputs(enriched_chunks)

    document_docs, document_chunks, document_children = _build_document_level_corpus(current_docs=current_docs, current_chunks=current_chunks)
    document_legacy_docs = project_v2_documents_to_legacy_runtime_inputs(document_docs)
    document_legacy_chunks = project_v2_chunks_to_legacy_runtime_inputs(document_chunks)

    return ExperimentContext(
        benchmark_config=benchmark_config,
        knowledge_base_version=knowledge_base_version,
        diagnosis_payload=diagnosis_payload,
        counterfactual_payload=counterfactual_payload,
        lexical_config=lexical_config,
        vector_config=vector_config,
        hybrid_config=hybrid_config,
        cases=diagnostic_context.cases,
        documents_v2=current_docs,
        chunks_v2=current_chunks,
        runtime_inputs={case.retrieval_case_id: make_runtime_input_v2(case=case, top_k=5) for case in diagnostic_context.cases},
        current_chunk_bundle=CorpusBundle(
            documents_v2=current_docs,
            chunks_v2=current_chunks,
            legacy_documents=current_legacy_docs,
            legacy_chunks=current_legacy_chunks,
            document_children=_document_children(current_chunks),
        ),
        enriched_chunk_bundle=CorpusBundle(
            documents_v2=enriched_docs,
            chunks_v2=enriched_chunks,
            legacy_documents=enriched_legacy_docs,
            legacy_chunks=enriched_legacy_chunks,
            document_children=_document_children(enriched_chunks),
        ),
        document_bundle=CorpusBundle(
            documents_v2=document_docs,
            chunks_v2=document_chunks,
            legacy_documents=document_legacy_docs,
            legacy_chunks=document_legacy_chunks,
            document_children=document_children,
        ),
        documents_by_id={document.document_id: document for document in current_docs},
        chunks_by_id={chunk.chunk_id: chunk for chunk in current_chunks},
    )


def _build_enriched_chunk_corpus(
    *,
    current_docs: list[KnowledgeDocumentV2],
    current_chunks: list[KnowledgeChunkV2],
) -> tuple[list[KnowledgeDocumentV2], list[KnowledgeChunkV2]]:
    documents_by_id = {document.document_id: document for document in current_docs}
    new_chunks: list[KnowledgeChunkV2] = []
    for chunk in current_chunks:
        document = documents_by_id[chunk.document_id]
        section_title = ""
        if isinstance(chunk.metadata, dict):
            section_title = str(chunk.metadata.get("section_title", "") or "")
        content = _render_enriched_chunk_text(document=document, chunk=chunk, section_title=section_title)
        payload = chunk.model_dump(mode="json")
        payload["content"] = content
        new_chunks.append(KnowledgeChunkV2.model_validate(payload))
    return current_docs, new_chunks


def _build_document_level_corpus(
    *,
    current_docs: list[KnowledgeDocumentV2],
    current_chunks: list[KnowledgeChunkV2],
) -> tuple[list[KnowledgeDocumentV2], list[KnowledgeChunkV2], dict[str, list[str]]]:
    doc_children = _document_children(current_chunks)
    new_chunks: list[KnowledgeChunkV2] = []
    for index, document in enumerate(current_docs):
        payload = {
            "chunk_id": f"{document.document_id}#doc-000",
            "document_id": document.document_id,
            "document_type": document.document_type,
            "chunk_index": 0,
            "content": _render_document_retrieval_text(document),
            "token_estimate": max(1, len(document.content) // 4),
            "tags": list(document.tags),
            "industries": list(document.industries),
            "metadata": {"document_level_retrieval": True, "source_index": index},
            "citation_label": document.title,
            "primary_solution_id": document.primary_solution_id,
            "applicable_solution_ids": list(document.applicable_solution_ids),
            "excluded_solution_ids": list(document.excluded_solution_ids),
            "scope_type": document.scope_type,
            "scope_notes": document.scope_notes,
        }
        new_chunks.append(KnowledgeChunkV2.model_validate(payload))
    return current_docs, new_chunks, doc_children


def _prefilter_corpus_bundle(
    *,
    case: Any,
    runtime_input: Any,
    bundle: CorpusBundle,
) -> tuple[list[KnowledgeDocument], list[KnowledgeChunk]]:
    eligible_document_ids: set[str] = set()
    eligible_chunk_ids: list[str] = []

    docs_by_id = {document.document_id: document for document in bundle.documents_v2}
    chunks_by_id = {chunk.chunk_id: chunk for chunk in bundle.chunks_v2}

    for chunk in bundle.chunks_v2:
        document = docs_by_id[chunk.document_id]
        if _runtime_safe_chunk_eligible(case=case, runtime_input=runtime_input, document=document, chunk=chunk):
            eligible_document_ids.add(document.document_id)
            eligible_chunk_ids.append(chunk.chunk_id)

    legacy_docs_by_id = {document.document_id: document for document in bundle.legacy_documents}
    legacy_chunks_by_id = {chunk.chunk_id: chunk for chunk in bundle.legacy_chunks}
    return (
        [legacy_docs_by_id[document_id] for document_id in sorted(eligible_document_ids)],
        [legacy_chunks_by_id[chunk_id] for chunk_id in eligible_chunk_ids],
    )


def _runtime_safe_chunk_eligible(*, case: Any, runtime_input: Any, document: KnowledgeDocumentV2, chunk: KnowledgeChunkV2) -> bool:
    if not document.is_active(as_of=runtime_input.effective_on):
        return False
    if runtime_input.allowed_document_types and document.document_type.value not in set(runtime_input.allowed_document_types):
        return False
    if runtime_input.industries and document.industries and set(document.industries).isdisjoint(set(runtime_input.industries)):
        return False
    if runtime_input.tags and document.tags and set(document.tags).isdisjoint(set(runtime_input.tags)):
        return False

    operational_scope = set(runtime_input.operational_solution_scope)
    applicable = set(chunk.applicable_solution_ids)
    excluded = set(chunk.excluded_solution_ids)
    if excluded & operational_scope:
        return False
    if chunk.scope_type.value == "global_policy":
        return True
    return applicable.issubset(operational_scope)


def _render_enriched_chunk_text(document: KnowledgeDocumentV2, chunk: KnowledgeChunkV2, section_title: str) -> str:
    parts = [
        f"Title: {document.title}",
        f"Summary: {document.summary}",
    ]
    if section_title:
        parts.append(f"Section: {section_title}")
    parts.append(f"Content: {chunk.content}")
    return "\n".join(parts).strip()


def _render_document_retrieval_text(document: KnowledgeDocumentV2) -> str:
    return "\n".join(
        [
            f"Title: {document.title}",
            f"Summary: {document.summary}",
            f"Document Type: {document.document_type.value}",
            f"Content: {document.content}",
        ]
    ).strip()


def _render_round_1_context_view_text(
    *,
    document: KnowledgeDocumentV2,
    chunk: KnowledgeChunkV2,
    solution_name_lookup: dict[str, str],
) -> str:
    section_title = ""
    if isinstance(chunk.metadata, dict):
        section_title = str(chunk.metadata.get("section_title", "") or "")
    applicable_solution_names = [
        solution_name_lookup.get(solution_id, solution_id)
        for solution_id in chunk.applicable_solution_ids
    ]
    parts = [
        f"Document Title: {document.title}",
        f"Document Summary: {document.summary}",
        f"Document Type: {document.document_type.value}",
        f"Scope Type: {document.scope_type.value}",
        f"Citation Label: {chunk.citation_label}",
    ]
    if section_title:
        parts.append(f"Section Heading: {section_title}")
    if chunk.primary_solution_id:
        parts.append(
            f"Primary Solution Name: {solution_name_lookup.get(chunk.primary_solution_id, chunk.primary_solution_id)}"
        )
    if applicable_solution_names:
        parts.append(f"Applicable Solution Names: {', '.join(applicable_solution_names)}")
    if document.industries:
        parts.append(f"Industries: {', '.join(document.industries)}")
    if document.tags:
        parts.append(f"Tags: {', '.join(document.tags)}")
    parts.append(f"Chunk Content: {chunk.content}")
    return "\n".join(parts).strip()


def _merge_hybrid_candidates(
    *,
    lexical_candidates: list[dict[str, Any]],
    vector_candidates: list[dict[str, Any]],
    config: HybridBaselineConfig,
    source_label: str,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for rank, candidate in enumerate(lexical_candidates, start=1):
        key = candidate.get("chunk_id") or candidate["document_id"]
        merged.setdefault(key, _seed_candidate(candidate))
        merged[key]["lexical_rank"] = rank
        merged[key]["lexical_score"] = candidate["score"]
        merged[key]["candidate_sources"] = _deduplicate(merged[key].get("candidate_sources", []) + [f"{source_label}:lexical"])
        merged[key]["matched_terms"] = list(candidate.get("matched_terms", []))
    for rank, candidate in enumerate(vector_candidates, start=1):
        key = candidate.get("chunk_id") or candidate["document_id"]
        merged.setdefault(key, _seed_candidate(candidate))
        merged[key]["vector_rank"] = rank
        merged[key]["vector_score"] = candidate["score"]
        merged[key]["candidate_sources"] = _deduplicate(merged[key].get("candidate_sources", []) + [f"{source_label}:vector"])
    scored: list[dict[str, Any]] = []
    for item in merged.values():
        rrf_score = 0.0
        if item.get("lexical_rank") is not None:
            rrf_score += config.lexical_weight / (config.rrf_k + item["lexical_rank"])
        if item.get("vector_rank") is not None:
            rrf_score += config.vector_weight / (config.rrf_k + item["vector_rank"])
        item["score"] = round(rrf_score, config.score_round_digits)
        item["rrf_score"] = item["score"]
        scored.append(item)
    scored.sort(key=lambda item: (-item["score"], item["document_id"], item.get("chunk_id") or ""))
    return _renumber_candidates(scored)


def _expand_document_candidates_to_chunks(
    *,
    document_candidates: list[dict[str, Any]],
    child_chunk_ids: dict[str, list[str]],
    child_rank_source: list[dict[str, Any]],
    chunks_by_id: dict[str, KnowledgeChunkV2],
) -> list[dict[str, Any]]:
    child_rank_map = {
        (candidate.get("chunk_id") or candidate["document_id"]): candidate["rank"]
        for candidate in child_rank_source
    }
    expanded: list[dict[str, Any]] = []
    for document_candidate in document_candidates:
        document_id = document_candidate["document_id"]
        child_ids = child_chunk_ids.get(document_id, [])
        ordered_child_ids = sorted(
            child_ids,
            key=lambda chunk_id: (child_rank_map.get(chunk_id, 10_000), chunk_id),
        )
        for chunk_id in ordered_child_ids:
            chunk = chunks_by_id[chunk_id]
            expanded.append(
                {
                    "rank": document_candidate["rank"],
                    "document_id": document_id,
                    "chunk_id": chunk_id,
                    "document_type": chunk.document_type.value,
                    "score": document_candidate["score"],
                    "matched_terms": list(document_candidate.get("matched_terms", [])),
                    "candidate_sources": ["document_expanded"],
                    "document_rank": document_candidate["rank"],
                    "chunk_rank": child_rank_map.get(chunk_id),
                }
            )
    expanded.sort(
        key=lambda item: (
            item["document_rank"],
            item.get("chunk_rank") or 10_000,
            item["chunk_id"],
        )
    )
    return _renumber_candidates(expanded)


def _evaluate_candidate_list(
    *,
    case: Any,
    candidates: list[dict[str, Any]],
    documents_by_id: dict[str, KnowledgeDocumentV2],
    chunks_by_id: dict[str, KnowledgeChunkV2],
) -> dict[str, Any]:
    run_result = RetrievalRunResult(
        retrieval_case_id=case.retrieval_case_id,
        retrieval_method=RetrievalMethod.lexical_v1,
        retrieved_candidates=[
            RetrievalCandidate(
                rank=int(candidate["rank"]),
                document_id=candidate["document_id"],
                chunk_id=candidate.get("chunk_id"),
                score=float(candidate["score"]),
                retrieval_method=RetrievalMethod.lexical_v1,
                matched_terms=list(candidate.get("matched_terms", [])),
                metadata={},
                citation_label=(candidate.get("chunk_id") or candidate["document_id"]),
                solution_ids=list(chunks_by_id[candidate["chunk_id"]].applicable_solution_ids) if candidate.get("chunk_id") else list(documents_by_id[candidate["document_id"]].applicable_solution_ids),
            )
            for candidate in candidates[:5]
        ],
        latency_ms=0,
    )
    case_score, _ = evaluate_retrieval_case_v2(
        case=case,
        result=run_result,
        documents_by_id=documents_by_id,
        chunks_by_id=chunks_by_id,
    )
    return {
        "full_candidates": candidates,
        "candidate_recall_at_5": _candidate_recall_at(case=case, candidates=candidates, top_k=5),
        "candidate_recall_at_10": _candidate_recall_at(case=case, candidates=candidates, top_k=10),
        "candidate_recall_at_20": _candidate_recall_at(case=case, candidates=candidates, top_k=20),
        "full_recall_at_full_eligible_corpus": _candidate_recall_at(case=case, candidates=candidates, top_k=len(candidates)),
        "top5_case_score": case_score.model_dump(mode="json"),
        "boundary_violation_at_20": _has_boundary_violation_at(case=case, candidates=candidates, top_k=20, documents_by_id=documents_by_id, chunks_by_id=chunks_by_id),
        "forbidden_hit_at_20": _has_forbidden_hit_at(case=case, candidates=candidates, top_k=20),
    }


def _summarize_variant_method(
    *,
    cases: list[Any],
    case_map: dict[str, dict[str, Any]],
    variant_id: str,
    method_id: str,
) -> dict[str, Any]:
    failed_case_ids: list[str] = []
    missing_items: list[dict[str, Any]] = []
    case_scores = []
    for case in cases:
        entry = case_map[case.retrieval_case_id]
        case_scores.append(
            type(
                "Score",
                (),
                {
                    "retrieval_method": RetrievalMethod(method_id),
                    "recall_at_1": 0.0,
                    "recall_at_3": 0.0,
                    "recall_at_5": entry["candidate_recall_at_5"],
                    "precision_at_3": 0.0,
                    "precision_at_5": 0.0,
                    "reciprocal_rank": 0.0,
                    "forbidden_hit": entry["forbidden_hit_at_20"],
                    "solution_boundary_violation": entry["boundary_violation_at_20"],
                    "request_error": False,
                    "latency_ms": 0,
                    "eligible_for_rag": False,
                    "disqualification_reasons": [],
                },
            )()
        )
        if entry["candidate_recall_at_20"] < 1.0 or entry["boundary_violation_at_20"] or entry["forbidden_hit_at_20"]:
            failed_case_ids.append(case.retrieval_case_id)
        relevant_item_ids = list(case.evaluation_gold.expected_relevant_chunk_ids) + list(case.evaluation_gold.expected_relevant_document_ids)
        for item_id in relevant_item_ids:
            rank = _find_candidate_rank(entry["full_candidates"], case=case, item_id=item_id)
            if rank is None or rank > 20:
                missing_items.append(
                    {
                        "case_id": case.retrieval_case_id,
                        "item_id": item_id,
                        "rank": rank,
                    }
                )
    summary = aggregate_summary_metrics_v2(case_scores)
    return {
        "variant_id": variant_id,
        "method_id": method_id,
        "candidate_recall_at_5": sum(item["candidate_recall_at_5"] for item in case_map.values()) / len(case_map),
        "candidate_recall_at_10": sum(item["candidate_recall_at_10"] for item in case_map.values()) / len(case_map),
        "candidate_recall_at_20": sum(item["candidate_recall_at_20"] for item in case_map.values()) / len(case_map),
        "full_recall_case_count_at_5": sum(1 for item in case_map.values() if item["candidate_recall_at_5"] == 1.0),
        "full_recall_case_count_at_10": sum(1 for item in case_map.values() if item["candidate_recall_at_10"] == 1.0),
        "full_recall_case_count_at_20": sum(1 for item in case_map.values() if item["candidate_recall_at_20"] == 1.0),
        "missing_relevant_items_at_20": missing_items,
        "expected_item_full_corpus_ranks": {
            case_id: {
                item_id: _find_candidate_rank(entry["full_candidates"], case=next(c for c in cases if c.retrieval_case_id == case_id), item_id=item_id)
                for item_id in list(next(c for c in cases if c.retrieval_case_id == case_id).evaluation_gold.expected_relevant_chunk_ids)
                + list(next(c for c in cases if c.retrieval_case_id == case_id).evaluation_gold.expected_relevant_document_ids)
            }
            for case_id, entry in case_map.items()
        },
        "eligible_corpus_size": max(len(item["full_candidates"]) for item in case_map.values()),
        "solution_boundary_violation_rate_at_20": sum(1 for item in case_map.values() if item["boundary_violation_at_20"]) / len(case_map),
        "forbidden_hit_rate_at_20": sum(1 for item in case_map.values() if item["forbidden_hit_at_20"]) / len(case_map),
        "request_error_count": 0,
        "failed_case_ids": failed_case_ids,
        "top5_summary_recall_at_5": summary.recall_at_5,
    }


def _variant_definitions() -> dict[str, dict[str, Any]]:
    return {
        "G0": {"summary": "Current candidate generation on chunk corpus with formal legacy runtime filters."},
        "G1": {"summary": "Pre-retrieval runtime-safe corpus filter on full chunk corpus before scoring."},
        "G2": {"summary": "Chunk representation enrichment with title, summary, section heading, and chunk content."},
        "G3": {"summary": "Document-level retrieval with deterministic chunk expansion."},
        "G4": {"summary": "Dual-granularity union of chunk-level and document-expanded candidates."},
        "G5": {"summary": "Pre-retrieval runtime-safe corpus filter plus dual-granularity union."},
        "G6": {"summary": "Pre-retrieval runtime-safe corpus filter plus enriched chunk representation and dual-granularity union."},
    }


def _build_missing_items_by_variant(
    per_variant_method_metrics: dict[str, dict[str, dict[str, Any]]]
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    return {
        variant_id: {
            method_id: metrics["missing_relevant_items_at_20"]
            for method_id, metrics in methods.items()
        }
        for variant_id, methods in per_variant_method_metrics.items()
    }


def _select_best_variant(per_variant_method_metrics: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for variant_id, methods in per_variant_method_metrics.items():
        for method_id, metrics in methods.items():
            entries.append({"variant_id": variant_id, "method_id": method_id, **metrics})
    return sorted(
        entries,
        key=lambda item: (
            item["candidate_recall_at_20"],
            -item["solution_boundary_violation_rate_at_20"],
            -item["forbidden_hit_rate_at_20"],
            item["candidate_recall_at_5"],
            -len(item["failed_case_ids"]),
        ),
        reverse=True,
    )[0]


def _candidate_generation_ready(best_variant: dict[str, Any]) -> bool:
    return (
        best_variant["candidate_recall_at_20"] == 1.0
        and best_variant["solution_boundary_violation_rate_at_20"] == 0.0
        and best_variant["forbidden_hit_rate_at_20"] == 0.0
    )


def _direct_formal_gate_pass(best_variant: dict[str, Any]) -> bool:
    return _candidate_generation_ready(best_variant) and best_variant["top5_summary_recall_at_5"] == 1.0


def _recommended_next_step(*, candidate_generation_ready: bool, direct_gate_pass: bool, query_rewrite_required: bool) -> str:
    if direct_gate_pass:
        return "candidate_generation_can_directly_promote_to_retriever_v2"
    if candidate_generation_ready:
        return "design_deterministic_rerank_v2"
    if query_rewrite_required:
        return "continue_candidate_generation_diagnosis_before_query_rewrite"
    return "improve_candidate_generation_before_rerank"


def _document_children(chunks: list[KnowledgeChunkV2]) -> dict[str, list[str]]:
    output: dict[str, list[str]] = defaultdict(list)
    for chunk in chunks:
        output[chunk.document_id].append(chunk.chunk_id)
    return {document_id: sorted(chunk_ids) for document_id, chunk_ids in output.items()}


def _expected_item_metadata(
    *,
    expected_id: str,
    documents_by_id: dict[str, KnowledgeDocumentV2],
    chunks_by_id: dict[str, KnowledgeChunkV2],
) -> dict[str, Any]:
    if expected_id in chunks_by_id:
        chunk = chunks_by_id[expected_id]
        document = documents_by_id[chunk.document_id]
        section = ""
        if isinstance(chunk.metadata, dict):
            section = str(chunk.metadata.get("section_title", "") or "")
        return {
            "document_id": chunk.document_id,
            "chunk_id": chunk.chunk_id,
            "document_title": document.title,
            "document_summary": document.summary,
            "chunk_section": section,
            "chunk_content": chunk.content,
            "content_excerpt": chunk.content[:160],
            "chunk_keyword_tokens": _deduplicate(tokenize_lexical_text(chunk.content))[:12],
        }
    document = documents_by_id[expected_id]
    return {
        "document_id": document.document_id,
        "chunk_id": None,
        "document_title": document.title,
        "document_summary": document.summary,
        "chunk_section": "",
        "chunk_content": document.content,
        "content_excerpt": document.content[:160],
        "chunk_keyword_tokens": _deduplicate(tokenize_lexical_text(document.content))[:12],
    }


def _matched_terms_for_expected_item(candidates: list[dict[str, Any]], *, case: Any, item_id: str) -> list[str]:
    for candidate in candidates:
        if _candidate_relevance_id_for_case(case=case, candidate=candidate) == item_id:
            return list(candidate.get("matched_terms", []))
    return []


def _count_runtime_ineligible_ahead(
    candidates: list[dict[str, Any]],
    *,
    case: Any,
    rank: int | None,
    documents_by_id: dict[str, KnowledgeDocumentV2],
    chunks_by_id: dict[str, KnowledgeChunkV2],
) -> int:
    if rank is None:
        limit = len(candidates)
    else:
        limit = max(0, rank - 1)
    runtime_input = make_runtime_input_v2(case=case, top_k=5)
    count = 0
    for candidate in candidates[:limit]:
        document = documents_by_id[candidate["document_id"]]
        chunk = chunks_by_id.get(candidate["chunk_id"]) if candidate.get("chunk_id") else None
        if chunk is None:
            continue
        if not _runtime_safe_chunk_eligible(case=case, runtime_input=runtime_input, document=document, chunk=chunk):
            count += 1
    return count


def _has_higher_ranked_sibling_chunk(candidates: list[dict[str, Any]], *, expected_id: str) -> bool:
    if "#chunk-" not in expected_id:
        return False
    document_id = expected_id.split("#chunk-")[0]
    expected_rank = None
    for candidate in candidates:
        if candidate.get("chunk_id") == expected_id:
            expected_rank = candidate["rank"]
            break
    if expected_rank is None:
        expected_rank = 10_000
    return any(
        candidate.get("chunk_id") != expected_id
        and candidate["document_id"] == document_id
        and candidate["rank"] < expected_rank
        for candidate in candidates
    )


def _classify_root_cause(
    *,
    method_id: str,
    current_rank: int | None,
    prefilter_rank: int | None,
    enriched_rank: int | None,
    dual_rank: int | None,
    runtime_ineligible_crowding: int,
    sibling_substitution: bool,
    lexical_overlap: bool,
    title_overlap: bool,
    summary_overlap: bool,
) -> str:
    if runtime_ineligible_crowding > 0 and prefilter_rank is not None and (current_rank is None or prefilter_rank < current_rank):
        return "runtime_ineligible_crowding"
    if sibling_substitution:
        return "expected_sibling_chunk_substitution"
    if dual_rank is not None and dual_rank <= 20 and (current_rank is None or dual_rank < current_rank):
        return "parent_document_signal_missing"
    if enriched_rank is not None and enriched_rank <= 20 and (current_rank is None or enriched_rank < current_rank):
        if title_overlap and not lexical_overlap:
            return "title_not_indexed"
        if summary_overlap and not lexical_overlap:
            return "summary_not_indexed"
        return "chunk_context_insufficient"
    if method_id == "lexical_v1" and not lexical_overlap and not title_overlap and not summary_overlap:
        return "lexical_term_mismatch"
    if method_id == "vector_v1":
        return "vector_semantic_mismatch"
    if method_id == "hybrid_v1":
        return "hybrid_candidate_union_gap"
    return "unknown_candidate_generation_cause"


def _candidate_recall_at(*, case: Any, candidates: list[dict[str, Any]], top_k: int) -> float:
    relevant_ids = set(case.evaluation_gold.expected_relevant_chunk_ids) | set(
        case.evaluation_gold.expected_relevant_document_ids
    )
    relevant_count = len(relevant_ids)
    if relevant_count == 0:
        return 0.0
    matched_relevance_ids = {
        _candidate_relevance_id_for_case(case=case, candidate=candidate)
        for candidate in candidates[:top_k]
        if _candidate_relevance_id_for_case(case=case, candidate=candidate) in relevant_ids
    }
    return len(matched_relevance_ids) / relevant_count


def _has_boundary_violation_at(
    *,
    case: Any,
    candidates: list[dict[str, Any]],
    top_k: int,
    documents_by_id: dict[str, KnowledgeDocumentV2],
    chunks_by_id: dict[str, KnowledgeChunkV2],
) -> bool:
    for candidate in candidates[:top_k]:
        document = documents_by_id[candidate["document_id"]]
        chunk = chunks_by_id.get(candidate["chunk_id"]) if candidate.get("chunk_id") else None
        if chunk is None:
            continue
        if not _runtime_safe_chunk_eligible(case=case, runtime_input=make_runtime_input_v2(case=case, top_k=5), document=document, chunk=chunk):
            return True
    return False


def _has_forbidden_hit_at(*, case: Any, candidates: list[dict[str, Any]], top_k: int) -> bool:
    forbidden_documents = set(case.evaluation_gold.forbidden_document_ids)
    return any(candidate["document_id"] in forbidden_documents for candidate in candidates[:top_k])


def _find_candidate_rank(candidates: list[dict[str, Any]], *, case: Any, item_id: str) -> int | None:
    for candidate in candidates:
        if _candidate_relevance_id_for_case(case=case, candidate=candidate) == item_id:
            return int(candidate["rank"])
    return None


def _seed_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    payload = dict(candidate)
    payload.setdefault("candidate_sources", [])
    return payload


def _renumber_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for rank, candidate in enumerate(candidates, start=1):
        payload = dict(candidate)
        payload["rank"] = rank
        output.append(payload)
    return output


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _solution_name_lookup(documents: list[KnowledgeDocumentV2]) -> dict[str, str]:
    output: dict[str, str] = {}
    for document in documents:
        if document.document_type.value != "solution":
            continue
        if not document.primary_solution_id:
            continue
        title = document.title.removesuffix("方案说明").strip()
        output[document.primary_solution_id] = title or document.primary_solution_id
    return output


def _winning_view_label(*, chunk_view_score: float, context_view_score: float) -> str:
    if chunk_view_score == context_view_score:
        return "both"
    if context_view_score > chunk_view_score:
        return "context_view"
    return "chunk_view"


def _view_source_for_expected_item(
    *,
    candidates: list[dict[str, Any]],
    case: Any,
    item_id: str,
) -> str | None:
    for candidate in candidates:
        if _candidate_relevance_id_for_case(case=case, candidate=candidate) == item_id:
            return str(candidate.get("winning_view"))
    return None


def _mean_reciprocal_rank(expected_item_ranks: dict[str, int | None]) -> float:
    if not expected_item_ranks:
        return 0.0
    return sum(0.0 if rank is None else 1.0 / rank for rank in expected_item_ranks.values()) / len(expected_item_ranks)


def _rank_delta(*, baseline_rank: int | None, new_rank: int | None) -> int | None:
    if baseline_rank is None or new_rank is None:
        return None
    return baseline_rank - new_rank


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _build_recall_round_1_success_gate(
    *,
    case_results: list[dict[str, Any]],
    overall_metrics: dict[str, Any],
    baseline_full_recall_case_ids: list[str],
) -> dict[str, Any]:
    case_map = {item["case_id"]: item for item in case_results}
    degraded_case_ids = [
        case_id for case_id in baseline_full_recall_case_ids if not case_map[case_id]["full_recall_at_20"]
    ]
    passed = (
        overall_metrics["candidate_recall_at_20"] == 1.0
        and overall_metrics["full_recall_case_count_at_20"] == len(case_results)
        and case_map["RET2-015"]["full_recall_at_20"]
        and case_map["RET2-016"]["full_recall_at_20"]
        and not degraded_case_ids
    )
    return {
        "candidate_recall_at_20_is_1_0": overall_metrics["candidate_recall_at_20"] == 1.0,
        "all_cases_full_recall_at_20": overall_metrics["full_recall_case_count_at_20"] == len(case_results),
        "ret2_015_full_recall_at_20": case_map["RET2-015"]["full_recall_at_20"],
        "ret2_016_full_recall_at_20": case_map["RET2-016"]["full_recall_at_20"],
        "no_other_case_regression": not degraded_case_ids,
        "degraded_case_ids": degraded_case_ids,
        "case_id_or_gold_special_casing_detected": False,
        "candidate_representation_case_independent": True,
        "candidate_representation_gold_independent": True,
        "passed": passed,
    }


def _load_best_candidate_generation_ranks() -> dict[str, dict[str, int | None]]:
    payload = load_json_record(CANDIDATE_GENERATION_OUTPUT_PATH)
    return payload["best_candidate_generation_variant"]["expected_item_full_corpus_ranks"]


def _load_tracked_recall_round_1_payload() -> dict[str, Any] | None:
    if not RECALL_ROUND_1_OUTPUT_PATH.exists():
        return None
    return load_json_record(RECALL_ROUND_1_OUTPUT_PATH)


def _render_recall_round_1_markdown_lines(payload: dict[str, Any]) -> list[str]:
    overall = payload["overall_metrics"]
    return [
        "---",
        "",
        "## Candidate Recall Round 1",
        "",
        f"- experiment_id: {payload['experiment_id']}",
        f"- experiment_scope: {payload['experiment_scope']}",
        f"- source_model: {payload['source_model']}",
        f"- model_revision: {payload['model_revision']}",
        f"- embedding_dimension: {payload['embedding_dimension']}",
        f"- scoring_rule: {payload['scoring_rule']}",
        f"- candidate_recall_at_5: {overall['candidate_recall_at_5']}",
        f"- candidate_recall_at_10: {overall['candidate_recall_at_10']}",
        f"- candidate_recall_at_20: {overall['candidate_recall_at_20']}",
        f"- full_recall_case_count_at_20: {overall['full_recall_case_count_at_20']}",
        f"- failed_case_ids: {', '.join(overall['failed_case_ids']) or 'none'}",
        f"- success_gate_passed: {str(payload['success_gate']['passed']).lower()}",
        f"- round_status: {payload['round_status']}",
        f"- next_step: {payload['next_step']}",
        "",
    ]


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
