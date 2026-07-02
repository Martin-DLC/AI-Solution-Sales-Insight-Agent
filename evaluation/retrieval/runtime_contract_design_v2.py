from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evaluation.retrieval.candidate_generation_v2 import (
    CANDIDATE_GENERATION_OUTPUT_PATH,
    _evaluate_candidate_list,
    _load_experiment_context,
    _sha256,
)
from evaluation.retrieval.diagnostics_v2 import _candidate_relevance_id_for_case, compute_formal_result_hashes
from evaluation.retrieval.runner_v2 import make_runtime_input_v2
from evaluation.retrieval.separability_v2 import (
    RUNTIME_RULE_IDS,
    SEPARABILITY_OUTPUT_PATH,
    FIELD_VARIANT_IDS,
    QUERY_VARIANT_IDS,
    METHOD_IDS,
    COMBINED_VARIANTS,
    SeparabilityExperimentRunner,
    _relevant_ids,
)
from evaluation.retrieval.storage import diff_json_objects, load_json_record, write_json_atomic
from knowledge_base import KnowledgeChunkV2, KnowledgeDocumentV2


RUNTIME_CONTRACT_PROPOSAL_OUTPUT_PATH = Path(
    "data/evaluation/retrieval/retrieval_runtime_contract_v2_1_proposal.json"
)
RUNTIME_CONTRACT_PROPOSAL_DOC_PATH = Path("docs/32_Retrieval_Runtime_Boundary_Contract_V2_1.md")


CURRENT_RUNTIME_FIELDS = (
    "operational_solution_scope",
    "allowed_document_types",
    "industries",
    "tags",
    "effective_on",
    "operational_filters",
)

CURRENT_CANDIDATE_FIELDS = (
    "scope_type",
    "primary_solution_id",
    "applicable_solution_ids",
    "excluded_solution_ids",
    "document_type",
    "industries",
    "tags",
    "effective_on",
    "global_policy_flag",
    "cross_cutting_requirement_flag",
    "citation_label",
)


@dataclass(frozen=True)
class CandidateRecord:
    case_id: str
    method_id: str
    document: KnowledgeDocumentV2
    chunk: KnowledgeChunkV2 | None
    candidate: KnowledgeChunkV2 | KnowledgeDocumentV2
    candidate_id: str
    relevant: bool
    boundary: bool


def build_plan_payload() -> dict[str, Any]:
    return {
        "mode": "plan",
        "proposal_version": "retrieval_runtime_boundary_contract_v2_1_proposal_v1",
        "diagnostic_only": True,
        "formal_result_hashes": compute_formal_result_hashes(),
        "separability_analysis_hash": _sha256(SEPARABILITY_OUTPUT_PATH),
        "candidate_generation_analysis_hash": _sha256(CANDIDATE_GENERATION_OUTPUT_PATH),
        "planned_outputs": {
            "json": str(RUNTIME_CONTRACT_PROPOSAL_OUTPUT_PATH),
            "doc": str(RUNTIME_CONTRACT_PROPOSAL_DOC_PATH),
        },
        "allowed_current_runtime_fields": list(CURRENT_RUNTIME_FIELDS),
        "allowed_current_candidate_fields": list(CURRENT_CANDIDATE_FIELDS),
    }


def build_runtime_contract_design_payload() -> dict[str, Any]:
    context = _load_experiment_context()
    separability = load_json_record(SEPARABILITY_OUTPUT_PATH)
    runner = SeparabilityExperimentRunner(context=context)
    candidate_records = _collect_candidate_records(context=context, runner=runner)

    joinability = _build_joinability_matrix()
    conflict_clusters = _build_conflict_clusters(separability=separability, context=context)
    field_proposals = _build_candidate_field_proposals()
    contract_variants = _build_contract_variants(context=context, candidate_records=candidate_records)
    counterfactual_results = _build_counterfactual_results(contract_variants)
    recommended_variant = _select_recommended_contract(counterfactual_results)

    proposed_scope = recommended_variant["upgrade_scope"]
    runtime_schema_changes = recommended_variant["runtime_schema_changes"]
    candidate_metadata_changes = recommended_variant["candidate_metadata_changes"]

    return {
        "proposal_version": "retrieval_runtime_boundary_contract_v2_1_proposal_v1",
        "diagnostic_only": True,
        "evidence_classification": "P1_content_explainable_not_blind_validated",
        "contract_status": "feasible_contract_hypothesis",
        "runtime_matching_rule_uses_gold": False,
        "candidate_assignment_rule_reads_gold_fields": False,
        "authoring_process_was_blind_to_cases_and_gold": False,
        "evaluation_uses_gold_for_measurement": True,
        "assignment_rule_case_independent": True,
        "assignment_rule_uses_candidate_static_fields_only": True,
        "assignment_rule_has_id_hardcoding": False,
        "assignment_rule_designed_after_outcome_review": True,
        "blind_authoring_validated": False,
        "independent_validation_completed": False,
        "deployment_validated": False,
        "ready_for_blind_authoring": True,
        "formal_result_hashes": compute_formal_result_hashes(),
        "separability_analysis_hash": _sha256(SEPARABILITY_OUTPUT_PATH),
        "runtime_candidate_joinability_matrix": joinability,
        "conflict_clusters": conflict_clusters,
        "current_contract_limitations": [
            "Current runtime fields can express scope, document type, industry, tags, and effective date, but they do not encode how a candidate should relate to a partial operational scope.",
            "Strict subset filtering removes boundary candidates but also removes relevant cross-cutting and multi-solution evidence that is safe when the primary solution remains in scope.",
            "The same chunk can be relevant in a full two-solution runtime scope and boundary-violating in a one-solution runtime scope, which means field semantics must be case-independent but runtime-match-aware.",
        ],
        "candidate_field_proposals": field_proposals,
        "contract_variants": [item["variant_definition"] for item in contract_variants],
        "counterfactual_results": counterfactual_results,
        "proposed_upgrade_scope": proposed_scope,
        "final_upgrade_scope_decision": "pending_blind_authoring_validation",
        "recommended_next_step": "build_blind_authoring_packet_freeze_labels_and_evaluate",
        "recommended_metadata_granularity": "document_default_with_chunk_override",
        "runtime_schema_changes": runtime_schema_changes,
        "candidate_metadata_changes": candidate_metadata_changes,
        "migration_requirements": [
            "Author runtime_scope_match_mode for candidate records using knowledge-authoring review of cross-cutting and multi-solution documents/chunks.",
            "Preserve a single static metadata value per candidate; do not vary the field by retrieval case.",
            "Backfill v2.1 metadata without touching frozen v2 benchmark data or formal result artifacts.",
        ],
        "backward_compatibility_status": "design_incomplete",
        "default_behavior_status": "pending_blind_authoring_design",
        "manual_review_required_for": [
            "multi_solution",
            "cross_cutting_requirement",
            "ambiguous_document_chunk_semantics",
        ],
        "backward_compatibility": {
            "runtime_side": "No new runtime field is required in the recommended variant; existing runtime_context remains backward compatible.",
            "candidate_side": "Migration defaults are not finalized. Partial-overlap records, multi-solution evidence, and cross-cutting requirements still require blind authoring design before production rollout.",
        },
        "ret2_015_016_status": {
            "boundary_contract_resolves_ret2_015": False,
            "boundary_contract_resolves_ret2_016": False,
            "recall_workstream_still_required": True,
            "notes": "RET2-015 and RET2-016 remain candidate-generation misses. Boundary contract upgrades do not add the missing candidates into Top-20.",
        },
        "boundary_contract_ready_for_versioning": False,
        "retriever_v2_ready_for_implementation": False,
        "architecture_c_status": "blocked",
        "limitations": [
            "This proposal is diagnostic-only and does not modify frozen v2 results, cases, KB, or retriever code.",
            "Counterfactual validation is run against the existing formal top-20 candidate pools; it does not solve RET2-015 or RET2-016 recall gaps.",
            "Candidate runtime_scope_match_mode can be inferred heuristically in the analysis, but the current proposal is still a post-hoc hypothesis rather than a blind-authored and independently validated production contract.",
        ],
    }


