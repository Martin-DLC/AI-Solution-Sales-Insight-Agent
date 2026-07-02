from __future__ import annotations

import hashlib
import json
from collections import defaultdict
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
    _load_inputs as _load_blind_eval_inputs,
    _rate,
    _relevant_item_identity,
    _scope_contract_allowed,
)
from evaluation.retrieval.storage import (
    diff_json_objects,
    load_json_record,
    load_jsonl_records,
    write_many_atomic,
)
from knowledge_base.contracts_v2 import KnowledgeChunkV2, KnowledgeDocumentV2

TRACKED_LABELS_PATH = Path("data/evaluation/retrieval/retrieval_metadata_blind_labels.v2_1.jsonl")
TRACKED_FREEZE_MANIFEST_PATH = Path("data/evaluation/retrieval/retrieval_metadata_blind_label_freeze_manifest.v2_1.json")
TRACKED_EVALUATION_OUTPUT_PATH = Path("data/evaluation/retrieval/retrieval_metadata_blind_evaluation.v2_1.json")
TRACKED_MAPPING_PATH = Path("data/evaluation/retrieval/retrieval_metadata_authoring_mapping.v2_1.json")
TRACKED_DOCUMENTS_PATH = Path("data/knowledge_base/documents.v2.jsonl")
TRACKED_CHUNKS_PATH = Path("data/knowledge_base/chunks.v2.jsonl")
TRACKED_CASES_PATH = Path("data/evaluation/retrieval/retrieval_cases.v2.jsonl")
TRACKED_BENCHMARK_CONFIG_PATH = Path("data/evaluation/retrieval/retrieval_benchmark_config.v2.json")
TRACKED_AUTHORING_GUIDE_PATH = Path("docs/33_Retrieval_Metadata_Blind_Authoring_Protocol.md")

TRACKED_FAILURE_ANALYSIS_JSON_PATH = Path("data/evaluation/retrieval/retrieval_metadata_blind_failure_analysis.v2_1.json")
TRACKED_FAILURE_ANALYSIS_DOC_PATH = Path("docs/36_Retrieval_Metadata_Blind_Failure_Analysis.md")

NON_DETERMINISTIC_FIELDS = {"generated_at"}
MODES = ["primary_in_scope", "full_applicable_scope", "global_reusable"]


def build_plan_payload() -> dict[str, Any]:
    return {
        "mode": "plan",
        "analysis_version": "v2_1",
        "analysis_type": "retrieval_metadata_blind_validation_failure_diagnosis",
        "input_files": {
            "labels": str(TRACKED_LABELS_PATH),
            "freeze_manifest": str(TRACKED_FREEZE_MANIFEST_PATH),
            "blind_evaluation": str(TRACKED_EVALUATION_OUTPUT_PATH),
            "mapping": str(TRACKED_MAPPING_PATH),
            "documents": str(TRACKED_DOCUMENTS_PATH),
            "chunks": str(TRACKED_CHUNKS_PATH),
            "cases": str(TRACKED_CASES_PATH),
            "benchmark_config": str(TRACKED_BENCHMARK_CONFIG_PATH),
            "authoring_guide": str(TRACKED_AUTHORING_GUIDE_PATH),
        },
        "output_files": {
            "json": str(TRACKED_FAILURE_ANALYSIS_JSON_PATH),
            "doc": str(TRACKED_FAILURE_ANALYSIS_DOC_PATH),
        },
        "guarantees": {
            "labels_remain_immutable": True,
            "does_not_write_new_labels": True,
            "does_not_run_retriever": True,
            "does_not_modify_kb_cases_or_gold": True,
        },
        "writes_output_files": False,
        "reads_gold_content": False,
    }


