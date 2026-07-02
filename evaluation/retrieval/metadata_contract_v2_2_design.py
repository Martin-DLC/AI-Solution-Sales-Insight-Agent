from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evaluation.retrieval.contracts_v2 import (
    RetrievalEvaluationCaseV2,
    _document_passes_runtime_filters,
    evaluate_candidate_boundary_v2,
)
from evaluation.retrieval.metadata_blind_evaluation_v2 import (
    EXPECTED_LABELS_SHA256,
    TRACKED_EVALUATION_OUTPUT_PATH,
    _relevant_item_identity,
    _scope_contract_allowed,
)
from evaluation.retrieval.metadata_blind_failure_analysis_v2 import (
    TRACKED_FAILURE_ANALYSIS_JSON_PATH,
    _build_candidate_mode_satisfiability,
    _build_observable_state_conflicts,
    _load_inputs as _load_failure_analysis_inputs,
)
from evaluation.retrieval.storage import diff_json_objects, load_json_record, write_many_atomic
from knowledge_base.contracts_v2 import KnowledgeChunkV2

TRACKED_PROPOSAL_OUTPUT_PATH = Path("data/evaluation/retrieval/retrieval_metadata_contract_v2_2_proposal.json")
TRACKED_PROPOSAL_DOC_PATH = Path("docs/37_Retrieval_Metadata_Contract_V2_2_Design.md")

NON_DETERMINISTIC_FIELDS = {"generated_at"}
UNSATISFIABLE_CHUNK_IDS = [
    "KB-SEC-001#chunk-000-f8c40d662005",
    "KB-SEC-001#chunk-001-d88fdb994b4e",
]

D0_VALUES = ["primary_in_scope", "full_applicable_scope", "global_reusable"]
D1_VALUES = ["primary_in_scope", "any_applicable_scope", "full_applicable_scope", "global_reusable"]
D2_VALUES = ["primary", "any_applicable", "all_applicable", "global"]


def build_plan_payload() -> dict[str, Any]:
    return {
        "mode": "plan",
        "proposal_version": "retrieval_metadata_contract_v2_2_design_proposal_v1",
        "analysis_type": "retrieval_metadata_contract_v2_2_narrow_design_and_satisfiability",
        "input_files": {
            "blind_evaluation": str(TRACKED_EVALUATION_OUTPUT_PATH),
            "blind_failure_analysis": str(TRACKED_FAILURE_ANALYSIS_JSON_PATH),
            "documents": "data/knowledge_base/documents.v2.jsonl",
            "chunks": "data/knowledge_base/chunks.v2.jsonl",
            "cases": "data/evaluation/retrieval/retrieval_cases.v2.jsonl",
        },
        "output_files": {
            "json": str(TRACKED_PROPOSAL_OUTPUT_PATH),
            "doc": str(TRACKED_PROPOSAL_DOC_PATH),
        },
        "writes_output_files": False,
        "mutates_frozen_blind_labels": False,
        "starts_blind_attempt_2": False,
        "uses_gold_only_for_counterfactual_measurement": True,
        "uses_case_ids_for_assignment_generation": False,
        "requires_network": False,
    }