def render_runtime_contract_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Retrieval Runtime Boundary Contract V2.1")
    lines.append("")
    lines.append("## 证据等级")
    lines.append("")
    lines.append(f"- evidence_classification: {payload['evidence_classification']}")
    lines.append(f"- contract_status: {payload['contract_status']}")
    lines.append(f"- blind_authoring_validated: {str(payload['blind_authoring_validated']).lower()}")
    lines.append(f"- independent_validation_completed: {str(payload['independent_validation_completed']).lower()}")
    lines.append(f"- deployment_validated: {str(payload['deployment_validated']).lower()}")
    lines.append(f"- ready_for_blind_authoring: {str(payload['ready_for_blind_authoring']).lower()}")
    lines.append("")
    lines.append("## 证据等级与设计阶段泄漏限制")
    lines.append("")
    lines.append("- `runtime_scope_match_mode` 的推导函数当前不直接读取 Gold。")
    lines.append("- 同一 Candidate 的 mode 在当前实现中跨 Case 静态，不依赖 case_id 或 Candidate ID 硬编码。")
    lines.append("- 但本提案的规则形成过程读取了 Cases、Evaluation Gold、Boundary 标签和 Separability conflict clusters。")
    lines.append("- 因此当前结果属于 post-hoc design 风险下的反事实支持证据，不构成盲标验证或独立部署验证。")
    lines.append("- 下一步需要仅基于 KB 内容的 Blind Authoring Packet、标签冻结和独立评估。")
    lines.append("- RET2-015 / RET2-016 仍是独立的 Recall 工作流问题。")
    lines.append("- Architecture C 继续 blocked。")
    lines.append("")
    lines.append("## 为什么Runtime可识别不等于可分离")
    lines.append("")
    lines.append("- Strict Filter 能识别并过滤部分或全部违规候选，但现有字段组合会误伤合法 Relevant。")
    lines.append("- 误伤的根因不是单一排序问题，而是缺少“候选如何与局部 solution scope 匹配”的静态合同。")
    lines.append("")
    lines.append("## 当前字段Joinability")
    lines.append("")
    comparable = [row for row in payload["runtime_candidate_joinability_matrix"] if row["comparable"]]
    lines.append(f"- comparable_pairs: {len(comparable)} / {len(payload['runtime_candidate_joinability_matrix'])}")
    lines.append("- 现有最强可比链路：solution scope -> primary/applicable/excluded，document types -> document_type，industry -> industries，tags -> tags。")
    lines.append("- 缺失链路：没有字段表达 candidate 对“部分 operational scope”是可复用还是必须全量命中。")
    lines.append("")
    lines.append("## Strict Filter误伤原因")
    lines.append("")
    lines.append("- S1误伤18个 Relevant Candidate。")
    lines.append("- S3误伤30个 Relevant Candidate。")
    lines.append("- cross-cutting 与 multi-solution 证据中，部分记录应允许 primary solution in scope 即可复用，部分记录则必须 full applicable scope 才安全。")
    lines.append("")
    lines.append("## Cross-cutting证据语义")
    lines.append("")
    lines.append("- 不是所有 applicable_solution_ids 包含 scope 外 solution 的 cross-cutting 证据都应视为越界。")
    lines.append("- 安全与合规类 shared prerequisite 证据可以服务单一 solution scope。")
    lines.append("- unsupported / readiness 类跨方案约束如果需要依赖全部适用方案共同成立，则 partial overlap 不安全。")
    lines.append("")
    lines.append("## Multi-solution证据语义")
    lines.append("")
    lines.append("- multi-solution 证据至少分成两类：")
    lines.append("  - `primary_in_scope` 即可复用：实施 Playbook、参考案例。")
    lines.append("  - `full_applicable_scope` 才安全：需要所有列出方案共同成立的能力说明或边界说明。")
    lines.append("")
    lines.append("## 冲突簇")
    lines.append("")
    for cluster in payload["conflict_clusters"]:
        lines.append(
            f"- {cluster['conflict_cluster_id']}: requires_both_sides={str(cluster['requires_both_sides']).lower()}, "
            f"missing_runtime_signal={cluster['missing_runtime_signal']}, missing_candidate_signal={cluster['missing_candidate_signal']}"
        )
    lines.append("")
    lines.append("## Runtime-only方案")
    lines.append("")
    runtime_only = next(item for item in payload["counterfactual_results"] if item["contract_id"] == "C1")
    lines.append(
        f"- C1 retention={runtime_only['relevant_candidate_retention_rate']}, "
        f"boundary_removal={runtime_only['boundary_candidate_removal_rate']}, "
        f"deployable={str(runtime_only['deployable']).lower()}"
    )
    lines.append("")
    lines.append("## Metadata-only方案")
    lines.append("")
    metadata_only = next(item for item in payload["counterfactual_results"] if item["contract_id"] == "C2")
    lines.append(
        f"- C2 retention={metadata_only['relevant_candidate_retention_rate']}, "
        f"boundary_removal={metadata_only['boundary_candidate_removal_rate']}, "
        f"candidate_recall_at_20={metadata_only['candidate_recall_at_20']}, "
        f"deployable={str(metadata_only['deployable']).lower()}, "
        f"validated_contract={str(metadata_only['validated_contract']).lower()}, "
        f"hypothesis_supported={str(metadata_only['hypothesis_supported']).lower()}"
    )
    lines.append("")
    lines.append("## Paired方案")
    lines.append("")
    paired = next(item for item in payload["counterfactual_results"] if item["contract_id"] == "C3")
    lines.append(
        f"- C3 retention={paired['relevant_candidate_retention_rate']}, "
        f"boundary_removal={paired['boundary_candidate_removal_rate']}, "
        f"deployable={str(paired['deployable']).lower()}"
    )
    lines.append("")
    lines.append("## Oracle上界")
    lines.append("")
    oracle = next(item for item in payload["counterfactual_results"] if item["contract_id"] == "C4")
    lines.append(
        f"- C4 retention={oracle['relevant_candidate_retention_rate']}, "
        f"boundary_removal={oracle['boundary_candidate_removal_rate']}, "
        f"runtime_rule_uses_gold={str(oracle['runtime_rule_uses_gold']).lower()}"
    )
    lines.append("")
    lines.append("## 推荐合同字段")
    lines.append("")
    for proposal in payload["candidate_field_proposals"]:
        lines.append(
            f"- {proposal['field_name']} ({proposal['side']}): values={', '.join(proposal['allowed_values'])}"
        )
    lines.append("")
    lines.append("## 字段来源和维护责任")
    lines.append("")
    lines.append("- 当前拟议的最小升级范围仍是 candidate/knowledge metadata 字段，不新增 runtime schema 字段。")
    lines.append("- 推荐粒度：document_default_with_chunk_override。")
    lines.append("- Document 层提供默认值，Chunk 层允许覆盖；`KB-CAP-001` 已显示 document-only 粒度可能过粗。")
    lines.append("- Chunk override 必须是静态 Knowledge Metadata，不得随 Case 变化。")
    lines.append("- 当前不要求新增 runtime 字段。")
    lines.append("")
    lines.append("## Migration设计")
    lines.append("")
    for item in payload["migration_requirements"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## 向后兼容策略")
    lines.append("")
    lines.append(f"- backward_compatibility_status: {payload['backward_compatibility_status']}")
    lines.append(f"- default_behavior_status: {payload['default_behavior_status']}")
    lines.append(f"- runtime: {payload['backward_compatibility']['runtime_side']}")
    lines.append(f"- candidate: {payload['backward_compatibility']['candidate_side']}")
    lines.append(f"- manual_review_required_for: {', '.join(payload['manual_review_required_for'])}")
    lines.append("")
    lines.append("## RET2-015/016为何仍是独立问题")
    lines.append("")
    status = payload["ret2_015_016_status"]
    lines.append(f"- boundary_contract_resolves_ret2_015: {str(status['boundary_contract_resolves_ret2_015']).lower()}")
    lines.append(f"- boundary_contract_resolves_ret2_016: {str(status['boundary_contract_resolves_ret2_016']).lower()}")
    lines.append(f"- recall_workstream_still_required: {str(status['recall_workstream_still_required']).lower()}")
    lines.append("")
    lines.append("## 是否可进入Retriever v2实现")
    lines.append("")
    lines.append(f"- boundary_contract_ready_for_versioning: {str(payload['boundary_contract_ready_for_versioning']).lower()}")
    lines.append(f"- proposed_upgrade_scope: {payload['proposed_upgrade_scope']}")
    lines.append(f"- final_upgrade_scope_decision: {payload['final_upgrade_scope_decision']}")
    lines.append(f"- recommended_next_step: {payload['recommended_next_step']}")
    lines.append("- retriever_v2_ready_for_implementation: false")
    lines.append("")
    lines.append("## Architecture C状态")
    lines.append("")
    lines.append(f"- architecture_c_status: {payload['architecture_c_status']}")
    lines.append("")
    return "\n".join(lines)


def write_runtime_contract_outputs(payload: dict[str, Any]) -> None:
    write_json_atomic(RUNTIME_CONTRACT_PROPOSAL_OUTPUT_PATH, payload)
    RUNTIME_CONTRACT_PROPOSAL_DOC_PATH.write_text(render_runtime_contract_markdown(payload), encoding="utf-8")


def check_runtime_contract_outputs() -> tuple[bool, list[str]]:
    recomputed = build_runtime_contract_design_payload()
    differences: list[str] = []
    if not RUNTIME_CONTRACT_PROPOSAL_OUTPUT_PATH.exists():
        differences.append(f"Missing tracked JSON output: {RUNTIME_CONTRACT_PROPOSAL_OUTPUT_PATH}")
    else:
        tracked_json = load_json_record(RUNTIME_CONTRACT_PROPOSAL_OUTPUT_PATH)
        differences.extend(diff_json_objects(tracked_json, recomputed))
    rendered_markdown = render_runtime_contract_markdown(recomputed)
    if not RUNTIME_CONTRACT_PROPOSAL_DOC_PATH.exists():
        differences.append(f"Missing tracked Markdown output: {RUNTIME_CONTRACT_PROPOSAL_DOC_PATH}")
    else:
        tracked_markdown = RUNTIME_CONTRACT_PROPOSAL_DOC_PATH.read_text(encoding="utf-8")
        if tracked_markdown != rendered_markdown:
            differences.append(f"Markdown output drifted: {RUNTIME_CONTRACT_PROPOSAL_DOC_PATH}")
    return (not differences, differences)


def _build_joinability_matrix() -> list[dict[str, Any]]:
    semantics: dict[tuple[str, str], dict[str, Any]] = {
        ("operational_solution_scope", "primary_solution_id"): {
            "comparable": True,
            "comparison_semantics": "membership",
            "cardinality": "N:1",
            "nullability": "runtime_non_empty_candidate_nullable",
            "source_of_truth": "runtime_case_and_kb_metadata",
            "runtime_population_source": "runtime_context.operational_solution_scope",
            "candidate_population_source": "knowledge scope.primary_solution_id",
            "can_be_populated_without_gold": True,
            "generalizable_across_cases": True,
            "missing_signal": False,
            "false_positive_risk": "medium",
            "false_negative_risk": "medium",
        },
        ("operational_solution_scope", "applicable_solution_ids"): {
            "comparable": True,
            "comparison_semantics": "subset_or_overlap",
            "cardinality": "N:N",
            "nullability": "non_empty",
            "source_of_truth": "runtime_case_and_kb_metadata",
            "runtime_population_source": "runtime_context.operational_solution_scope",
            "candidate_population_source": "knowledge scope.applicable_solution_ids",
            "can_be_populated_without_gold": True,
            "generalizable_across_cases": True,
            "missing_signal": False,
            "false_positive_risk": "high",
            "false_negative_risk": "high",
        },
        ("operational_solution_scope", "excluded_solution_ids"): {
            "comparable": True,
            "comparison_semantics": "disjointness",
            "cardinality": "N:N",
            "nullability": "candidate_optional",
            "source_of_truth": "runtime_case_and_kb_metadata",
            "runtime_population_source": "runtime_context.operational_solution_scope",
            "candidate_population_source": "knowledge scope.excluded_solution_ids",
            "can_be_populated_without_gold": True,
            "generalizable_across_cases": True,
            "missing_signal": False,
            "false_positive_risk": "low",
            "false_negative_risk": "medium",
        },
        ("allowed_document_types", "document_type"): {
            "comparable": True,
            "comparison_semantics": "membership",
            "cardinality": "N:1",
            "nullability": "runtime_optional_candidate_non_null",
            "source_of_truth": "runtime_case_and_kb_metadata",
            "runtime_population_source": "runtime_context.allowed_document_types",
            "candidate_population_source": "knowledge document_type",
            "can_be_populated_without_gold": True,
            "generalizable_across_cases": True,
            "missing_signal": False,
            "false_positive_risk": "medium",
            "false_negative_risk": "low",
        },
        ("industries", "industries"): {
            "comparable": True,
            "comparison_semantics": "overlap",
            "cardinality": "N:N",
            "nullability": "both_optional",
            "source_of_truth": "runtime_case_and_kb_metadata",
            "runtime_population_source": "runtime_context.industries",
            "candidate_population_source": "knowledge industries",
            "can_be_populated_without_gold": True,
            "generalizable_across_cases": True,
            "missing_signal": False,
            "false_positive_risk": "low",
            "false_negative_risk": "low",
        },
        ("tags", "tags"): {
            "comparable": True,
            "comparison_semantics": "overlap",
            "cardinality": "N:N",
            "nullability": "both_optional",
            "source_of_truth": "runtime_case_and_kb_metadata",
            "runtime_population_source": "runtime_context.tags",
            "candidate_population_source": "knowledge tags",
            "can_be_populated_without_gold": True,
            "generalizable_across_cases": True,
            "missing_signal": False,
            "false_positive_risk": "low",
            "false_negative_risk": "low",
        },
        ("effective_on", "effective_on"): {
            "comparable": True,
            "comparison_semantics": "active_as_of",
            "cardinality": "1:1",
            "nullability": "runtime_non_null_candidate_derived",
            "source_of_truth": "runtime_case_and_kb_metadata",
            "runtime_population_source": "runtime_context.effective_on",
            "candidate_population_source": "document effective_from/effective_until",
            "can_be_populated_without_gold": True,
            "generalizable_across_cases": True,
            "missing_signal": False,
            "false_positive_risk": "low",
            "false_negative_risk": "low",
        },
        ("operational_solution_scope", "scope_type"): {
            "comparable": True,
            "comparison_semantics": "requires_extra_policy",
            "cardinality": "N:1",
            "nullability": "candidate_non_null",
            "source_of_truth": "kb_metadata_only",
            "runtime_population_source": "runtime_context.operational_solution_scope",
            "candidate_population_source": "knowledge scope.scope_type",
            "can_be_populated_without_gold": True,
            "generalizable_across_cases": True,
            "missing_signal": True,
            "false_positive_risk": "high",
            "false_negative_risk": "high",
        },
        ("allowed_document_types", "citation_label"): {
            "comparable": True,
            "comparison_semantics": "weak_proxy_only",
            "cardinality": "N:1",
            "nullability": "candidate_non_null",
            "source_of_truth": "mixed",
            "runtime_population_source": "runtime_context.allowed_document_types",
            "candidate_population_source": "chunk citation_label",
            "can_be_populated_without_gold": True,
            "generalizable_across_cases": True,
            "missing_signal": True,
            "false_positive_risk": "medium",
            "false_negative_risk": "medium",
        },
    }

    matrix: list[dict[str, Any]] = []
    for runtime_field in CURRENT_RUNTIME_FIELDS:
        for candidate_field in CURRENT_CANDIDATE_FIELDS:
            config = semantics.get((runtime_field, candidate_field))
            if config is None:
                matrix.append(
                    {
                        "runtime_field": runtime_field,
                        "candidate_field": candidate_field,
                        "comparable": False,
                        "comparison_semantics": "none",
                        "cardinality": "n/a",
                        "nullability": "unknown",
                        "source_of_truth": "n/a",
                        "runtime_population_source": "runtime_context",
                        "candidate_population_source": "candidate_metadata",
                        "can_be_populated_without_gold": True,
                        "generalizable_across_cases": True,
                        "missing_signal": False,
                        "false_positive_risk": "n/a",
                        "false_negative_risk": "n/a",
                    }
                )
                continue
            matrix.append({"runtime_field": runtime_field, "candidate_field": candidate_field, **config})
    return matrix


def _build_conflict_clusters(*, separability: dict[str, Any], context: Any) -> list[dict[str, Any]]:
    filtered = []
    for rule_id in ("S1", "S3"):
        filtered.extend(separability["runtime_filter_false_exclusion_analysis"][rule_id]["filtered_candidates"])

    by_candidate_key: defaultdict[tuple[str, str | None], dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"relevant": [], "boundary": []}
    )
    by_scope_family: defaultdict[tuple[str, str], dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"relevant": [], "boundary": []}
    )
    for item in filtered:
        if item["filtered_category"] == "irrelevant_safe_candidate":
            continue
        label = "relevant" if item["filtered_category"] == "relevant_gold_candidate" else "boundary"
        candidate_key = (item["document_id"], item["chunk_id"])
        by_candidate_key[candidate_key][label].append(item)
        scope_family = (item["scope_type"], _document_type_for_item(context=context, item=item))
        by_scope_family[scope_family][label].append(item)

    clusters: list[dict[str, Any]] = []
    cluster_index = 1

    for (document_id, chunk_id), grouped in sorted(by_candidate_key.items()):
        if not grouped["relevant"] or not grouped["boundary"]:
            continue
        clusters.append(
            {
                "conflict_cluster_id": f"CC-{cluster_index:03d}",
                "boundary_candidates": _candidate_refs(grouped["boundary"]),
                "relevant_candidates": _candidate_refs(grouped["relevant"]),
                "indistinguishable_existing_fields": [
                    "scope_type",
                    "primary_solution_id",
                    "applicable_solution_ids",
                    "excluded_solution_ids",
                    "document_type",
                    "citation_label",
                ],
                "distinguishing_existing_fields": [
                    "operational_solution_scope",
                    "allowed_document_types",
                    "query intent (not structured as runtime field)",
                ],
                "missing_runtime_signal": False,
                "missing_candidate_signal": True,
                "requires_both_sides": False,
                "cannot_be_resolved_without_gold": False,
            }
        )
        cluster_index += 1

    by_scope_only: defaultdict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"relevant": [], "boundary": []}
    )
    for item in filtered:
        if item["filtered_category"] == "irrelevant_safe_candidate":
            continue
        label = "relevant" if item["filtered_category"] == "relevant_gold_candidate" else "boundary"
        by_scope_only[item["scope_type"]][label].append(item)

    for scope_type, grouped in sorted(by_scope_only.items()):
        if not grouped["relevant"] or not grouped["boundary"]:
            continue
        clusters.append(
            {
                "conflict_cluster_id": f"CC-{cluster_index:03d}",
                "boundary_candidates": _candidate_refs(grouped["boundary"]),
                "relevant_candidates": _candidate_refs(grouped["relevant"]),
                "indistinguishable_existing_fields": [
                    "scope_type",
                    "partial operational scope overlap",
                ],
                "distinguishing_existing_fields": [
                    "document_type",
                    "citation_label",
                    "summary/title semantics",
                ],
                "missing_runtime_signal": False,
                "missing_candidate_signal": True,
                "requires_both_sides": False,
                "cannot_be_resolved_without_gold": False,
            }
        )
        cluster_index += 1

    return clusters