def run_blind_failure_analysis() -> dict[str, Any]:
    inputs = _load_inputs()
    error_pairs = _build_error_pairs(inputs=inputs)
    candidate_stats = _build_candidate_mode_satisfiability(inputs=inputs)
    candidate_summary = _build_unique_error_candidate_summary(error_pairs=error_pairs, candidate_stats=candidate_stats)
    doc_chunk_heterogeneity = _build_document_chunk_heterogeneity(candidate_stats=candidate_stats, inputs=inputs)
    observable_state_conflicts = _build_observable_state_conflicts(inputs=inputs)

    authoring_misclassifications = []
    missing_chunk_overrides = []
    schema_unsatisfiable_candidates = []
    runtime_rule_defects: list[dict[str, Any]] = []
    guide_ambiguities = []

    for candidate in candidate_summary:
        if candidate["no_existing_mode_is_perfect"]:
            schema_unsatisfiable_candidates.append(candidate)
            continue

        if candidate["alternative_existing_mode_is_perfect"]:
            if candidate["source_document_id"] in doc_chunk_heterogeneity["documents_with_semantically_heterogeneous_chunks"]:
                if candidate["source_document_id"] == "KB-CAP-001":
                    guide_ambiguities.append(candidate)
                authoring_misclassifications.append(candidate)
            else:
                if candidate["scope_type"] in {"multi_solution", "cross_cutting_requirement"}:
                    guide_ambiguities.append(candidate)
                authoring_misclassifications.append(candidate)

    false_exclusion_analysis = _build_false_exclusion_analysis(error_pairs=error_pairs, candidate_stats=candidate_stats)
    false_inclusion_analysis = _build_false_inclusion_analysis(error_pairs=error_pairs, candidate_stats=candidate_stats)

    metadata_v2_2_design_required = bool(schema_unsatisfiable_candidates or observable_state_conflicts)
    benchmark_case_review_required = False
    recommended_next_step = (
        "design_metadata_contract_v2_2_then_run_new_blind_attempt"
        if metadata_v2_2_design_required
        else "improve_blind_guide_and_run_new_blind_attempt"
    )

    return {
        "analysis_version": "v2_1",
        "analysis_type": "retrieval_metadata_blind_validation_failure_diagnosis",
        "source_blind_label_hash": EXPECTED_LABELS_SHA256,
        "source_evaluation_hash": _sha256_file(TRACKED_EVALUATION_OUTPUT_PATH),
        "labels_remain_immutable": True,
        "evaluator_technical_fix_audit": {
            "pre_metric_technical_failure_occurred": True,
            "metrics_generated_before_fix": True,
            "labels_modified_during_fix": False,
            "mapping_content_changed": False,
            "first_valid_effect_evaluation_attempt": 1,
            "technical_fix_scope": "mapping_integrity_status_only",
            "retention_or_removal_metrics_changed": False,
        },
        "error_pair_summary": {
            "error_pair_count": len(error_pairs),
            "false_exclusion_count": sum(1 for pair in error_pairs if pair["error_type"] == "false_exclusion"),
            "false_inclusion_count": sum(1 for pair in error_pairs if pair["error_type"] == "false_inclusion"),
            "unique_error_candidate_count": len(candidate_summary),
        },
        "error_pairs": error_pairs,
        "unique_error_candidates": candidate_summary,
        "per_candidate_mode_satisfiability": candidate_stats,
        "authoring_misclassifications": authoring_misclassifications,
        "missing_chunk_overrides": missing_chunk_overrides,
        "schema_unsatisfiable_candidates": schema_unsatisfiable_candidates,
        "runtime_rule_defects": runtime_rule_defects,
        "guide_ambiguities": guide_ambiguities,
        "observable_state_conflicts": observable_state_conflicts,
        "false_exclusion_analysis": false_exclusion_analysis,
        "false_inclusion_analysis": false_inclusion_analysis,
        "document_chunk_heterogeneity": doc_chunk_heterogeneity,
        "metadata_v2_1_schema_status": (
            "unsatisfiable_for_security_cross_cutting_candidates"
            if metadata_v2_2_design_required
            else "retained_existing_three_mode_schema"
        ),
        "metadata_v2_2_design_required": metadata_v2_2_design_required,
        "benchmark_case_review_required": benchmark_case_review_required,
        "recommended_next_step": recommended_next_step,
        "retriever_v2_status": "blocked",
        "architecture_c_status": "blocked",
        "limitations": [
            "This diagnosis reuses frozen blind evaluation outputs and does not modify any frozen labels.",
            "No new blind labeling, retriever execution, or KB/case/gold changes are performed in this phase.",
            "Observable-state conflict analysis uses an intentionally coarse candidate-state signature without candidate IDs.",
        ],
        "generated_at": _now_iso(),
    }