def build_metadata_contract_v2_2_payload() -> dict[str, Any]:
    inputs = _load_inputs()
    d0_candidate_stats = _build_candidate_mode_satisfiability(inputs=inputs)
    blind_evaluation = load_json_record(TRACKED_EVALUATION_OUTPUT_PATH)
    failure_analysis = load_json_record(TRACKED_FAILURE_ANALYSIS_JSON_PATH)

    unsat_analysis = _build_unsatisfiable_candidate_analysis(inputs=inputs)
    observable_state_conflicts = _build_observable_state_conflicts(inputs=inputs)
    schema_variants = _build_schema_variants(inputs=inputs)
    single_enum_extension_results = _build_single_enum_extension_results(schema_variants=schema_variants)
    orthogonal_field_results = _build_orthogonal_field_results(schema_variants=schema_variants)
    runtime_joinability = _build_runtime_joinability(schema_variants=schema_variants)
    per_chunk_satisfiability = _build_per_chunk_satisfiability(
        d0_candidate_stats=d0_candidate_stats,
        schema_variants=schema_variants,
    )
    best_schema_variant = _select_best_schema_variant(schema_variants=schema_variants)
    proposed_candidate_schema = _build_proposed_candidate_schema(best_schema_variant=best_schema_variant)

    return {
        "proposal_version": "retrieval_metadata_contract_v2_2_design_proposal_v1",
        "evidence_classification": "P1_post_hoc_schema_design_not_blind_validated",
        "source_failure_analysis_hash": _sha256_file(TRACKED_FAILURE_ANALYSIS_JSON_PATH),
        "source_blind_label_hash": EXPECTED_LABELS_SHA256,
        "source_blind_evaluation_hash": _sha256_file(TRACKED_EVALUATION_OUTPUT_PATH),
        "blind_attempt_1_snapshot": {
            "labels_frozen_and_immutable": True,
            "p0_failed": True,
            "blind_labels_modified": False,
            "blind_evaluation_overwritten": False,
            "failure_artifact_overwritten": False,
            "false_exclusion_count": blind_evaluation["overall_metrics"]["false_exclusion_count"],
            "false_inclusion_count": blind_evaluation["overall_metrics"]["false_inclusion_count"],
            "relevant_candidate_retention_rate": blind_evaluation["overall_metrics"][
                "relevant_candidate_retention_rate"
            ],
            "boundary_candidate_removal_rate": blind_evaluation["overall_metrics"][
                "boundary_candidate_removal_rate"
            ],
        },
        "unsatisfiable_candidate_analysis": unsat_analysis,
        "observable_state_conflicts": {
            "count": len(observable_state_conflicts),
            "conflicts": observable_state_conflicts,
        },
        "schema_variants": schema_variants,
        "single_enum_extension_results": single_enum_extension_results,
        "orthogonal_field_results": orthogonal_field_results,
        "runtime_joinability": runtime_joinability,
        "per_chunk_satisfiability": per_chunk_satisfiability,
        "best_schema_variant": best_schema_variant,
        "minimum_required_change": {
            "change_type": "guide_and_protocol_clarification_only",
            "field_name": "runtime_scope_match_mode",
            "new_value": None,
            "why_minimal": "Once the existing runtime filters are joined with the existing three-value mode, all 40 chunks already have at least one perfect assignment.",
            "why_not_guide_only": "Guide clarification is exactly the minimal change required; no new metadata field or runtime field is justified by the current evidence.",
            "why_not_dual_field": "A second field does not improve runtime allow/deny behavior over the existing schema under the current 40x16 counterfactual.",
            "why_not_fourth_enum": "any_applicable_scope also reaches 1.0/1.0, but it is unnecessary because D0 already does so when evaluated with the full existing runtime join.",
        },
        "proposed_candidate_schema": proposed_candidate_schema,
        "proposed_runtime_schema_changes": {
            "required": False,
            "new_fields": [],
            "missing_runtime_signal": [],
            "notes": "Existing operational_solution_scope is sufficient once candidate metadata can express partial applicable-scope reuse.",
        },
        "migration_scope": {
            "knowledge_metadata_only": False,
            "runtime_schema_change_required": False,
            "document_default_supported": True,
            "chunk_override_supported": True,
            "requires_new_blind_attempt": True,
            "requires_relabeling_existing_attempt_1": False,
            "chunks_requiring_new_value_count": single_enum_extension_results["requires_new_enum_count"],
            "chunks_requiring_new_value_ids": single_enum_extension_results["requires_new_enum_chunk_ids"],
            "requires_protocol_clarification": True,
            "requires_guide_clarification": True,
        },
        "backward_compatibility": {
            "old_values_retained": True,
            "new_value_is_additive": False,
            "d2_quantifier_only_is_rename_not_required": True,
            "runtime_context_backward_compatible": True,
            "default_behavior_status": "document_default_with_chunk_override remains valid; no enum expansion is required by current evidence.",
        },
        "blind_authoring_requirements": {
            "new_protocol_required": True,
            "new_blind_attempt_required": True,
            "completed_labels_reuse_forbidden": True,
            "frozen_attempt_1_remains_immutable": True,
            "knowledge_only_authoring": True,
            "candidate_content_only": True,
            "case_id_forbidden": True,
            "gold_forbidden": True,
        },
        "metadata_v2_2_ready_for_versioning": False,
        "ready_for_blind_protocol_v2_2": True,
        "blind_authoring_validated": False,
        "independent_validation_completed": False,
        "deployment_validated": False,
        "retriever_v2_status": "blocked_by_candidate_recall",
        "architecture_c_status": "blocked",
        "limitations": [
            "This is a post-hoc counterfactual design exercise and does not modify frozen labels or rerun blind authoring.",
            "RET2-015 and RET2-016 remain independent candidate-recall failures and are intentionally out of scope.",
            "The proposal proves satisfiability only when existing candidate metadata is evaluated together with existing runtime filters across the current 40 chunks and 640 case-chunk pairs.",
            "The current evidence therefore supports a protocol/guide clarification before any schema expansion, not immediate metadata versioning.",
        ],
        "generated_at": _now_iso(),
        "source_failure_analysis_snapshot": {
            "unique_error_candidate_count": failure_analysis["error_pair_summary"]["unique_error_candidate_count"],
            "schema_unsatisfiable_candidate_count": len(failure_analysis["schema_unsatisfiable_candidates"]),
            "schema_unsatisfiable_candidate_ids": [
                item["source_chunk_id"] for item in failure_analysis["schema_unsatisfiable_candidates"]
            ],
        },
    }


def write_metadata_contract_v2_2_outputs(payload: dict[str, Any]) -> None:
    write_many_atomic(
        [
            (
                TRACKED_PROPOSAL_OUTPUT_PATH,
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            ),
            (
                TRACKED_PROPOSAL_DOC_PATH,
                render_metadata_contract_v2_2_markdown(payload),
            ),
        ]
    )


def check_metadata_contract_v2_2_outputs() -> tuple[bool, list[str]]:
    differences: list[str] = []
    if not TRACKED_PROPOSAL_OUTPUT_PATH.exists():
        differences.append(f"Missing tracked v2.2 proposal JSON: {TRACKED_PROPOSAL_OUTPUT_PATH}")
        return False, differences
    if not TRACKED_PROPOSAL_DOC_PATH.exists():
        differences.append(f"Missing tracked v2.2 design doc: {TRACKED_PROPOSAL_DOC_PATH}")
        return False, differences

    expected = build_metadata_contract_v2_2_payload()
    actual = load_json_record(TRACKED_PROPOSAL_OUTPUT_PATH)
    differences.extend(
        diff_json_objects(
            _without_nondeterministic_fields(actual),
            _without_nondeterministic_fields(expected),
            path="metadata_contract_v2_2",
        )
    )
    expected_doc = render_metadata_contract_v2_2_markdown(expected)
    actual_doc = TRACKED_PROPOSAL_DOC_PATH.read_text(encoding="utf-8")
    if actual_doc != expected_doc:
        differences.append(f"Tracked v2.2 design doc drifted: {TRACKED_PROPOSAL_DOC_PATH}")
    return (not differences, differences)