def _build_candidate_field_proposals() -> list[dict[str, Any]]:
    return [
        {
            "field_name": "runtime_scope_match_mode",
            "side": "candidate",
            "business_definition": (
                "Defines whether a candidate can safely serve a narrower operational solution scope with only its primary solution in scope, "
                "or whether all listed applicable solutions must be present at runtime."
            ),
            "allowed_values": [
                "primary_in_scope",
                "full_applicable_scope",
                "global_reusable",
            ],
            "examples": [
                {
                    "candidate_kind": "security_compliance cross-cutting prerequisite",
                    "value": "primary_in_scope",
                },
                {
                    "candidate_kind": "multi-solution capability explanation requiring both products together",
                    "value": "full_applicable_scope",
                },
            ],
            "population_owner": "knowledge_authoring",
            "population_time": "knowledge_document_or_chunk_release",
            "deterministic_derivation_possible": True,
            "requires_manual_knowledge_authoring": True,
            "can_be_populated_without_gold": True,
            "risk_of_encoding_case_specific_logic": "low",
            "backward_compatibility": "Missing values can temporarily fall back to primary_in_scope during migration, but ambiguous records should be explicitly authored before rollout.",
            "required_or_optional": "required_for_v2_1_boundary_contract",
            "default_behavior": "treat_missing_as_primary_in_scope_for_non_production_analysis_only",
            "validation_rules": [
                "global_policy scope must use global_reusable",
                "solution_specific scope should default to primary_in_scope",
                "full_applicable_scope requires applicable_solution_ids length >= 2",
            ],
        },
        {
            "field_name": "requested_evidence_roles",
            "side": "runtime",
            "business_definition": (
                "Optional future runtime field for narrowing retrieval by evidence purpose such as capability proof, prerequisite, case study, or unsupported boundary."
            ),
            "allowed_values": [
                "solution_capability",
                "shared_prerequisite",
                "integration_dependency",
                "reference_case",
                "readiness_gate",
                "unsupported_boundary",
            ],
            "examples": [{"query_pattern": "公开案例或上线前提", "value": ["reference_case", "integration_dependency"]}],
            "population_owner": "runtime_or_application_layer",
            "population_time": "request_construction",
            "deterministic_derivation_possible": False,
            "requires_manual_knowledge_authoring": False,
            "can_be_populated_without_gold": True,
            "risk_of_encoding_case_specific_logic": "medium",
            "backward_compatibility": "Optional future extension only; not required for the minimal v2.1 recommendation.",
            "required_or_optional": "optional_future_extension",
            "default_behavior": "omit_field",
            "validation_rules": [
                "must not include expected or forbidden gold identifiers",
                "values must come from a fixed enum",
            ],
        },
    ]