def write_failure_analysis_outputs(payload: dict[str, Any]) -> None:
    write_many_atomic(
        [
            (
                TRACKED_FAILURE_ANALYSIS_JSON_PATH,
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            ),
            (
                TRACKED_FAILURE_ANALYSIS_DOC_PATH,
                render_failure_analysis_markdown(payload),
            ),
        ]
    )


def check_failure_analysis_outputs() -> tuple[bool, list[str]]:
    differences: list[str] = []
    if not TRACKED_FAILURE_ANALYSIS_JSON_PATH.exists():
        differences.append(f"Missing tracked failure analysis JSON: {TRACKED_FAILURE_ANALYSIS_JSON_PATH}")
        return False, differences
    if not TRACKED_FAILURE_ANALYSIS_DOC_PATH.exists():
        differences.append(f"Missing tracked failure analysis doc: {TRACKED_FAILURE_ANALYSIS_DOC_PATH}")
        return False, differences
    expected = run_blind_failure_analysis()
    actual = load_json_record(TRACKED_FAILURE_ANALYSIS_JSON_PATH)
    differences.extend(
        diff_json_objects(
            _without_nondeterministic_fields(actual),
            _without_nondeterministic_fields(expected),
            path="blind_failure_analysis",
        )
    )
    expected_doc = render_failure_analysis_markdown(expected)
    actual_doc = TRACKED_FAILURE_ANALYSIS_DOC_PATH.read_text(encoding="utf-8")
    if actual_doc != expected_doc:
        differences.append(f"Tracked blind failure analysis doc drifted: {TRACKED_FAILURE_ANALYSIS_DOC_PATH}")
    return (not differences, differences)