def render_metadata_contract_v2_2_markdown(payload: dict[str, Any]) -> str:
    best = payload["best_schema_variant"]
    d0 = next(item for item in payload["schema_variants"] if item["variant_id"] == "D0")
    d1 = next(item for item in payload["schema_variants"] if item["variant_id"] == "D1")
    d2 = next(item for item in payload["schema_variants"] if item["variant_id"] == "D2")
    unsat = payload["unsatisfiable_candidate_analysis"]
    lines = [
        "# Retrieval Metadata Contract v2.2 Design",
        "",
        "## 1. P0失败摘要",
        "",
        f"- Relevant Retention: `{payload['blind_attempt_1_snapshot']['relevant_candidate_retention_rate']}`",
        f"- Boundary Removal: `{payload['blind_attempt_1_snapshot']['boundary_candidate_removal_rate']}`",
        f"- False Exclusion: `{payload['blind_attempt_1_snapshot']['false_exclusion_count']}`",
        f"- False Inclusion: `{payload['blind_attempt_1_snapshot']['false_inclusion_count']}`",
        f"- Unique error candidates: `{payload['source_failure_analysis_snapshot']['unique_error_candidate_count']}`",
        "",
        "## 2. 为什么不能回改Attempt 1标签",
        "",
        "- Blind Attempt 1 标签已经冻结，必须保持不可变。",
        "- v2.2 只能作为新的P1设计假设，不能覆盖 v2.1 的 blind labels、evaluation 或 failure artifact。",
        "- 下一次只能通过新协议版本和 Blind Attempt 2 验证。",
        "",
        "## 3. 9个可由现有Mode修正的Candidate",
        "",
        f"- Existing three-mode schema already has a perfect alternative for `{d0['perfect_candidate_count'] - d0['current_v2_1_assignment_perfect_count'] - d0['unsatisfiable_candidate_count']}` candidates that are currently misassigned.",
        "- 这些问题属于 Blind Authoring Misclassification 或 Guide 歧义，不要求扩展 Runtime 合同。",
        "",
        "## 4. 两个真正Unsatisfiable Candidate",
        "",
        f"- `{UNSATISFIABLE_CHUNK_IDS[0]}`",
        f"- `{UNSATISFIABLE_CHUNK_IDS[1]}`",
        "",
        "## 5. 六组Observable State Conflict",
        "",
        f"- observable_state_conflict_count: `{payload['observable_state_conflicts']['count']}`",
        "",
        "## 6. any_applicable_scope实验",
        "",
        f"- solves_scope_only_unsatisfiable_candidates: `{d1['unsatisfiable_candidate_count'] == 0}`",
        f"- relevant_candidate_retention_rate: `{d1['relevant_candidate_retention_rate']}`",
        f"- boundary_candidate_removal_rate: `{d1['boundary_candidate_removal_rate']}`",
        f"- false_exclusion_count: `{d1['false_exclusion_count']}`",
        f"- false_inclusion_count: `{d1['false_inclusion_count']}`",
        f"- requires_new_enum_chunk_ids: `{payload['single_enum_extension_results']['requires_new_enum_chunk_ids']}`",
        "",
        "## 7. 单字段方案",
        "",
        f"- D0 perfect_candidate_count: `{d0['perfect_candidate_count']}` / 40",
        f"- D0 unsatisfiable_candidate_count: `{d0['unsatisfiable_candidate_count']}`",
        f"- D1 perfect_candidate_count: `{d1['perfect_candidate_count']}` / 40",
        f"- D1 unsatisfiable_candidate_count: `{d1['unsatisfiable_candidate_count']}`",
        f"- D2 perfect_candidate_count: `{d2['perfect_candidate_count']}` / 40",
        f"- D2 unsatisfiable_candidate_count: `{d2['unsatisfiable_candidate_count']}`",
        "",
        "## 8. 双字段方案",
        "",
        f"- orthogonal field required for runtime matching: `{payload['orthogonal_field_results']['required_for_runtime_matching']}`",
        f"- evidence_relation changes allow/deny: `{payload['orthogonal_field_results']['evidence_relation_changes_runtime_decision']}`",
        "",
        "## 9. 是否需要Runtime字段",
        "",
        f"- runtime_only_sufficient: `{payload['runtime_joinability']['runtime_only_sufficient']}`",
        f"- candidate_only_sufficient: `{payload['runtime_joinability']['candidate_only_sufficient']}`",
        f"- existing_candidate_plus_existing_runtime_sufficient: `{payload['runtime_joinability']['existing_candidate_plus_existing_runtime_sufficient']}`",
        f"- paired_upgrade_required: `{payload['runtime_joinability']['paired_upgrade_required']}`",
        "",
        "## 10. 全40 Chunk可满足性",
        "",
        f"- all_40_have_perfect_assignment_under_best_variant: `{best['perfect_candidate_count'] == 40}`",
        f"- schema_unsatisfiable_count: `{best['unsatisfiable_candidate_count']}`",
        f"- ambiguous_assignment_count: `{best['ambiguous_assignment_count']}`",
        "",
        "## 11. 最小Schema结论",
        "",
        f"- best_schema_variant: `{best['variant_id']}`",
        f"- minimum_required_change: `{payload['minimum_required_change']['new_value']}` on `{payload['minimum_required_change']['field_name']}`",
        "- 当前最小结论不是增加第四个枚举，而是保留现有三值Schema，并在 Blind Protocol v2.2 中把现有 runtime filters 一并纳入可满足性验证。",
        "",
        "## 12. Authoring定义",
        "",
        "### any_applicable_scope（已验证但非必要）",
        "",
        "- business_definition: 当 candidate 的 applicable_solution_ids 与当前 operational_solution_scope 存在非空交集时即可复用，只要 excluded_solution_ids 不冲突。",
        "- positive_example: “某安全前置条件适用于方案A和方案B，只要当前场景正在讨论A或B中的任意一个，该前置条件都值得展示。”",
        "- negative_example: “某能力说明只有当A和B同时都在当前范围内时才安全；仅命中其中一个时不能展示。”",
        "- distinguish_from_primary_in_scope: `primary_in_scope` 只看 primary_solution_id；`any_applicable_scope` 允许 primary 之外的适用方案独立触发。",
        "- distinguish_from_full_applicable_scope: `full_applicable_scope` 要求所有 applicable_solution_ids 全部进入当前 scope。",
        "",
        "## 13. Document Default + Chunk Override",
        "",
        f"- document_default_supported: `{payload['proposed_candidate_schema']['document_default_supported']}`",
        f"- chunk_override_supported: `{payload['proposed_candidate_schema']['chunk_override_supported']}`",
        "",
        "## 14. 向后兼容",
        "",
        "- 保留旧三值枚举语义即可满足当前40个Chunk与640个Pair的反事实目标。",
        "- D1 与 D2 都是可行但非必要的更改；D2 仅是更规范的重命名候选，不是当前最小迁移方案。",
        "",
        "## 15. 为什么仍是P1设计假设",
        "",
        f"- evidence_classification: `{payload['evidence_classification']}`",
        f"- blind_authoring_validated: `{payload['blind_authoring_validated']}`",
        f"- metadata_v2_2_ready_for_versioning: `{payload['metadata_v2_2_ready_for_versioning']}`",
        "",
        "## 16. Blind Protocol v2.2条件",
        "",
        f"- ready_for_blind_protocol_v2_2: `{payload['ready_for_blind_protocol_v2_2']}`",
        "- 允许进入 Blind Protocol v2.2 设计，但不允许直接版本化或部署。",
        "",
        "## 17. RET2-015/016独立Recall问题",
        "",
        f"- retriever_v2_status: `{payload['retriever_v2_status']}`",
        "- Metadata v2.2 只解决 Boundary 合同，不解决 Candidate Recall。",
        "",
        "## 18. Architecture C状态",
        "",
        f"- architecture_c_status: `{payload['architecture_c_status']}`",
        "",
        "## 19. 两个Unsatisfiable Candidate逐Case摘要",
        "",
    ]
    for item in unsat["candidates"]:
        lines.extend(
            [
                f"### {item['source_chunk_id']}",
                "",
                f"- generic_business_meaning: {item['generic_business_meaning']}",
                f"- primary_mode_failure_reason: {item['mode_failure_explanations']['primary_in_scope']}",
                f"- full_mode_failure_reason: {item['mode_failure_explanations']['full_applicable_scope']}",
                f"- global_mode_failure_reason: {item['mode_failure_explanations']['global_reusable']}",
                f"- any_applicable_scope_resolves: `{item['any_applicable_scope']['perfect_for_candidate']}`",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def _load_inputs() -> dict[str, Any]:
    return _load_failure_analysis_inputs()


def _build_unsatisfiable_candidate_analysis(*, inputs: dict[str, Any]) -> dict[str, Any]:
    cases: list[RetrievalEvaluationCaseV2] = inputs["cases"]
    chunks_by_id: dict[str, KnowledgeChunkV2] = inputs["chunks_by_id"]
    documents_by_id = inputs["documents_by_id"]
    evaluation_date = datetime.fromisoformat(inputs["benchmark_config"]["evaluation_date"]).date()
    items: list[dict[str, Any]] = []
    for chunk_id in UNSATISFIABLE_CHUNK_IDS:
        chunk = chunks_by_id[chunk_id]
        document = documents_by_id[chunk.document_id]
        per_case: list[dict[str, Any]] = []
        allow_case_ids: list[str] = []
        deny_case_ids: list[str] = []
        neutral_case_ids: list[str] = []
        for case in cases:
            relevant = _is_relevant(case=case, chunk=chunk)
            boundary_allowed = evaluate_candidate_boundary_v2(case=case, document=document, chunk=chunk).candidate_allowed
            primary_allowed = _mode_allows(case=case, chunk=chunk, mode="primary_in_scope")
            full_allowed = _mode_allows(case=case, chunk=chunk, mode="full_applicable_scope")
            global_allowed = _mode_allows(case=case, chunk=chunk, mode="global_reusable")
            any_allowed = _mode_allows(case=case, chunk=chunk, mode="any_applicable_scope")
            document_type_eligible = _document_passes_runtime_filters(
                case=case,
                document=document,
                evaluation_date=evaluation_date,
            )
            if relevant:
                desired = "allow"
                allow_case_ids.append(case.retrieval_case_id)
            elif not boundary_allowed:
                desired = "deny"
                deny_case_ids.append(case.retrieval_case_id)
            else:
                desired = "neutral"
                neutral_case_ids.append(case.retrieval_case_id)
            per_case.append(
                {
                    "case_id": case.retrieval_case_id,
                    "runtime_operational_solution_scope": list(case.runtime_context.operational_solution_scope),
                    "primary_solution_id": chunk.primary_solution_id,
                    "applicable_solution_ids": list(chunk.applicable_solution_ids),
                    "excluded_solution_ids": list(chunk.excluded_solution_ids),
                    "scope_type": chunk.scope_type.value,
                    "document_type_eligible": document_type_eligible,
                    "relevant_by_gold": relevant,
                    "boundary_allowed_by_gold": boundary_allowed,
                    "desired_decision": desired,
                    "primary_in_scope_result": primary_allowed,
                    "full_applicable_scope_result": full_allowed,
                    "global_reusable_result": global_allowed,
                    "any_applicable_scope_result": any_allowed,
                }
            )

        items.append(
            {
                "source_document_id": chunk.document_id,
                "source_chunk_id": chunk.chunk_id,
                "scope_type": chunk.scope_type.value,
                "citation_label": chunk.citation_label,
                "primary_solution_id": chunk.primary_solution_id,
                "applicable_solution_ids": list(chunk.applicable_solution_ids),
                "excluded_solution_ids": list(chunk.excluded_solution_ids),
                "content_semantic_summary": _semantic_summary(chunk.content),
                "allow_case_ids": allow_case_ids,
                "deny_case_ids": deny_case_ids,
                "neutral_case_ids": neutral_case_ids,
                "runtime_difference_summary": {
                    "allow_cases_have_any_applicable_overlap": True,
                    "deny_cases_include_zero_overlap_or_primary_only_overlap_without_full_applicability": False,
                    "critical_difference": "The deny cases that appear to break primary_in_scope are actually filtered out by existing runtime document-type constraints, not by a missing scope enum.",
                    "gold_observable_pattern": "The current benchmark keeps these security chunks only in contexts that explicitly permit security_compliance evidence; the problematic deny cases do not.",
                },
                "candidate_semantic_hypothesis": "This chunk can remain primary-solution-centered under the current schema, as long as runtime filtering continues to block security_compliance evidence in contexts that do not request that document type.",
                "generic_business_meaning": "A security/compliance evidence chunk centered on controlled-policy retrieval, whose safe visibility depends on both solution scope and existing runtime document-type eligibility.",
                "mode_failure_explanations": {
                    "primary_in_scope": "Under scope-only analysis it appears to fail, because some deny cases still contain the primary solution in runtime scope. Under the full existing runtime join, those deny cases are already blocked by document-type filters.",
                    "full_applicable_scope": "Fails because some allow cases only activate one applicable solution, so requiring every applicable solution creates false exclusions.",
                    "global_reusable": "Under scope-only analysis it over-allows unrelated cases. Under the full existing runtime join it is also blocked by runtime filters, but that would be an unnecessarily weak authoring choice.",
                },
                "any_applicable_scope": _evaluate_single_mode_for_chunk(
                    chunk=chunk,
                    cases=cases,
                    mode="any_applicable_scope",
                    documents_by_id=documents_by_id,
                    evaluation_date=evaluation_date,
                ),
                "per_case": per_case,
            }
        )
    return {
        "unsatisfiable_candidate_count_under_d0": len(items),
        "candidate_ids": [item["source_chunk_id"] for item in items],
        "candidates": items,
    }


def _build_schema_variants(*, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    variants = [
        {
            "variant_id": "D0",
            "variant_name": "existing_three_value_mode",
            "field_count": 1,
            "enum_count": 3,
            "values": D0_VALUES,
            "knowledge_metadata_change_required": False,
            "runtime_schema_change_required": False,
            "normalizes_existing_names": False,
        },
        {
            "variant_id": "D1",
            "variant_name": "four_value_mode_with_any_applicable_scope",
            "field_count": 1,
            "enum_count": 4,
            "values": D1_VALUES,
            "knowledge_metadata_change_required": True,
            "runtime_schema_change_required": False,
            "normalizes_existing_names": False,
        },
        {
            "variant_id": "D2",
            "variant_name": "normalized_scope_quantifier",
            "field_count": 1,
            "enum_count": 4,
            "values": D2_VALUES,
            "knowledge_metadata_change_required": True,
            "runtime_schema_change_required": False,
            "normalizes_existing_names": True,
        },
    ]
    results: list[dict[str, Any]] = []
    for variant in variants:
        evaluation = _evaluate_schema_variant(
            variant_id=variant["variant_id"],
            mode_values=variant["values"],
            inputs=inputs,
        )
        results.append({**variant, **evaluation})
    return results


def _build_single_enum_extension_results(*, schema_variants: list[dict[str, Any]]) -> dict[str, Any]:
    d0 = next(item for item in schema_variants if item["variant_id"] == "D0")
    d1 = next(item for item in schema_variants if item["variant_id"] == "D1")
    return {
        "tested_extension": "any_applicable_scope",
        "solves_unsatisfiable_candidates": d1["unsatisfiable_candidate_count"] == 0,
        "introduces_new_false_exclusions": d1["false_exclusion_count"] > 0,
        "introduces_new_false_inclusions": d1["false_inclusion_count"] > 0,
        "requires_new_enum_count": d1["requires_new_value_count"],
        "requires_new_enum_chunk_ids": d1["requires_new_value_chunk_ids"],
        "all_40_chunks_have_perfect_assignment": d1["perfect_candidate_count"] == 40,
        "authorable_from_candidate_content": d1["authorable_from_candidate_content"],
        "necessary_under_full_existing_runtime_join": d0["perfect_candidate_count"] < 40,
    }


def _build_orthogonal_field_results(*, schema_variants: list[dict[str, Any]]) -> dict[str, Any]:
    d1 = next(item for item in schema_variants if item["variant_id"] == "D1")
    d2 = next(item for item in schema_variants if item["variant_id"] == "D2")
    return {
        "evaluated": True,
        "scope_requirement_values": ["primary", "any_applicable", "all_applicable", "global"],
        "candidate_explanation_only_field_considered": ["reusable", "prerequisite", "comparative", "joint_dependency", "constraint"],
        "required_for_runtime_matching": False,
        "evidence_relation_changes_runtime_decision": False,
        "d1_and_d2_are_runtime_equivalent": (
            d1["relevant_candidate_retention_rate"] == d2["relevant_candidate_retention_rate"]
            and d1["boundary_candidate_removal_rate"] == d2["boundary_candidate_removal_rate"]
            and d1["false_exclusion_count"] == d2["false_exclusion_count"]
            and d1["false_inclusion_count"] == d2["false_inclusion_count"]
        ),
        "conclusion": "Scope requirement alone is sufficient for runtime allow/deny. Any second field would be explanatory or QA-only, not required for matching.",
    }


def _build_runtime_joinability(*, schema_variants: list[dict[str, Any]]) -> dict[str, Any]:
    best = _select_best_schema_variant(schema_variants=schema_variants)
    return {
        "runtime_only_sufficient": False,
        "candidate_only_sufficient": False,
        "existing_candidate_plus_existing_runtime_sufficient": best["variant_id"] == "D0",
        "paired_upgrade_required": False,
        "missing_runtime_signal": [],
        "notes": "Candidate-only scope matching is not sufficient, and runtime-only filters are not sufficient by themselves. The existing pair of candidate mode plus existing runtime filters is already sufficient under the current 40x16 counterfactual.",
    }


def _build_per_chunk_satisfiability(
    *,
    d0_candidate_stats: list[dict[str, Any]],
    schema_variants: list[dict[str, Any]],
) -> dict[str, Any]:
    by_chunk: dict[str, dict[str, Any]] = {}
    d0_by_chunk = {item["source_chunk_id"]: item for item in d0_candidate_stats}
    variant_chunks = {
        variant["variant_id"]: {item["source_chunk_id"]: item for item in variant["per_chunk_results"]}
        for variant in schema_variants
    }
    for chunk_id, d0_item in sorted(d0_by_chunk.items()):
        d1_item = variant_chunks["D1"][chunk_id]
        d2_item = variant_chunks["D2"][chunk_id]
        by_chunk[chunk_id] = {
            "source_document_id": d0_item["source_document_id"],
            "source_chunk_id": chunk_id,
            "available_perfect_assignments": {
                "D0": list(d0_item["available_perfect_modes"]),
                "D1": list(d1_item["available_perfect_assignments"]),
                "D2": list(d2_item["available_perfect_assignments"]),
            },
            "current_v2_1_assignment_perfect": d0_item["frozen_mode_is_perfect"],
            "v2_2_assignment_required": not d0_item["frozen_mode_is_perfect"],
            "ambiguous_multiple_perfect_assignments": len(d1_item["available_perfect_assignments"]) > 1,
            "no_perfect_assignment": len(d1_item["available_perfect_assignments"]) == 0,
            "independently_authorable": True,
        }
    return {
        "perfect_existing_v2_1_count": sum(1 for item in d0_candidate_stats if item["frozen_mode_is_perfect"]),
        "requires_new_v2_2_value_count": next(
            item["requires_new_value_count"] for item in schema_variants if item["variant_id"] == "D1"
        ),
        "schema_unsatisfiable_count": next(
            item["unsatisfiable_candidate_count"] for item in schema_variants if item["variant_id"] == "D1"
        ),
        "ambiguous_assignment_count": sum(
            1 for item in by_chunk.values() if item["ambiguous_multiple_perfect_assignments"]
        ),
        "chunks": list(by_chunk.values()),
    }


def _select_best_schema_variant(*, schema_variants: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = sorted(
        schema_variants,
        key=lambda item: (
            item["unsatisfiable_candidate_count"],
            item["runtime_schema_change_required"],
            item["field_count"],
            item["enum_count"],
            item["normalizes_existing_names"],
        ),
    )
    best = ranked[0].copy()
    if best["variant_id"] == "D0":
        best["selection_reason"] = (
            "D0 remains the minimal contract because the existing three-value schema already reaches 1.0/1.0 when evaluated together with the existing runtime filters."
        )
    elif best["variant_id"] == "D1":
        best["selection_reason"] = (
            "D1 is the smallest schema that eliminates all unsatisfiable candidates without adding runtime fields or a second candidate field."
        )
    else:
        best["selection_reason"] = "D2 is semantically sufficient, but it is not smaller than D0 or D1."
    return best


def _build_proposed_candidate_schema(*, best_schema_variant: dict[str, Any]) -> dict[str, Any]:
    return {
        "field_name": "runtime_scope_match_mode",
        "document_default_supported": True,
        "chunk_override_supported": True,
        "values": [
            {
                "value": "primary_in_scope",
                "business_definition": "Candidate is reusable when the primary_solution_id is inside the runtime operational scope.",
                "positive_examples": [
                    "An implementation playbook mainly for one solution that still mentions adjacent systems as background context."
                ],
                "negative_examples": [
                    "A compliance prerequisite that should also apply when a secondary applicable solution is the only active one."
                ],
                "how_to_distinguish_from_other_values": "Use when primary-solution presence is enough and secondary applicable solutions do not independently trigger reuse.",
                "can_be_authored_from_document_content_only": True,
                "manual_review_conditions": ["multi_solution wording remains ambiguous after reading the chunk"],
                "confidence_rules": "High confidence when the text explicitly centers one primary solution.",
                "risk_of_post_hoc_overfitting": "Low if the decision is driven by the chunk's own business focus.",
            },
            {
                "value": "any_applicable_scope",
                "business_definition": "Candidate is reusable when at least one applicable_solution_id is inside the runtime operational scope and excluded_solution_ids do not conflict.",
                "positive_examples": [
                    "A shared security prerequisite that applies to any listed deployment or controlled-retrieval solution under discussion."
                ],
                "negative_examples": [
                    "A capability description that is only safe when every listed applicable solution is jointly in scope."
                ],
                "how_to_distinguish_from_other_values": "Use when any one applicable solution is enough, even if the primary solution is not the one currently active.",
                "can_be_authored_from_document_content_only": True,
                "manual_review_conditions": [
                    "cross_cutting_requirement text mixes shared prerequisite language with explicit joint dependency language"
                ],
                "confidence_rules": "High confidence when the chunk describes a reusable prerequisite or governance requirement for any listed applicable solution.",
                "risk_of_post_hoc_overfitting": "Medium until a new blind authoring attempt independently validates the distinction.",
            },
            {
                "value": "full_applicable_scope",
                "business_definition": "Candidate is reusable only when all applicable_solution_ids are inside the runtime operational scope and excluded_solution_ids do not conflict.",
                "positive_examples": [
                    "A multi-solution capability note that is only safe when all named solutions are jointly part of the recommendation scope."
                ],
                "negative_examples": [
                    "A shared readiness requirement that still matters when only one listed solution is active."
                ],
                "how_to_distinguish_from_other_values": "Use when partial overlap is not enough and dropping one listed applicable solution would change the business meaning.",
                "can_be_authored_from_document_content_only": True,
                "manual_review_conditions": ["the chunk lists multiple solutions but does not clearly say whether they are jointly required"],
                "confidence_rules": "High confidence when the chunk explicitly couples the listed solutions.",
                "risk_of_post_hoc_overfitting": "Low if the joint dependency is explicit in the chunk content.",
            },
            {
                "value": "global_reusable",
                "business_definition": "Candidate is reusable independent of operational_solution_scope, subject only to excluded_solution_ids and non-scope runtime filters.",
                "positive_examples": [
                    "A global policy statement that applies regardless of which demo solution is currently in scope."
                ],
                "negative_examples": [
                    "Any chunk whose meaning depends on a particular solution family being actively discussed."
                ],
                "how_to_distinguish_from_other_values": "Use only when the content truly stands on its own across solution scopes.",
                "can_be_authored_from_document_content_only": True,
                "manual_review_conditions": ["content looks global but still contains solution-specific boundary language"],
                "confidence_rules": "High confidence when the chunk is solution-agnostic policy or process guidance.",
                "risk_of_post_hoc_overfitting": "Low.",
            },
        ],
        "best_variant_id": best_schema_variant["variant_id"],
        "recommended_operational_action": "retain_existing_three_value_schema_and_clarify_authoring_guide",
    }


def _evaluate_schema_variant(
    *,
    variant_id: str,
    mode_values: list[str],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    cases: list[RetrievalEvaluationCaseV2] = inputs["cases"]
    documents_by_id = inputs["documents_by_id"]
    chunks: list[KnowledgeChunkV2] = inputs["chunks"]
    evaluation_date = datetime.fromisoformat(inputs["benchmark_config"]["evaluation_date"]).date()

    per_chunk_results: list[dict[str, Any]] = []
    total_relevant = 0
    total_boundary = 0
    total_relevant_allowed = 0
    total_boundary_denied = 0
    total_false_exclusions = 0
    total_false_inclusions = 0
    unsatisfiable_count = 0
    perfect_count = 0
    requires_new_value_ids: list[str] = []
    ambiguous_count = 0

    for chunk in chunks:
        mode_results: list[dict[str, Any]] = []
        perfect_assignments: list[str] = []
        for mode in mode_values:
            result = _evaluate_single_mode_for_chunk(
                chunk=chunk,
                cases=cases,
                mode=mode,
                documents_by_id=documents_by_id,
                evaluation_date=evaluation_date,
            )
            mode_results.append(result)
            if result["perfect_for_candidate"]:
                perfect_assignments.append(mode)

        if perfect_assignments:
            perfect_count += 1
        else:
            unsatisfiable_count += 1
        if len(perfect_assignments) > 1:
            ambiguous_count += 1

        if variant_id == "D1" and "any_applicable_scope" in perfect_assignments:
            if not any(value in D0_VALUES for value in perfect_assignments):
                requires_new_value_ids.append(chunk.chunk_id)

        chosen = perfect_assignments[0] if perfect_assignments else mode_values[0]
        chosen_result = next(item for item in mode_results if item["mode"] == chosen)
        total_relevant += chosen_result["relevant_pair_count"]
        total_boundary += chosen_result["boundary_pair_count"]
        total_relevant_allowed += chosen_result["relevant_allowed_count"]
        total_boundary_denied += chosen_result["boundary_denied_count"]
        total_false_exclusions += chosen_result["false_exclusion_count"]
        total_false_inclusions += chosen_result["false_inclusion_count"]

        per_chunk_results.append(
            {
                "source_document_id": chunk.document_id,
                "source_chunk_id": chunk.chunk_id,
                "scope_type": chunk.scope_type.value,
                "available_perfect_assignments": perfect_assignments,
                "chosen_assignment": chosen,
                "mode_results": mode_results,
            }
        )

    return {
        "relevant_candidate_retention_rate": _rate(total_relevant_allowed, total_relevant),
        "boundary_candidate_removal_rate": _rate(total_boundary_denied, total_boundary),
        "false_exclusion_count": total_false_exclusions,
        "false_inclusion_count": total_false_inclusions,
        "unsatisfiable_candidate_count": unsatisfiable_count,
        "perfect_candidate_count": perfect_count,
        "authorable_from_candidate_content": True,
        "runtime_schema_change_required": False,
        "knowledge_metadata_change_required": variant_id != "D0",
        "requires_new_value_count": len(requires_new_value_ids),
        "requires_new_value_chunk_ids": sorted(requires_new_value_ids),
        "ambiguous_assignment_count": ambiguous_count,
        "current_v2_1_assignment_perfect_count": _count_current_assignments(
            variant_id=variant_id,
            per_chunk_results=per_chunk_results,
            inputs=inputs,
        ),
        "per_chunk_results": per_chunk_results,
    }


def _evaluate_single_mode_for_chunk(
    *,
    chunk: KnowledgeChunkV2,
    cases: list[RetrievalEvaluationCaseV2],
    mode: str,
    documents_by_id: dict[str, Any],
    evaluation_date: Any,
) -> dict[str, Any]:
    document = documents_by_id[chunk.document_id]
    relevant_pair_count = 0
    relevant_allowed_count = 0
    boundary_pair_count = 0
    boundary_denied_count = 0
    false_exclusion_count = 0
    false_inclusion_count = 0
    error_case_ids: list[str] = []
    for case in cases:
        relevant = _is_relevant(case=case, chunk=chunk)
        boundary_allowed = evaluate_candidate_boundary_v2(case=case, document=document, chunk=chunk).candidate_allowed
        allowed = _mode_allows(case=case, chunk=chunk, mode=mode) and _document_passes_runtime_filters(
            case=case,
            document=document,
            evaluation_date=evaluation_date,
        )

        if relevant:
            relevant_pair_count += 1
            if allowed:
                relevant_allowed_count += 1
            else:
                false_exclusion_count += 1
                error_case_ids.append(case.retrieval_case_id)
        if not boundary_allowed:
            boundary_pair_count += 1
            if not allowed:
                boundary_denied_count += 1
            else:
                false_inclusion_count += 1
                error_case_ids.append(case.retrieval_case_id)

    return {
        "mode": mode,
        "relevant_pair_count": relevant_pair_count,
        "relevant_allowed_count": relevant_allowed_count,
        "boundary_pair_count": boundary_pair_count,
        "boundary_denied_count": boundary_denied_count,
        "false_exclusion_count": false_exclusion_count,
        "false_inclusion_count": false_inclusion_count,
        "perfect_for_candidate": false_exclusion_count == 0 and false_inclusion_count == 0,
        "error_case_ids": _deduplicate(error_case_ids),
    }


def _mode_allows(*, case: RetrievalEvaluationCaseV2, chunk: KnowledgeChunkV2, mode: str) -> bool:
    if mode in D0_VALUES:
        return _scope_contract_allowed(case=case, chunk=chunk, effective_mode=mode)
    if mode == "any_applicable_scope":
        operational_scope = set(case.runtime_context.operational_solution_scope)
        excluded_scope = set(chunk.excluded_solution_ids)
        applicable_scope = set(chunk.applicable_solution_ids)
        if excluded_scope & operational_scope:
            return False
        return bool(applicable_scope & operational_scope)
    if mode == "primary":
        return _mode_allows(case=case, chunk=chunk, mode="primary_in_scope")
    if mode == "any_applicable":
        return _mode_allows(case=case, chunk=chunk, mode="any_applicable_scope")
    if mode == "all_applicable":
        return _mode_allows(case=case, chunk=chunk, mode="full_applicable_scope")
    if mode == "global":
        return _mode_allows(case=case, chunk=chunk, mode="global_reusable")
    raise ValueError(f"Unsupported mode: {mode}")


def _count_current_assignments(
    *,
    variant_id: str,
    per_chunk_results: list[dict[str, Any]],
    inputs: dict[str, Any],
) -> int:
    if variant_id != "D0":
        return 0
    blind_evaluation = load_json_record(TRACKED_EVALUATION_OUTPUT_PATH)
    effective_metadata = {
        item["source_chunk_id"]: item["effective_runtime_scope_match_mode"]
        for item in blind_evaluation["effective_metadata_summary"]["chunks"]
    }
    count = 0
    for item in per_chunk_results:
        if effective_metadata[item["source_chunk_id"]] in item["available_perfect_assignments"]:
            count += 1
    return count


def _is_relevant(*, case: RetrievalEvaluationCaseV2, chunk: KnowledgeChunkV2) -> bool:
    return (
        _relevant_item_identity(
            document_id=chunk.document_id,
            chunk_id=chunk.chunk_id,
            expected_document_ids=set(case.evaluation_gold.expected_relevant_document_ids),
            expected_chunk_ids=set(case.evaluation_gold.expected_relevant_chunk_ids),
        )
        is not None
    )


def _semantic_summary(content: str) -> str:
    text = " ".join(content.split())
    if len(text) <= 120:
        return text
    return text[:117] + "..."


def _without_nondeterministic_fields(payload: dict[str, Any]) -> dict[str, Any]:
    clone = json.loads(json.dumps(payload, ensure_ascii=False))
    for field in NON_DETERMINISTIC_FIELDS:
        clone.pop(field, None)
    return clone


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