def _build_contract_variants(*, context: Any, candidate_records: list[CandidateRecord]) -> list[dict[str, Any]]:
    variants = [
        {
            "variant_definition": {
                "contract_id": "C0",
                "contract_name": "Current Contract",
                "upgrade_scope": "no_contract_upgrade",
                "description": "Current non-gold contract using only existing runtime fields and current metadata with primary/applicable/excluded semantics.",
            },
            "evaluator": _allow_current_contract,
            "deployable": True,
            "runtime_schema_changes": [],
            "candidate_metadata_changes": [],
        },
        {
            "variant_definition": {
                "contract_id": "C1",
                "contract_name": "Runtime-only Extension",
                "upgrade_scope": "runtime_only_v2_1",
                "description": "Adds runtime-side intent knobs only, without adding a stable candidate-side scope-match field.",
            },
            "evaluator": _allow_runtime_only_extension,
            "deployable": False,
            "runtime_schema_changes": ["requested_evidence_roles"],
            "candidate_metadata_changes": [],
        },
        {
            "variant_definition": {
                "contract_id": "C2",
                "contract_name": "Knowledge Metadata-only Extension",
                "upgrade_scope": "knowledge_metadata_only_v2_1",
                "description": "Adds a candidate-side runtime_scope_match_mode field while reusing the current runtime context unchanged.",
            },
            "evaluator": _allow_candidate_metadata_only_extension,
            "deployable": False,
            "runtime_schema_changes": [],
            "candidate_metadata_changes": ["runtime_scope_match_mode"],
        },
        {
            "variant_definition": {
                "contract_id": "C3",
                "contract_name": "Runtime + Candidate Paired Extension",
                "upgrade_scope": "runtime_and_knowledge_metadata_v2_1",
                "description": "Adds both candidate-side runtime_scope_match_mode and optional runtime-side requested_evidence_roles.",
            },
            "evaluator": _allow_paired_extension,
            "deployable": False,
            "runtime_schema_changes": ["requested_evidence_roles"],
            "candidate_metadata_changes": ["runtime_scope_match_mode"],
        },
        {
            "variant_definition": {
                "contract_id": "C4",
                "contract_name": "Oracle Contract",
                "upgrade_scope": "oracle_only",
                "description": "Uses evaluation gold to identify boundary items perfectly. Non-deployable upper bound only.",
            },
            "evaluator": _allow_oracle_contract,
            "deployable": False,
            "runtime_schema_changes": [],
            "candidate_metadata_changes": [],
        },
    ]

    for item in variants:
        case_metrics = _evaluate_contract_variant(
            context=context,
            candidate_records=candidate_records,
            evaluator=item["evaluator"],
        )
        case_metrics["deployable"] = item["deployable"]
        item["metrics"] = case_metrics
    return variants