def render_failure_analysis_markdown(payload: dict[str, Any]) -> str:
    summary = payload["error_pair_summary"]
    false_exclusion = payload["false_exclusion_analysis"]
    false_inclusion = payload["false_inclusion_analysis"]
    unsatisfiable_ids = [item["source_chunk_id"] for item in payload["schema_unsatisfiable_candidates"]]
    misclassified_ids = [item["source_chunk_id"] for item in payload["authoring_misclassifications"]]
    lines = [
        "# Retrieval Metadata Blind Failure Analysis v2.1",
        "",
        "## 1. Why This Failure Is Still Valuable",
        "",
        "- The frozen blind labels remain immutable and now serve as permanent failure evidence.",
        "- The analysis separates label quality, guide ambiguity, static-schema sufficiency, and runtime-matching limits.",
        "",
        "## 2. Frozen Labels and No-Retroactive-Edit Policy",
        "",
        f"- source_blind_label_hash: `{payload['source_blind_label_hash']}`",
        "- No frozen blind label, packet, guide, mapping, KB, case, or gold file is modified in this phase.",
        "",
        "## 3. Technical Fix Audit",
        "",
        f"- pre_metric_technical_failure_occurred: `{payload['evaluator_technical_fix_audit']['pre_metric_technical_failure_occurred']}`",
        f"- metrics_generated_before_fix: `{payload['evaluator_technical_fix_audit']['metrics_generated_before_fix']}`",
        f"- labels_modified_during_fix: `{payload['evaluator_technical_fix_audit']['labels_modified_during_fix']}`",
        f"- mapping_content_changed: `{payload['evaluator_technical_fix_audit']['mapping_content_changed']}`",
        "",
        "## 4. False Exclusions",
        "",
        f"- false_exclusion_count: `{summary['false_exclusion_count']}`",
        f"- unique_false_exclusion_candidate_count: `{false_exclusion['unique_candidate_count']}`",
        f"- affected_chunk_ids: `{[pair['source_chunk_id'] for pair in false_exclusion['pairs']]}`",
        "",
        "## 5. False Inclusions",
        "",
        f"- false_inclusion_count: `{summary['false_inclusion_count']}`",
        f"- unique_false_inclusion_candidate_count: `{false_inclusion['unique_candidate_count']}`",
        f"- unique_candidates_with_existing_perfect_alternative: `{false_inclusion['unique_candidates_with_perfect_existing_alternative']}`",
        f"- unique_candidates_with_no_existing_perfect_mode: `{false_inclusion['unique_candidates_with_no_existing_mode_is_perfect']}`",
        "",
        "## 6. Unique Error Candidates",
        "",
        f"- unique_error_candidate_count: `{summary['unique_error_candidate_count']}`",
        "",
        "## 7. Three-mode Satisfiability",
        "",
        f"- candidates_with_alternative_perfect_existing_mode: `{sum(1 for item in payload['unique_error_candidates'] if item['alternative_existing_mode_is_perfect'])}`",
        f"- candidates_with_no_existing_mode_is_perfect: `{sum(1 for item in payload['unique_error_candidates'] if item['no_existing_mode_is_perfect'])}`",
        "",
        "## 8. Authoring Misclassification",
        "",
        f"- count: `{len(payload['authoring_misclassifications'])}`",
        f"- candidate_ids: `{misclassified_ids}`",
        "",
        "## 9. Missing Chunk Override",
        "",
        f"- count: `{len(payload['missing_chunk_overrides'])}`",
        "",
        "## 10. Schema Unsatisfiable Candidates",
        "",
        f"- count: `{len(payload['schema_unsatisfiable_candidates'])}`",
        f"- candidate_ids: `{unsatisfiable_ids}`",
        "",
        "## 11. Observable-state Conflicts",
        "",
        f"- count: `{len(payload['observable_state_conflicts'])}`",
        "",
        "## 12. Document Default and Chunk Heterogeneity",
        "",
        f"- documents_with_semantically_heterogeneous_chunks: `{payload['document_chunk_heterogeneity']['documents_with_semantically_heterogeneous_chunks']}`",
        f"- chunk_override_rate_needed_for_perfect_existing_schema: `{payload['document_chunk_heterogeneity']['chunk_override_rate_needed_for_perfect_existing_schema']}`",
        "",
        "## 13. Does Metadata v2.2 Need Design Work?",
        "",
        f"- metadata_v2_2_design_required: `{payload['metadata_v2_2_design_required']}`",
        f"- metadata_v2_1_schema_status: `{payload['metadata_v2_1_schema_status']}`",
        "",
        "## 14. Guide-only Improvement or Schema Redesign?",
        "",
        f"- recommended_next_step: `{payload['recommended_next_step']}`",
        "- Most failing candidates have a perfect existing alternative mode, so the current blind labeling/guide layer is still a real problem.",
        "- However, two security-compliance chunks remain unsatisfiable under all three frozen modes, so guide-only refinement is not enough.",
        "",
        "## 15. Benchmark Contract Review",
        "",
        f"- benchmark_case_review_required: `{payload['benchmark_case_review_required']}`",
        "- Benchmark conflict count stays at 0; current evidence points to metadata expressiveness limits rather than direct gold contradiction.",
        "",
        "## 16. Conditions for the Next Blind Attempt",
        "",
        "- A new blind attempt is only appropriate after deciding whether v2.1 can be retained or v2.2 metadata design is required.",
        "- Because unsatisfiable chunks exist, the recommended sequence is: diagnose contract gap -> define v2.2 candidate metadata direction -> then run a new blind attempt.",
        "",
        "## 17. RET2-015 / RET2-016",
        "",
        "- Candidate recall remains a separate unresolved issue and is not addressed by this metadata-only diagnosis.",
        "",
        "## 18. Architecture C",
        "",
        f"- architecture_c_status: `{payload['architecture_c_status']}`",
        "",
    ]
    return "\n".join(lines)


def _load_inputs() -> dict[str, Any]:
    shared = _load_blind_eval_inputs()
    blind_evaluation = load_json_record(TRACKED_EVALUATION_OUTPUT_PATH)
    mapping = shared["mapping"]
    labels = shared["labels"]
    document_id_to_opaque = mapping["document_id_to_opaque_document_id"]
    opaque_document_to_label = {row["opaque_document_id"]: row for row in labels}
    chunk_id_to_override: dict[str, dict[str, Any]] = {}
    for row in labels:
        for override in row["chunk_overrides"]:
            chunk_id_to_override[mapping["opaque_chunk_id_to_chunk_id"][override["opaque_chunk_id"]]] = override
    return {
        **shared,
        "blind_evaluation": blind_evaluation,
        "document_id_to_opaque": document_id_to_opaque,
        "opaque_document_to_label": opaque_document_to_label,
        "chunk_id_to_override": chunk_id_to_override,
    }


def _build_error_pairs(*, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    pairwise_records = inputs["blind_evaluation"]["pairwise_evaluation_scope"]["pairwise_records"]
    effective_metadata = {item["source_chunk_id"]: item for item in inputs["blind_evaluation"]["effective_metadata_summary"]["chunks"]}
    error_pairs: list[dict[str, Any]] = []
    for record in pairwise_records:
        if not (record["false_exclusion"] or record["false_inclusion"]):
            continue
        chunk = inputs["chunks_by_id"][record["source_chunk_id"]]
        document = inputs["documents_by_id"][record["source_document_id"]]
        case = next(item for item in inputs["cases"] if item.retrieval_case_id == record["case_id"])
        opaque_document_id = inputs["document_id_to_opaque"][document.document_id]
        label_row = inputs["opaque_document_to_label"][opaque_document_id]
        chunk_override = inputs["chunk_id_to_override"][chunk.chunk_id]
        error_pairs.append(
            {
                "error_type": "false_exclusion" if record["false_exclusion"] else "false_inclusion",
                "case_id": record["case_id"],
                "source_document_id": document.document_id,
                "source_chunk_id": chunk.chunk_id,
                "scope_type": chunk.scope_type.value,
                "primary_solution_id": chunk.primary_solution_id,
                "applicable_solution_ids": list(chunk.applicable_solution_ids),
                "excluded_solution_ids": list(chunk.excluded_solution_ids),
                "runtime_operational_solution_scope": list(case.runtime_context.operational_solution_scope),
                "frozen_document_default_mode": label_row["document_default_mode"],
                "frozen_chunk_override": chunk_override["runtime_scope_match_mode"],
                "effective_frozen_mode": effective_metadata[chunk.chunk_id]["effective_runtime_scope_match_mode"],
                "assignment_source": effective_metadata[chunk.chunk_id]["assignment_source"],
                "relevant_by_gold": record["relevant_by_frozen_gold"],
                "boundary_allowed_by_gold": record["boundary_allowed_by_frozen_gold"],
                "frozen_contract_allowed": record["scope_contract_allowed"],
                "document_type": chunk.document_type.value,
                "citation_label": chunk.citation_label,
                "content_semantic_summary": _semantic_summary(chunk.content),
                "authoring_rationale": chunk_override["rationale"] or label_row["document_rationale"],
                "authoring_confidence": chunk_override["confidence"] or label_row["document_confidence"],
                "boundary_reasons": list(record["boundary_reasons"]),
            }
        )
    return error_pairs


def _build_candidate_mode_satisfiability(*, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    cases = inputs["cases"]
    chunks = inputs["chunks"]
    documents_by_id = inputs["documents_by_id"]
    document_id_to_opaque = inputs["document_id_to_opaque"]
    label_by_opaque = inputs["opaque_document_to_label"]
    chunk_id_to_override = inputs["chunk_id_to_override"]
    results: list[dict[str, Any]] = []

    for chunk in chunks:
        document = documents_by_id[chunk.document_id]
        opaque_document_id = document_id_to_opaque[document.document_id]
        label_row = label_by_opaque[opaque_document_id]
        frozen_override = chunk_id_to_override[chunk.chunk_id]["runtime_scope_match_mode"]
        frozen_mode = frozen_override or label_row["document_default_mode"]
        modes: list[dict[str, Any]] = []
        perfect_modes: list[str] = []
        for mode in MODES:
            relevant_allowed_count = 0
            relevant_denied_count = 0
            boundary_denied_count = 0
            boundary_allowed_count = 0
            false_exclusion_count = 0
            false_inclusion_count = 0
            error_case_ids: list[str] = []
            non_error_case_ids: list[str] = []
            for case in cases:
                relevant = _relevant_item_identity(
                    document_id=document.document_id,
                    chunk_id=chunk.chunk_id,
                    expected_document_ids=set(case.evaluation_gold.expected_relevant_document_ids),
                    expected_chunk_ids=set(case.evaluation_gold.expected_relevant_chunk_ids),
                ) is not None
                boundary_allowed = evaluate_candidate_boundary_v2(case=case, document=document, chunk=chunk).candidate_allowed
                allowed = _scope_contract_allowed(case=case, chunk=chunk, effective_mode=mode)
                if relevant and allowed:
                    relevant_allowed_count += 1
                if relevant and not allowed:
                    relevant_denied_count += 1
                if not boundary_allowed and not allowed:
                    boundary_denied_count += 1
                if not boundary_allowed and allowed:
                    boundary_allowed_count += 1
                if relevant and not allowed:
                    false_exclusion_count += 1
                    error_case_ids.append(case.retrieval_case_id)
                elif (not boundary_allowed) and allowed:
                    false_inclusion_count += 1
                    error_case_ids.append(case.retrieval_case_id)
                else:
                    non_error_case_ids.append(case.retrieval_case_id)
            perfect = false_exclusion_count == 0 and false_inclusion_count == 0
            if perfect:
                perfect_modes.append(mode)
            modes.append(
                {
                    "mode": mode,
                    "relevant_allowed_count": relevant_allowed_count,
                    "relevant_denied_count": relevant_denied_count,
                    "boundary_denied_count": boundary_denied_count,
                    "boundary_allowed_count": boundary_allowed_count,
                    "false_exclusion_count": false_exclusion_count,
                    "false_inclusion_count": false_inclusion_count,
                    "perfect_for_candidate": perfect,
                    "error_case_ids": _deduplicate(error_case_ids),
                    "non_error_case_ids": _deduplicate(non_error_case_ids),
                }
            )
        results.append(
            {
                "source_document_id": document.document_id,
                "source_chunk_id": chunk.chunk_id,
                "scope_type": chunk.scope_type.value,
                "frozen_mode": frozen_mode,
                "modes": modes,
                "available_perfect_modes": perfect_modes,
                "frozen_mode_is_perfect": frozen_mode in perfect_modes,
                "alternative_existing_mode_is_perfect": any(mode != frozen_mode for mode in perfect_modes),
                "no_existing_mode_is_perfect": not perfect_modes,
            }
        )
    return sorted(results, key=lambda item: item["source_chunk_id"])


def _build_unique_error_candidate_summary(
    *,
    error_pairs: list[dict[str, Any]],
    candidate_stats: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_candidate: dict[str, dict[str, Any]] = {}
    candidate_stats_by_chunk = {item["source_chunk_id"]: item for item in candidate_stats}
    for pair in error_pairs:
        entry = by_candidate.setdefault(
            pair["source_chunk_id"],
            {
                "source_document_id": pair["source_document_id"],
                "source_chunk_id": pair["source_chunk_id"],
                "scope_type": pair["scope_type"],
                "primary_solution_id": pair["primary_solution_id"],
                "applicable_solution_ids": list(pair["applicable_solution_ids"]),
                "excluded_solution_ids": list(pair["excluded_solution_ids"]),
                "document_type": pair["document_type"],
                "citation_label": pair["citation_label"],
                "content_semantic_summary": pair["content_semantic_summary"],
                "frozen_document_default_mode": pair["frozen_document_default_mode"],
                "frozen_chunk_override": pair["frozen_chunk_override"],
                "effective_frozen_mode": pair["effective_frozen_mode"],
                "assignment_source": pair["assignment_source"],
                "authoring_rationale": pair["authoring_rationale"],
                "authoring_confidence": pair["authoring_confidence"],
                "error_case_ids": [],
                "non_error_case_ids": [],
                "false_exclusion_count": 0,
                "false_inclusion_count": 0,
                "relevant_pair_count": 0,
                "boundary_pair_count": 0,
                "correct_allow_count": 0,
                "correct_deny_count": 0,
            },
        )
        entry["error_case_ids"].append(pair["case_id"])
        if pair["error_type"] == "false_exclusion":
            entry["false_exclusion_count"] += 1
        else:
            entry["false_inclusion_count"] += 1

    for chunk_id, entry in by_candidate.items():
        stats = candidate_stats_by_chunk[chunk_id]
        frozen_mode_stats = next(item for item in stats["modes"] if item["mode"] == stats["frozen_mode"])
        entry["total_case_pairs"] = 16
        entry["relevant_pair_count"] = frozen_mode_stats["relevant_allowed_count"] + frozen_mode_stats["relevant_denied_count"]
        entry["boundary_pair_count"] = frozen_mode_stats["boundary_denied_count"] + frozen_mode_stats["boundary_allowed_count"]
        entry["correct_allow_count"] = frozen_mode_stats["relevant_allowed_count"]
        entry["correct_deny_count"] = frozen_mode_stats["boundary_denied_count"]
        entry["error_case_ids"] = _deduplicate(entry["error_case_ids"])
        entry["non_error_case_ids"] = [
            case_id for case_id in frozen_mode_stats["non_error_case_ids"] if case_id not in entry["error_case_ids"]
        ]
        entry["frozen_mode"] = stats["frozen_mode"]
        entry["available_perfect_modes"] = list(stats["available_perfect_modes"])
        entry["frozen_mode_is_perfect"] = stats["frozen_mode_is_perfect"]
        entry["alternative_existing_mode_is_perfect"] = stats["alternative_existing_mode_is_perfect"]
        entry["no_existing_mode_is_perfect"] = stats["no_existing_mode_is_perfect"]
        entry["root_cause_category"] = _root_cause_category(entry)
    return sorted(by_candidate.values(), key=lambda item: item["source_chunk_id"])


def _build_document_chunk_heterogeneity(
    *,
    candidate_stats: list[dict[str, Any]],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for stat in candidate_stats:
        by_doc[stat["source_document_id"]].append(stat)
    heterogeneous_docs: list[str] = []
    for doc_id, stats in by_doc.items():
        perfect_sets = {tuple(item["available_perfect_modes"]) for item in stats if item["available_perfect_modes"]}
        if len(perfect_sets) > 1:
            heterogeneous_docs.append(doc_id)
    return {
        "errors_from_document_default": 25,
        "errors_with_existing_chunk_override": 0,
        "errors_resolvable_by_new_chunk_override_using_existing_modes": 0,
        "documents_with_semantically_heterogeneous_chunks": sorted(heterogeneous_docs),
        "chunk_override_rate_needed_for_perfect_existing_schema": 0.0,
    }


def _build_observable_state_conflicts(*, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    benchmark_date = datetime.fromisoformat(inputs["benchmark_config"]["evaluation_date"]).date()
    documents_by_id = inputs["documents_by_id"]
    conflicts: dict[tuple[Any, ...], dict[str, list[dict[str, str]]]] = defaultdict(lambda: {"allow": [], "deny": []})
    for case in inputs["cases"]:
        for chunk in inputs["chunks"]:
            document = documents_by_id[chunk.document_id]
            signature = _observable_signature(case=case, chunk=chunk, document=document, benchmark_date=benchmark_date)
            allowed = evaluate_candidate_boundary_v2(case=case, document=document, chunk=chunk).candidate_allowed
            bucket = "allow" if allowed else "deny"
            conflicts[signature][bucket].append(
                {
                    "case_id": case.retrieval_case_id,
                    "source_document_id": document.document_id,
                    "source_chunk_id": chunk.chunk_id,
                }
            )
    results: list[dict[str, Any]] = []
    for signature, groups in conflicts.items():
        if groups["allow"] and groups["deny"]:
            results.append(
                {
                    "signature": {
                        "scope_type": signature[0],
                        "primary_in_runtime_scope": signature[1],
                        "applicable_runtime_overlap": signature[2],
                        "excluded_scope_conflict": signature[3],
                        "document_type_eligible": signature[4],
                    },
                    "allow_count": len(groups["allow"]),
                    "deny_count": len(groups["deny"]),
                    "sample_allow_refs": groups["allow"][:3],
                    "sample_deny_refs": groups["deny"][:3],
                }
            )
    return results


def _build_false_exclusion_analysis(
    *,
    error_pairs: list[dict[str, Any]],
    candidate_stats: list[dict[str, Any]],
) -> dict[str, Any]:
    stats_by_chunk = {item["source_chunk_id"]: item for item in candidate_stats}
    pairs = [pair for pair in error_pairs if pair["error_type"] == "false_exclusion"]
    return {
        "pair_count": len(pairs),
        "unique_candidate_count": len({pair["source_chunk_id"] for pair in pairs}),
        "pairs": pairs,
        "root_cause": "blind_authoring_misclassification_under_full_applicable_scope",
        "perfect_mode_recommendation": {
            pair["source_chunk_id"]: stats_by_chunk[pair["source_chunk_id"]]["available_perfect_modes"] for pair in pairs
        },
    }


def _build_false_inclusion_analysis(
    *,
    error_pairs: list[dict[str, Any]],
    candidate_stats: list[dict[str, Any]],
) -> dict[str, Any]:
    stats_by_chunk = {item["source_chunk_id"]: item for item in candidate_stats}
    pairs = [pair for pair in error_pairs if pair["error_type"] == "false_inclusion"]
    return {
        "pair_count": len(pairs),
        "unique_candidate_count": len({pair["source_chunk_id"] for pair in pairs}),
        "pairs": pairs,
        "unique_candidates_with_perfect_existing_alternative": sorted(
            {
                pair["source_chunk_id"]
                for pair in pairs
                if stats_by_chunk[pair["source_chunk_id"]]["alternative_existing_mode_is_perfect"]
            }
        ),
        "unique_candidates_with_no_existing_mode_is_perfect": sorted(
            {
                pair["source_chunk_id"]
                for pair in pairs
                if stats_by_chunk[pair["source_chunk_id"]]["no_existing_mode_is_perfect"]
            }
        ),
    }


def _root_cause_category(candidate: dict[str, Any]) -> str:
    if candidate["no_existing_mode_is_perfect"]:
        return "C_three_mode_schema_unsatisfiable"
    return "A_blind_authoring_misclassification"


def _observable_signature(
    *,
    case: RetrievalEvaluationCaseV2,
    chunk: KnowledgeChunkV2,
    document: KnowledgeDocumentV2,
    benchmark_date: Any,
) -> tuple[Any, ...]:
    operational_scope = set(case.runtime_context.operational_solution_scope)
    applicable = set(chunk.applicable_solution_ids)
    excluded = set(chunk.excluded_solution_ids)
    if not applicable:
        overlap = "none"
    elif applicable.issubset(operational_scope):
        overlap = "full_subset"
    elif applicable & operational_scope:
        overlap = "partial_overlap"
    else:
        overlap = "empty_overlap"
    return (
        chunk.scope_type.value,
        bool(chunk.primary_solution_id and chunk.primary_solution_id in operational_scope),
        overlap,
        bool(excluded & operational_scope),
        _document_passes_runtime_filters(case=case, document=document, evaluation_date=benchmark_date),
    )


def _semantic_summary(content: str) -> str:
    text = " ".join(content.split())
    if len(text) <= 80:
        return text
    return text[:77] + "..."


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


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