def _build_counterfactual_results(contract_variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in contract_variants:
        metrics = item["metrics"]
        result = {
            "contract_id": item["variant_definition"]["contract_id"],
            "contract_name": item["variant_definition"]["contract_name"],
            "upgrade_scope": item["variant_definition"]["upgrade_scope"],
            "relevant_candidate_retention_rate": metrics["relevant_candidate_retention_rate"],
            "boundary_candidate_removal_rate": metrics["boundary_candidate_removal_rate"],
            "false_positive_count": metrics["false_positive_count"],
            "false_negative_count": metrics["false_negative_count"],
            "unresolved_conflict_clusters": metrics["unresolved_conflict_clusters"],
            "boundary_violation_rate": metrics["boundary_violation_rate"],
            "candidate_recall_at_20": metrics["candidate_recall_at_20"],
            "forbidden_hit_rate": metrics["forbidden_hit_rate"],
            "contract_satisfiable": False,
            "runtime_rule_uses_gold": metrics["runtime_rule_uses_gold"],
            "candidate_assignment_rule_reads_gold_fields": metrics["candidate_assignment_rule_reads_gold_fields"],
            "authoring_process_was_blind": metrics["authoring_process_was_blind"],
            "evaluation_uses_gold_for_measurement": True,
            "gold_independent": "deprecated_ambiguous_do_not_use",
            "gold_independent_deprecated": True,
            "deployable": metrics["deployable"],
            "method_id": metrics["method_id"],
            "unresolved_case_ids": metrics["unresolved_case_ids"],
            "uses_case_specific_logic": metrics["uses_case_specific_logic"],
            "observed_on_current_cases": True,
            "post_hoc_design_risk": not metrics["authoring_process_was_blind"],
            "validated_contract": False,
            "hypothesis_supported": (
                metrics["relevant_candidate_retention_rate"] == 1.0
                and metrics["boundary_candidate_removal_rate"] == 1.0
            ),
            "blind_authoring_required": not metrics["authoring_process_was_blind"],
        }
        results.append(result)
    return results


def _select_recommended_contract(counterfactual_results: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = sorted(
        counterfactual_results,
        key=lambda item: (
            item["hypothesis_supported"],
            item["relevant_candidate_retention_rate"],
            item["boundary_candidate_removal_rate"],
            -item["false_positive_count"],
            -item["false_negative_count"],
        ),
        reverse=True,
    )
    best = ranked[0]
    runtime_schema_changes: list[str]
    candidate_metadata_changes: list[str]
    if best["contract_id"] == "C2":
        runtime_schema_changes = []
        candidate_metadata_changes = ["runtime_scope_match_mode"]
    elif best["contract_id"] == "C3":
        runtime_schema_changes = ["requested_evidence_roles"]
        candidate_metadata_changes = ["runtime_scope_match_mode"]
    elif best["contract_id"] == "C1":
        runtime_schema_changes = ["requested_evidence_roles"]
        candidate_metadata_changes = []
    else:
        runtime_schema_changes = []
        candidate_metadata_changes = []
    return {
        **best,
        "runtime_schema_changes": runtime_schema_changes,
        "candidate_metadata_changes": candidate_metadata_changes,
    }


def _collect_candidate_records(*, context: Any, runner: SeparabilityExperimentRunner) -> list[CandidateRecord]:
    records: list[CandidateRecord] = []
    for method_id in METHOD_IDS:
        for case in context.cases:
            candidates = runner._get_strategy_candidates(  # noqa: SLF001
                case=case,
                method_id=method_id,
                query_variant_id="Q0",
                field_variant_id="F0",
            )[:20]
            for candidate_payload in candidates:
                view = runner._candidate_view(candidate_payload)  # noqa: SLF001
                candidate_id = candidate_payload.get("chunk_id") or candidate_payload["document_id"]
                relevant = _candidate_relevance_id_for_case(case=case, candidate=candidate_payload) in _relevant_ids(case)
                boundary = not _current_gold_boundary_allowed(case=case, document=view["document"], chunk=view["chunk"])
                records.append(
                    CandidateRecord(
                        case_id=case.retrieval_case_id,
                        method_id=method_id,
                        document=view["document"],
                        chunk=view["chunk"],
                        candidate=view["candidate"],
                        candidate_id=candidate_id,
                        relevant=relevant,
                        boundary=boundary,
                    )
                )
    return records


def _evaluate_contract_variant(*, context: Any, candidate_records: list[CandidateRecord], evaluator: Any) -> dict[str, Any]:
    by_method_case: defaultdict[tuple[str, str], list[CandidateRecord]] = defaultdict(list)
    for record in candidate_records:
        by_method_case[(record.method_id, record.case_id)].append(record)

    best_summary: dict[str, Any] | None = None
    for method_id in METHOD_IDS:
        case_results: list[dict[str, Any]] = []
        relevant_total = 0
        relevant_retained = 0
        boundary_total = 0
        boundary_removed = 0
        false_positive_count = 0
        false_negative_count = 0
        unresolved_case_ids: list[str] = []

        for case in context.cases:
            runtime_input = make_runtime_input_v2(case=case, top_k=20)
            filtered_payloads: list[dict[str, Any]] = []
            next_rank = 1
            for record in by_method_case[(method_id, case.retrieval_case_id)]:
                if record.relevant:
                    relevant_total += 1
                if record.boundary:
                    boundary_total += 1
                allowed = evaluator(case=case, runtime_input=runtime_input, record=record)
                if allowed:
                    filtered_payloads.append(
                        {
                            "rank": next_rank,
                            "document_id": record.document.document_id,
                            "chunk_id": record.chunk.chunk_id if record.chunk is not None else None,
                            "score": 1.0,
                        }
                    )
                    next_rank += 1
                    if record.relevant:
                        relevant_retained += 1
                    if record.boundary:
                        false_negative_count += 1
                else:
                    if record.boundary:
                        boundary_removed += 1
                    if record.relevant:
                        false_positive_count += 1
            case_result = _evaluate_candidate_list(
                case=case,
                candidates=filtered_payloads,
                documents_by_id=context.documents_by_id,
                chunks_by_id=context.chunks_by_id,
            )
            case_results.append({"case_id": case.retrieval_case_id, **case_result})
            if case_result["candidate_recall_at_20"] < 1.0:
                unresolved_case_ids.append(case.retrieval_case_id)

        candidate_recall_at_20 = sum(item["candidate_recall_at_20"] for item in case_results) / len(case_results)
        boundary_violation_rate = sum(1.0 if item["boundary_violation_at_20"] else 0.0 for item in case_results) / len(case_results)
        forbidden_hit_rate = sum(1.0 if item["forbidden_hit_at_20"] else 0.0 for item in case_results) / len(case_results)
        summary = {
            "method_id": method_id,
            "candidate_recall_at_20": candidate_recall_at_20,
            "boundary_violation_rate": boundary_violation_rate,
            "forbidden_hit_rate": forbidden_hit_rate,
            "relevant_candidate_retention_rate": (relevant_retained / relevant_total) if relevant_total else 1.0,
            "boundary_candidate_removal_rate": (boundary_removed / boundary_total) if boundary_total else 1.0,
            "false_positive_count": false_positive_count,
            "false_negative_count": false_negative_count,
            "unresolved_conflict_clusters": [],
            "unresolved_case_ids": sorted(set(unresolved_case_ids)),
            "runtime_rule_uses_gold": evaluator is _allow_oracle_contract,
            "candidate_assignment_rule_reads_gold_fields": False,
            "authoring_process_was_blind": False,
            "deployable": evaluator not in {_allow_oracle_contract, _allow_runtime_only_extension},
            "uses_case_specific_logic": False,
        }
        if best_summary is None or (
            summary["relevant_candidate_retention_rate"],
            summary["boundary_candidate_removal_rate"],
            summary["candidate_recall_at_20"],
            -summary["boundary_violation_rate"],
            -summary["forbidden_hit_rate"],
        ) > (
            best_summary["relevant_candidate_retention_rate"],
            best_summary["boundary_candidate_removal_rate"],
            best_summary["candidate_recall_at_20"],
            -best_summary["boundary_violation_rate"],
            -best_summary["forbidden_hit_rate"],
        ):
            best_summary = summary

    if best_summary is None:
        raise ValueError("Failed to evaluate contract variants.")
    return best_summary


def _allow_current_contract(*, case: Any, runtime_input: Any, record: CandidateRecord) -> bool:
    candidate = record.candidate
    document = record.document
    if not document.is_active(as_of=runtime_input.effective_on):
        return False
    if runtime_input.allowed_document_types and document.document_type.value not in set(runtime_input.allowed_document_types):
        return False
    if runtime_input.industries and document.industries and set(document.industries).isdisjoint(set(runtime_input.industries)):
        return False
    if runtime_input.tags and document.tags and set(document.tags).isdisjoint(set(runtime_input.tags)):
        return False
    if set(candidate.excluded_solution_ids) & set(runtime_input.operational_solution_scope):
        return False
    if candidate.scope_type.value == "global_policy":
        return True
    if candidate.primary_solution_id is None:
        return False
    return candidate.primary_solution_id in set(runtime_input.operational_solution_scope)


def _allow_runtime_only_extension(*, case: Any, runtime_input: Any, record: CandidateRecord) -> bool:
    if not _allow_current_contract(case=case, runtime_input=runtime_input, record=record):
        return False
    # Runtime-only cannot express candidate-specific partial-overlap semantics without new KB metadata.
    # It therefore collapses to current behavior for ambiguous multi-solution and cross-cutting records.
    return True


def _allow_candidate_metadata_only_extension(*, case: Any, runtime_input: Any, record: CandidateRecord) -> bool:
    candidate = record.candidate
    document = record.document
    if not document.is_active(as_of=runtime_input.effective_on):
        return False
    if runtime_input.allowed_document_types and document.document_type.value not in set(runtime_input.allowed_document_types):
        return False
    if runtime_input.industries and document.industries and set(document.industries).isdisjoint(set(runtime_input.industries)):
        return False
    if runtime_input.tags and document.tags and set(document.tags).isdisjoint(set(runtime_input.tags)):
        return False
    if set(candidate.excluded_solution_ids) & set(runtime_input.operational_solution_scope):
        return False

    mode = _derive_runtime_scope_match_mode(record=record)
    operational_scope = set(runtime_input.operational_solution_scope)
    applicable = set(candidate.applicable_solution_ids)
    if mode == "global_reusable":
        return True
    if mode == "primary_in_scope":
        return candidate.primary_solution_id in operational_scope
    if mode == "full_applicable_scope":
        return applicable.issubset(operational_scope)
    raise ValueError(f"Unsupported runtime_scope_match_mode: {mode}")


def _allow_paired_extension(*, case: Any, runtime_input: Any, record: CandidateRecord) -> bool:
    return _allow_candidate_metadata_only_extension(case=case, runtime_input=runtime_input, record=record)


def _allow_oracle_contract(*, case: Any, runtime_input: Any, record: CandidateRecord) -> bool:
    return not record.boundary


def _derive_runtime_scope_match_mode(*, record: CandidateRecord) -> str:
    candidate = record.candidate
    document_type = record.document.document_type.value
    citation_label = record.chunk.citation_label if record.chunk is not None else ""
    if candidate.scope_type.value == "global_policy":
        return "global_reusable"
    if candidate.scope_type.value == "solution_specific":
        return "primary_in_scope"
    if document_type in {"unsupported_scenario", "readiness_requirement"}:
        return "full_applicable_scope"
    if document_type == "capability" and "能力说明" in citation_label:
        return "full_applicable_scope"
    return "primary_in_scope"


def _document_type_for_item(*, context: Any, item: dict[str, Any]) -> str:
    return context.documents_by_id[item["document_id"]].document_type.value


def _candidate_refs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str | None, str]] = set()
    refs: list[dict[str, Any]] = []
    for item in items:
        key = (item["case_id"], item["document_id"], item["chunk_id"])
        if key in seen:
            continue
        seen.add(key)
        refs.append(
            {
                "case_id": item["case_id"],
                "document_id": item["document_id"],
                "chunk_id": item["chunk_id"],
            }
        )
    return refs


def _current_gold_boundary_allowed(*, case: Any, document: KnowledgeDocumentV2, chunk: KnowledgeChunkV2 | None) -> bool:
    candidate = chunk or document
    applicable = set(candidate.applicable_solution_ids)
    excluded = set(candidate.excluded_solution_ids)
    operational_scope = set(case.runtime_context.operational_solution_scope)
    forbidden_scope = set(case.evaluation_gold.forbidden_solution_ids)
    if document.document_id in case.evaluation_gold.forbidden_document_ids:
        return False
    if operational_scope and excluded & operational_scope:
        return False
    if candidate.scope_type.value != "global_policy":
        if operational_scope and applicable.isdisjoint(operational_scope):
            return False
        if forbidden_scope and applicable & forbidden_scope:
            return False
    return True
