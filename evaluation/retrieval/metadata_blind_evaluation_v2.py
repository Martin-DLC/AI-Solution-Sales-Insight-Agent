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
from evaluation.retrieval.storage import (
    diff_json_objects,
    load_json_record,
    load_jsonl_records,
    write_many_atomic,
)
from knowledge_base.contracts_v2 import KnowledgeChunkV2, KnowledgeDocumentV2

TRACKED_LABELS_PATH = Path("data/evaluation/retrieval/retrieval_metadata_blind_labels.v2_1.jsonl")
TRACKED_REPORT_PATH = Path("data/evaluation/retrieval/retrieval_metadata_blind_authoring_report.v2_1.json")
TRACKED_FREEZE_MANIFEST_PATH = Path("data/evaluation/retrieval/retrieval_metadata_blind_label_freeze_manifest.v2_1.json")
TRACKED_MAPPING_PATH = Path("data/evaluation/retrieval/retrieval_metadata_authoring_mapping.v2_1.json")
TRACKED_AUTHORING_MANIFEST_PATH = Path("data/evaluation/retrieval/retrieval_metadata_authoring_manifest.v2_1.json")
TRACKED_RUNTIME_CONTRACT_PROPOSAL_PATH = Path("data/evaluation/retrieval/retrieval_runtime_contract_v2_1_proposal.json")
TRACKED_DOCUMENTS_PATH = Path("data/knowledge_base/documents.v2.jsonl")
TRACKED_CHUNKS_PATH = Path("data/knowledge_base/chunks.v2.jsonl")
TRACKED_CASES_PATH = Path("data/evaluation/retrieval/retrieval_cases.v2.jsonl")
TRACKED_BENCHMARK_CONFIG_PATH = Path("data/evaluation/retrieval/retrieval_benchmark_config.v2.json")

TRACKED_EVALUATION_OUTPUT_PATH = Path("data/evaluation/retrieval/retrieval_metadata_blind_evaluation.v2_1.json")
TRACKED_EVALUATION_DOC_PATH = Path("docs/35_Retrieval_Metadata_Blind_Evaluation.md")

EXPECTED_LABELS_SHA256 = "58729c71ba03adce96f7e89170a9bc52bf637a028a7cfb33f1acd1b504327e92"
EXPECTED_REPORT_SHA256 = "13fce4a4793b3854daeeba0f1d4786ffa72dbe64d9c6b7c6066b8333899ebbc3"
EXPECTED_PACKET_SHA256 = "314135ac2e1d73dc12980bc097fbbb1e58bf9117b044a47c5cbc19e44ac927a9"
EXPECTED_GUIDE_SHA256 = "738a2afc587090de35b302a5575f23f66ac66119bf1e812b02e53138eecf16e7"
EXPECTED_TEMPLATE_SHA256 = "acd9ed60e0f945071f859f6b0f6d8f28dedd3ce23e9f8b2abf45e22d9428d79f"

ALLOWED_MODES = {
    "primary_in_scope",
    "full_applicable_scope",
    "global_reusable",
}

NON_DETERMINISTIC_FIELDS = {"generated_at"}


def build_plan_payload() -> dict[str, Any]:
    freeze_manifest = load_json_record(TRACKED_FREEZE_MANIFEST_PATH)
    authoring_manifest = load_json_record(TRACKED_AUTHORING_MANIFEST_PATH)
    benchmark_config = load_json_record(TRACKED_BENCHMARK_CONFIG_PATH)
    return {
        "mode": "plan",
        "evaluation_version": "v2_1",
        "evaluation_type": "post_freeze_independent_blind_label_evaluation",
        "input_files": {
            "labels": str(TRACKED_LABELS_PATH),
            "authoring_report": str(TRACKED_REPORT_PATH),
            "freeze_manifest": str(TRACKED_FREEZE_MANIFEST_PATH),
            "mapping": str(TRACKED_MAPPING_PATH),
            "authoring_manifest": str(TRACKED_AUTHORING_MANIFEST_PATH),
            "documents": str(TRACKED_DOCUMENTS_PATH),
            "chunks": str(TRACKED_CHUNKS_PATH),
            "cases": str(TRACKED_CASES_PATH),
            "benchmark_config": str(TRACKED_BENCHMARK_CONFIG_PATH),
            "p1_runtime_contract_proposal": str(TRACKED_RUNTIME_CONTRACT_PROPOSAL_PATH),
        },
        "output_files": {
            "json": str(TRACKED_EVALUATION_OUTPUT_PATH),
            "doc": str(TRACKED_EVALUATION_DOC_PATH),
        },
        "provenance_requirements": {
            "freeze_status": "frozen_before_evaluation",
            "evaluation_status_before_run": "not_started",
            "labels_frozen_before_evaluation": True,
            "labels_modified_after_authoring": False,
            "valid_blind_authoring_attempt_number": 1,
            "expected_labels_sha256": EXPECTED_LABELS_SHA256,
            "expected_authoring_report_sha256": EXPECTED_REPORT_SHA256,
            "expected_packet_sha256": EXPECTED_PACKET_SHA256,
            "expected_guide_sha256": EXPECTED_GUIDE_SHA256,
            "expected_template_sha256": EXPECTED_TEMPLATE_SHA256,
            "mapping_sha256": authoring_manifest["mapping_sha256"],
        },
        "pairwise_scope": {
            "case_count": benchmark_config["case_count"],
            "chunk_count": freeze_manifest["chunk_count"],
            "expected_pair_count": benchmark_config["case_count"] * freeze_manifest["chunk_count"],
        },
        "p0_gate": {
            "relevant_candidate_retention_rate_equals": 1.0,
            "boundary_candidate_removal_rate_equals": 1.0,
            "false_exclusion_count_equals": 0,
            "false_inclusion_count_equals": 0,
            "benchmark_contract_conflict_count_equals": 0,
            "mode_static_across_cases": True,
            "case_specific_logic_forbidden": True,
            "gold_used_in_mode_assignment_forbidden": True,
        },
        "writes_output_files": False,
        "reads_gold_content": False,
    }


def run_blind_metadata_evaluation() -> dict[str, Any]:
    inputs = _load_inputs()
    provenance_gate = _build_provenance_gate(inputs=inputs)
    mapping_integrity = _build_mapping_integrity(inputs=inputs)

    payload: dict[str, Any] = {
        "evaluation_version": "v2_1",
        "evaluation_type": "post_freeze_independent_blind_label_evaluation",
        "provenance_gate": provenance_gate,
        "input_hashes": inputs["input_hashes"],
        "mapping_integrity": mapping_integrity,
        "labels_remain_immutable": True,
        "evaluation_does_not_modify_labels": True,
    }

    if not provenance_gate["passed"]:
        payload.update(
            {
                "effective_metadata_summary": {},
                "pairwise_evaluation_scope": {
                    "case_count": len(inputs["cases"]),
                    "chunk_count": len(inputs["chunks"]),
                    "pair_count": 0,
                },
                "overall_metrics": {},
                "per_mode_metrics": {},
                "per_scope_type_metrics": {},
                "false_exclusions": [],
                "false_inclusions": [],
                "benchmark_contract_conflicts": [],
                "p1_vs_p0_comparison": _build_p1_vs_p0_comparison(None, None),
                "evidence_classification": "invalid_provenance_gate_failed",
                "p0_validation_status": "invalid",
                "boundary_contract_validation_status": "invalid",
                "metadata_v2_1_versioning_status": "blocked_provenance_failed",
                "retriever_v2_status": "blocked",
                "ret2_015_016_status": "candidate_recall_unresolved",
                "architecture_c_status": "blocked",
                "limitations": [
                    "Provenance gate failed; no pairwise effectiveness metrics were computed.",
                    "Frozen labels remain immutable and cannot be modified in this evaluation pass.",
                ],
                "generated_at": _now_iso(),
            }
        )
        return payload

    effective_metadata = _build_effective_chunk_metadata(inputs=inputs)
    pairwise_records = _build_pairwise_records(inputs=inputs, effective_metadata=effective_metadata)
    overall_metrics = _build_metrics_summary(pairwise_records)
    per_mode_metrics = _group_metrics(pairwise_records, key_name="effective_mode")
    per_scope_type_metrics = _group_metrics(pairwise_records, key_name="scope_type")
    false_exclusions = _filter_pair_list(pairwise_records, key="false_exclusion")
    false_inclusions = _filter_pair_list(pairwise_records, key="false_inclusion")
    contract_conflicts = _filter_pair_list(pairwise_records, key="benchmark_contract_conflict")
    p1_vs_p0 = _build_p1_vs_p0_comparison(
        overall_metrics["relevant_candidate_retention_rate"],
        overall_metrics["boundary_candidate_removal_rate"],
    )

    p0_passed = (
        provenance_gate["passed"]
        and provenance_gate["authoring_process_was_blind_to_cases_and_gold"]
        and provenance_gate["labels_frozen_before_evaluation"]
        and not provenance_gate["labels_modified_after_authoring"]
        and overall_metrics["relevant_candidate_retention_rate"] == 1.0
        and overall_metrics["boundary_candidate_removal_rate"] == 1.0
        and overall_metrics["false_exclusion_count"] == 0
        and overall_metrics["false_inclusion_count"] == 0
        and overall_metrics["benchmark_contract_conflict_count"] == 0
        and effective_metadata["mode_static_across_cases"]
        and not effective_metadata["case_specific_logic_detected"]
        and not effective_metadata["gold_participated_in_assignment"]
        and effective_metadata["document_count"] == 20
        and effective_metadata["chunk_count"] == 40
    )

    payload.update(
        {
            "effective_metadata_summary": effective_metadata,
            "pairwise_evaluation_scope": {
                "case_count": len(inputs["cases"]),
                "chunk_count": len(inputs["chunks"]),
                "pair_count": len(pairwise_records),
                "pairwise_records": pairwise_records,
            },
            "overall_metrics": overall_metrics,
            "per_mode_metrics": per_mode_metrics,
            "per_scope_type_metrics": per_scope_type_metrics,
            "false_exclusions": false_exclusions,
            "false_inclusions": false_inclusions,
            "benchmark_contract_conflicts": contract_conflicts,
            "p1_vs_p0_comparison": p1_vs_p0,
            "evidence_classification": (
                "P0_blind_authored_independently_validated"
                if p0_passed
                else "P1_content_explainable_not_blind_validated"
            ),
            "p0_validation_status": "passed" if p0_passed else "failed",
            "boundary_contract_validation_status": "passed" if p0_passed else "failed",
            "metadata_v2_1_versioning_status": (
                "ready_for_migration_design" if p0_passed else "blocked_blind_validation_failed"
            ),
            "retriever_v2_status": "blocked_by_candidate_recall" if p0_passed else "blocked",
            "ret2_015_016_status": "candidate_recall_unresolved",
            "architecture_c_status": "blocked",
            "limitations": [
                "This evaluation covers 16 cases x 40 chunks and does not run any retriever or alter ranking.",
                "RET2-015 and RET2-016 candidate recall limitations remain unresolved in this phase.",
                "full_runtime_eligible is reported separately so non-scope filters are not miscounted as scope-contract gains.",
                "If P0 fails, the current frozen blind label snapshot must remain immutable; any correction requires a new protocol version or new blind authoring attempt.",
            ],
            "generated_at": _now_iso(),
        }
    )
    return payload


def write_evaluation_outputs(payload: dict[str, Any]) -> None:
    write_many_atomic(
        [
            (
                TRACKED_EVALUATION_OUTPUT_PATH,
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            ),
            (
                TRACKED_EVALUATION_DOC_PATH,
                render_blind_evaluation_markdown(payload),
            ),
        ]
    )


def check_evaluation_outputs() -> tuple[bool, list[str]]:
    differences: list[str] = []
    if not TRACKED_EVALUATION_OUTPUT_PATH.exists():
        differences.append(f"Missing tracked blind evaluation JSON: {TRACKED_EVALUATION_OUTPUT_PATH}")
        return False, differences
    if not TRACKED_EVALUATION_DOC_PATH.exists():
        differences.append(f"Missing tracked blind evaluation doc: {TRACKED_EVALUATION_DOC_PATH}")
        return False, differences

    expected_payload = run_blind_metadata_evaluation()
    actual_payload = load_json_record(TRACKED_EVALUATION_OUTPUT_PATH)
    expected_compare = _without_nondeterministic_fields(expected_payload)
    actual_compare = _without_nondeterministic_fields(actual_payload)
    differences.extend(diff_json_objects(actual_compare, expected_compare, path="blind_evaluation"))

    expected_doc = render_blind_evaluation_markdown(expected_payload)
    actual_doc = TRACKED_EVALUATION_DOC_PATH.read_text(encoding="utf-8")
    if actual_doc != expected_doc:
        differences.append(f"Tracked blind evaluation doc drifted: {TRACKED_EVALUATION_DOC_PATH}")
    return (not differences, differences)


def render_blind_evaluation_markdown(payload: dict[str, Any]) -> str:
    overall = payload.get("overall_metrics", {})
    p1_vs_p0 = payload.get("p1_vs_p0_comparison", {})
    lines = [
        "# Retrieval Metadata Blind Evaluation v2.1",
        "",
        "## 1. P1 Contract Hypothesis Background",
        "",
        "- Blind labels were authored from KB-only packet content in an isolated workspace and frozen before any effectiveness evaluation.",
        "- This document records the first post-freeze independent validation pass and does not modify the frozen labels.",
        "",
        "## 2. Blind Packet, Authoring, and Freeze Process",
        "",
        f"- Packet SHA-256: `{payload['input_hashes']['packet_sha256']}`",
        f"- Guide SHA-256: `{payload['input_hashes']['guide_sha256']}`",
        f"- Template SHA-256: `{payload['input_hashes']['template_sha256']}`",
        f"- Labels SHA-256: `{payload['input_hashes']['labels_sha256']}`",
        f"- Authoring report SHA-256: `{payload['input_hashes']['authoring_report_sha256']}`",
        "",
        "## 3. Why This Is the First Valid Evaluation",
        "",
        f"- Freeze status: `{payload['provenance_gate'].get('freeze_status')}`",
        f"- Evaluation status before run: `{payload['provenance_gate'].get('evaluation_status_before_run')}`",
        f"- Provenance gate passed: `{payload['provenance_gate'].get('passed')}`",
        "",
        "## 4. Input Hashes and Provenance",
        "",
        f"- Mapping SHA-256: `{payload['input_hashes']['mapping_sha256']}`",
        f"- Provenance blind-to-cases-and-gold: `{payload['provenance_gate'].get('authoring_process_was_blind_to_cases_and_gold')}`",
        f"- Labels frozen before evaluation: `{payload['provenance_gate'].get('labels_frozen_before_evaluation')}`",
        f"- Labels modified after authoring: `{payload['provenance_gate'].get('labels_modified_after_authoring')}`",
        "",
        "## 5. Opaque ID Mapping Integrity",
        "",
        f"- Opaque document coverage: `{payload['mapping_integrity'].get('opaque_document_ids_mapped')}` / `{payload['mapping_integrity'].get('expected_document_count')}`",
        f"- Opaque chunk coverage: `{payload['mapping_integrity'].get('opaque_chunk_ids_mapped')}` / `{payload['mapping_integrity'].get('expected_chunk_count')}`",
        f"- Mapping passed: `{payload['mapping_integrity'].get('passed')}`",
        "",
        "## 6. Document Default + Chunk Override Results",
        "",
        f"- Document default mode counts: `{json.dumps(payload['effective_metadata_summary'].get('document_default_mode_counts', {}), ensure_ascii=False, sort_keys=True)}`",
        f"- Effective chunk mode counts: `{json.dumps(payload['effective_metadata_summary'].get('effective_mode_counts', {}), ensure_ascii=False, sort_keys=True)}`",
        f"- Chunk override count: `{payload['effective_metadata_summary'].get('chunk_override_count')}`",
        "",
        "## 7. 640 Pair Evaluation Scope",
        "",
        f"- Case count: `{payload['pairwise_evaluation_scope'].get('case_count')}`",
        f"- Chunk count: `{payload['pairwise_evaluation_scope'].get('chunk_count')}`",
        f"- Pair count: `{payload['pairwise_evaluation_scope'].get('pair_count')}`",
        "",
        "## 8. Relevant Retention",
        "",
        f"- relevant_pair_count: `{overall.get('relevant_pair_count')}`",
        f"- relevant_allowed_count: `{overall.get('relevant_allowed_count')}`",
        f"- relevant_denied_count: `{overall.get('relevant_denied_count')}`",
        f"- relevant_candidate_retention_rate: `{overall.get('relevant_candidate_retention_rate')}`",
        "",
        "## 9. Boundary Removal",
        "",
        f"- boundary_violating_pair_count: `{overall.get('boundary_violating_pair_count')}`",
        f"- boundary_denied_count: `{overall.get('boundary_denied_count')}`",
        f"- boundary_allowed_count: `{overall.get('boundary_allowed_count')}`",
        f"- boundary_candidate_removal_rate: `{overall.get('boundary_candidate_removal_rate')}`",
        "",
        "## 10. False Exclusion",
        "",
        f"- false_exclusion_count: `{overall.get('false_exclusion_count')}`",
        "",
        "## 11. False Inclusion",
        "",
        f"- false_inclusion_count: `{overall.get('false_inclusion_count')}`",
        "",
        "## 12. Benchmark Contract Conflict",
        "",
        f"- benchmark_contract_conflict_count: `{overall.get('benchmark_contract_conflict_count')}`",
        "",
        "## 13. Per-Mode Results",
        "",
    ]
    for mode, metrics in payload.get("per_mode_metrics", {}).items():
        lines.extend(
            [
                f"### {mode}",
                "",
                f"- relevant retention: `{metrics['relevant_candidate_retention_rate']}`",
                f"- boundary removal: `{metrics['boundary_candidate_removal_rate']}`",
                f"- pair_count: `{metrics['pair_count']}`",
                "",
            ]
        )
    lines.extend(["## 14. Per-Scope-Type Results", ""])
    for scope_type, metrics in payload.get("per_scope_type_metrics", {}).items():
        lines.extend(
            [
                f"### {scope_type}",
                "",
                f"- relevant retention: `{metrics['relevant_candidate_retention_rate']}`",
                f"- boundary removal: `{metrics['boundary_candidate_removal_rate']}`",
                f"- pair_count: `{metrics['pair_count']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## 15. P1 Counterfactual vs Blind Result",
            "",
            f"- P1 hypothesis retention: `{p1_vs_p0.get('p1_hypothesis_retention')}`",
            f"- P0 blind retention: `{p1_vs_p0.get('p0_blind_retention')}`",
            f"- P1 hypothesis removal: `{p1_vs_p0.get('p1_hypothesis_removal')}`",
            f"- P0 blind removal: `{p1_vs_p0.get('p0_blind_removal')}`",
            f"- hypothesis_replicated: `{p1_vs_p0.get('hypothesis_replicated')}`",
            "",
            "## 16. Did P0 Pass?",
            "",
            f"- p0_validation_status: `{payload.get('p0_validation_status')}`",
            f"- evidence_classification: `{payload.get('evidence_classification')}`",
            "",
            "## 17. Can Metadata v2.1 Enter Migration Design?",
            "",
            f"- metadata_v2_1_versioning_status: `{payload.get('metadata_v2_1_versioning_status')}`",
            "",
            "## 18. Why Retriever v2 Is Still Blocked by Recall",
            "",
            "- This evaluation does not run any retriever and does not address RET2-015 / RET2-016 candidate recall gaps.",
            f"- retriever_v2_status: `{payload.get('retriever_v2_status')}`",
            "",
            "## 19. RET2-015 / RET2-016 Status",
            "",
            f"- ret2_015_016_status: `{payload.get('ret2_015_016_status')}`",
            "",
            "## 20. Architecture C Status",
            "",
            f"- architecture_c_status: `{payload.get('architecture_c_status')}`",
            "",
            "## 21. Failure Policy",
            "",
            "- If P0 fails, the current frozen blind label snapshot must remain immutable. Any correction requires a new protocol version or a new blind authoring attempt.",
            "",
            "## 22. Limitations",
            "",
        ]
    )
    for limitation in payload.get("limitations", []):
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


def _load_inputs() -> dict[str, Any]:
    labels = load_jsonl_records(TRACKED_LABELS_PATH)
    report = load_json_record(TRACKED_REPORT_PATH)
    freeze_manifest = load_json_record(TRACKED_FREEZE_MANIFEST_PATH)
    mapping = load_json_record(TRACKED_MAPPING_PATH)
    authoring_manifest = load_json_record(TRACKED_AUTHORING_MANIFEST_PATH)
    documents = [KnowledgeDocumentV2.model_validate(row) for row in load_jsonl_records(TRACKED_DOCUMENTS_PATH)]
    chunks = [KnowledgeChunkV2.model_validate(row) for row in load_jsonl_records(TRACKED_CHUNKS_PATH)]
    cases = [RetrievalEvaluationCaseV2.model_validate(row) for row in load_jsonl_records(TRACKED_CASES_PATH)]
    benchmark_config = load_json_record(TRACKED_BENCHMARK_CONFIG_PATH)
    p1_proposal = load_json_record(TRACKED_RUNTIME_CONTRACT_PROPOSAL_PATH)
    documents_by_id = {document.document_id: document for document in documents}
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    return {
        "labels": labels,
        "report": report,
        "freeze_manifest": freeze_manifest,
        "mapping": mapping,
        "authoring_manifest": authoring_manifest,
        "documents": documents,
        "chunks": chunks,
        "cases": cases,
        "benchmark_config": benchmark_config,
        "p1_proposal": p1_proposal,
        "documents_by_id": documents_by_id,
        "chunks_by_id": chunks_by_id,
        "input_hashes": {
            "labels_sha256": _sha256_file(TRACKED_LABELS_PATH),
            "authoring_report_sha256": _sha256_file(TRACKED_REPORT_PATH),
            "freeze_manifest_sha256": _sha256_file(TRACKED_FREEZE_MANIFEST_PATH),
            "mapping_sha256": _sha256_file(TRACKED_MAPPING_PATH),
            "authoring_manifest_sha256": _sha256_file(TRACKED_AUTHORING_MANIFEST_PATH),
            "packet_sha256": authoring_manifest["packet_sha256"],
            "guide_sha256": authoring_manifest["guide_sha256"],
            "template_sha256": authoring_manifest["template_sha256"],
        },
    }


def _build_provenance_gate(*, inputs: dict[str, Any]) -> dict[str, Any]:
    freeze_manifest = inputs["freeze_manifest"]
    authoring_manifest = inputs["authoring_manifest"]
    report = inputs["report"]
    labels = inputs["labels"]
    mapping = inputs["mapping"]
    reasons: list[str] = []
    checks = {
        "freeze_status_matches": freeze_manifest.get("freeze_status") == "frozen_before_evaluation",
        "evaluation_status_before_run_matches": freeze_manifest.get("evaluation_status") == "not_started",
        "labels_frozen_before_evaluation": freeze_manifest.get("labels_frozen_before_evaluation") is True,
        "labels_modified_after_authoring": freeze_manifest.get("labels_modified_after_authoring") is False,
        "valid_blind_authoring_attempt_number_matches": freeze_manifest.get("valid_blind_authoring_attempt_number") == 1,
        "labels_hash_matches": inputs["input_hashes"]["labels_sha256"] == EXPECTED_LABELS_SHA256 == freeze_manifest.get("completed_labels_sha256"),
        "authoring_report_hash_matches": inputs["input_hashes"]["authoring_report_sha256"] == EXPECTED_REPORT_SHA256 == freeze_manifest.get("authoring_report_sha256"),
        "mapping_hash_matches_authoring_manifest": inputs["input_hashes"]["mapping_sha256"] == authoring_manifest.get("mapping_sha256"),
        "packet_hash_matches": authoring_manifest.get("packet_sha256") == EXPECTED_PACKET_SHA256 == freeze_manifest.get("packet_sha256"),
        "guide_hash_matches": authoring_manifest.get("guide_sha256") == EXPECTED_GUIDE_SHA256 == freeze_manifest.get("guide_sha256"),
        "template_hash_matches": authoring_manifest.get("template_sha256") == EXPECTED_TEMPLATE_SHA256 == freeze_manifest.get("template_sha256"),
        "document_count_matches": authoring_manifest.get("document_count") == 20 == freeze_manifest.get("document_count") == report.get("document_count") == len(labels),
        "chunk_count_matches": authoring_manifest.get("chunk_count") == 40 == freeze_manifest.get("chunk_count") == report.get("chunk_count") == len(inputs["chunks"]),
        "document_default_mode_counts_match": report.get("document_default_mode_counts") == freeze_manifest.get("document_default_mode_counts"),
        "chunk_override_counts_match": report.get("chunk_override_count") == freeze_manifest.get("chunk_override_count"),
        "authoring_report_blind_flags_clean": (
            report.get("external_files_accessed") is False
            and report.get("network_accessed") is False
            and report.get("cases_or_gold_accessed") is False
            and report.get("evaluation_performed") is False
        ),
        "freeze_manifest_blind_flags_clean": (
            freeze_manifest.get("external_files_accessed") is False
            and freeze_manifest.get("network_accessed") is False
            and freeze_manifest.get("cases_or_gold_accessed") is False
            and freeze_manifest.get("evaluation_performed") is False
        ),
        "mapping_complete_size": (
            len(mapping["opaque_document_id_to_document_id"]) == 20
            and len(mapping["document_id_to_opaque_document_id"]) == 20
            and len(mapping["opaque_chunk_id_to_chunk_id"]) == 40
            and len(mapping["chunk_id_to_opaque_chunk_id"]) == 40
        ),
    }
    for key, value in checks.items():
        if not value:
            reasons.append(key)
    return {
        "passed": not reasons,
        "reasons": reasons,
        "freeze_status": freeze_manifest.get("freeze_status"),
        "evaluation_status_before_run": freeze_manifest.get("evaluation_status"),
        "labels_frozen_before_evaluation": freeze_manifest.get("labels_frozen_before_evaluation"),
        "labels_modified_after_authoring": freeze_manifest.get("labels_modified_after_authoring"),
        "valid_blind_authoring_attempt_number": freeze_manifest.get("valid_blind_authoring_attempt_number"),
        "authoring_process_was_blind_to_cases_and_gold": (
            report.get("cases_or_gold_accessed") is False
            and freeze_manifest.get("cases_or_gold_accessed") is False
        ),
        "checks": checks,
    }


def _build_mapping_integrity(*, inputs: dict[str, Any]) -> dict[str, Any]:
    mapping = inputs["mapping"]
    labels = inputs["labels"]
    documents = inputs["documents"]
    chunks = inputs["chunks"]
    label_document_order = [record["opaque_document_id"] for record in labels]
    opaque_chunk_ids = [override["opaque_chunk_id"] for record in labels for override in record["chunk_overrides"]]
    document_ids = {document.document_id for document in documents}
    chunk_ids = {chunk.chunk_id for chunk in chunks}
    mapped_document_ids = set(mapping["opaque_document_id_to_document_id"].values())
    mapped_chunk_ids = set(mapping["opaque_chunk_id_to_chunk_id"].values())
    issues: list[str] = []
    if len(set(label_document_order)) != 20:
        issues.append("duplicate_opaque_document_id")
    if len(set(opaque_chunk_ids)) != 40:
        issues.append("duplicate_opaque_chunk_id")
    if mapped_document_ids != document_ids:
        issues.append("document_mapping_mismatch")
    if mapped_chunk_ids != chunk_ids:
        issues.append("chunk_mapping_mismatch")
    return {
        "passed": not issues,
        "issues": issues,
        "expected_document_count": 20,
        "expected_chunk_count": 40,
        "opaque_document_ids_mapped": len(set(label_document_order)),
        "opaque_chunk_ids_mapped": len(set(opaque_chunk_ids)),
        "duplicate_document_ids_detected": len(set(label_document_order)) != len(label_document_order),
        "duplicate_chunk_ids_detected": len(set(opaque_chunk_ids)) != len(opaque_chunk_ids),
        "template_order_revalidated_in_this_phase": False,
        "template_order_validation_source": "freeze_stage_prevalidation",
    }


def _build_effective_chunk_metadata(*, inputs: dict[str, Any]) -> dict[str, Any]:
    mapping = inputs["mapping"]
    labels = inputs["labels"]
    chunks = inputs["chunks"]
    chunks_by_id = inputs["chunks_by_id"]
    documents_by_id = inputs["documents_by_id"]
    opaque_document_to_real = mapping["opaque_document_id_to_document_id"]
    opaque_chunk_to_real = mapping["opaque_chunk_id_to_chunk_id"]

    document_default_mode_counts: dict[str, int] = {mode: 0 for mode in sorted(ALLOWED_MODES)}
    effective_mode_counts: dict[str, int] = {mode: 0 for mode in sorted(ALLOWED_MODES)}
    assignment_source_counts = {"document_default": 0, "chunk_override": 0}
    per_chunk: dict[str, dict[str, Any]] = {}
    override_count = 0

    for record in labels:
        opaque_document_id = record["opaque_document_id"]
        source_document_id = opaque_document_to_real[opaque_document_id]
        document_mode = record["document_default_mode"]
        document_default_mode_counts[document_mode] += 1
        override_by_chunk = {
            item["opaque_chunk_id"]: item["runtime_scope_match_mode"]
            for item in record["chunk_overrides"]
            if item["runtime_scope_match_mode"] is not None
        }
        override_count += len(override_by_chunk)
        for override in record["chunk_overrides"]:
            source_chunk_id = opaque_chunk_to_real[override["opaque_chunk_id"]]
            chunk = chunks_by_id[source_chunk_id]
            effective_mode = override_by_chunk.get(override["opaque_chunk_id"], document_mode)
            assignment_source = "chunk_override" if override["opaque_chunk_id"] in override_by_chunk else "document_default"
            effective_mode_counts[effective_mode] += 1
            assignment_source_counts[assignment_source] += 1
            per_chunk[source_chunk_id] = {
                "source_document_id": source_document_id,
                "source_chunk_id": source_chunk_id,
                "effective_runtime_scope_match_mode": effective_mode,
                "assignment_source": assignment_source,
                "document_default_mode": document_mode,
                "scope_type": chunk.scope_type.value,
                "primary_solution_id": chunk.primary_solution_id,
                "applicable_solution_ids": list(chunk.applicable_solution_ids),
                "excluded_solution_ids": list(chunk.excluded_solution_ids),
                "document_type": chunk.document_type.value,
            }

    missing_chunks = sorted(chunk.chunk_id for chunk in chunks if chunk.chunk_id not in per_chunk)
    if missing_chunks:
        raise ValueError(f"Blind label evaluation missing chunk mappings for: {missing_chunks}")

    document_summaries = []
    for document_id, document in sorted(documents_by_id.items()):
        chunk_ids = [chunk.chunk_id for chunk in chunks if chunk.document_id == document_id]
        document_summaries.append(
            {
                "source_document_id": document_id,
                "scope_type": document.scope_type.value,
                "primary_solution_id": document.primary_solution_id,
                "applicable_solution_ids": list(document.applicable_solution_ids),
                "excluded_solution_ids": list(document.excluded_solution_ids),
                "chunk_count": len(chunk_ids),
            }
        )

    return {
        "document_count": len(documents_by_id),
        "chunk_count": len(chunks),
        "document_default_mode_counts": document_default_mode_counts,
        "effective_mode_counts": effective_mode_counts,
        "chunk_override_count": override_count,
        "assignment_source_counts": assignment_source_counts,
        "mode_static_across_cases": True,
        "case_specific_logic_detected": False,
        "gold_participated_in_assignment": False,
        "documents": document_summaries,
        "chunks": [per_chunk[chunk.chunk_id] for chunk in chunks],
    }


def _build_pairwise_records(*, inputs: dict[str, Any], effective_metadata: dict[str, Any]) -> list[dict[str, Any]]:
    documents_by_id = inputs["documents_by_id"]
    chunks = inputs["chunks"]
    cases = inputs["cases"]
    benchmark_date = datetime.fromisoformat(inputs["benchmark_config"]["evaluation_date"]).date()
    effective_by_chunk = {item["source_chunk_id"]: item for item in effective_metadata["chunks"]}

    records: list[dict[str, Any]] = []
    for case in cases:
        expected_document_ids = set(case.evaluation_gold.expected_relevant_document_ids)
        expected_chunk_ids = set(case.evaluation_gold.expected_relevant_chunk_ids)
        for chunk in chunks:
            document = documents_by_id[chunk.document_id]
            metadata = effective_by_chunk[chunk.chunk_id]
            relevant_item_id = _relevant_item_identity(
                document_id=document.document_id,
                chunk_id=chunk.chunk_id,
                expected_document_ids=expected_document_ids,
                expected_chunk_ids=expected_chunk_ids,
            )
            relevant = relevant_item_id is not None
            boundary_decision = evaluate_candidate_boundary_v2(case=case, document=document, chunk=chunk)
            boundary_allowed = boundary_decision.candidate_allowed
            scope_allowed = _scope_contract_allowed(case=case, chunk=chunk, effective_mode=metadata["effective_runtime_scope_match_mode"])
            full_runtime_eligible = scope_allowed and _document_passes_runtime_filters(
                case=case,
                document=document,
                evaluation_date=benchmark_date,
            )
            conflict = relevant and not boundary_allowed
            records.append(
                {
                    "case_id": case.retrieval_case_id,
                    "source_case_id": case.source_case_id,
                    "source_document_id": document.document_id,
                    "source_chunk_id": chunk.chunk_id,
                    "scope_type": chunk.scope_type.value,
                    "effective_mode": metadata["effective_runtime_scope_match_mode"],
                    "assignment_source": metadata["assignment_source"],
                    "relevant_by_frozen_gold": relevant,
                    "relevant_item_id": relevant_item_id,
                    "boundary_allowed_by_frozen_gold": boundary_allowed,
                    "boundary_violating_by_frozen_gold": not boundary_allowed,
                    "boundary_reasons": list(boundary_decision.reasons),
                    "scope_contract_allowed": scope_allowed,
                    "full_runtime_eligible": full_runtime_eligible,
                    "false_exclusion": relevant and not scope_allowed,
                    "false_inclusion": (not boundary_allowed) and scope_allowed,
                    "benchmark_contract_conflict": conflict,
                }
            )
    return records


def _build_metrics_summary(pairwise_records: list[dict[str, Any]]) -> dict[str, Any]:
    relevant_pair_count = sum(1 for record in pairwise_records if record["relevant_by_frozen_gold"])
    relevant_allowed_count = sum(
        1 for record in pairwise_records if record["relevant_by_frozen_gold"] and record["scope_contract_allowed"]
    )
    boundary_violating_pair_count = sum(1 for record in pairwise_records if record["boundary_violating_by_frozen_gold"])
    boundary_denied_count = sum(
        1 for record in pairwise_records if record["boundary_violating_by_frozen_gold"] and not record["scope_contract_allowed"]
    )
    false_exclusion_count = sum(1 for record in pairwise_records if record["false_exclusion"])
    false_inclusion_count = sum(1 for record in pairwise_records if record["false_inclusion"])
    benchmark_contract_conflict_count = sum(1 for record in pairwise_records if record["benchmark_contract_conflict"])
    return {
        "pair_count": len(pairwise_records),
        "relevant_pair_count": relevant_pair_count,
        "relevant_allowed_count": relevant_allowed_count,
        "relevant_denied_count": relevant_pair_count - relevant_allowed_count,
        "relevant_candidate_retention_rate": _rate(relevant_allowed_count, relevant_pair_count),
        "boundary_violating_pair_count": boundary_violating_pair_count,
        "boundary_denied_count": boundary_denied_count,
        "boundary_allowed_count": boundary_violating_pair_count - boundary_denied_count,
        "boundary_candidate_removal_rate": _rate(boundary_denied_count, boundary_violating_pair_count),
        "false_exclusion_count": false_exclusion_count,
        "false_inclusion_count": false_inclusion_count,
        "benchmark_contract_conflict_count": benchmark_contract_conflict_count,
    }


def _group_metrics(pairwise_records: list[dict[str, Any]], *, key_name: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in pairwise_records:
        grouped.setdefault(str(record[key_name]), []).append(record)
    return {key: _build_metrics_summary(records) for key, records in sorted(grouped.items())}


def _filter_pair_list(pairwise_records: list[dict[str, Any]], *, key: str) -> list[dict[str, Any]]:
    return [
        {
            "case_id": record["case_id"],
            "source_document_id": record["source_document_id"],
            "source_chunk_id": record["source_chunk_id"],
            "effective_mode": record["effective_mode"],
            "assignment_source": record["assignment_source"],
            "scope_type": record["scope_type"],
        }
        for record in pairwise_records
        if record[key]
    ]


def _build_p1_vs_p0_comparison(
    p0_retention: float | None,
    p0_removal: float | None,
) -> dict[str, Any]:
    proposal = load_json_record(TRACKED_RUNTIME_CONTRACT_PROPOSAL_PATH)
    c2 = next(item for item in proposal["counterfactual_results"] if item["contract_id"] == "C2")
    return {
        "p1_hypothesis_retention": c2["relevant_candidate_retention_rate"],
        "p0_blind_retention": p0_retention,
        "p1_hypothesis_removal": c2["boundary_candidate_removal_rate"],
        "p0_blind_removal": p0_removal,
        "hypothesis_replicated": (
            p0_retention is not None
            and p0_removal is not None
            and p0_retention == c2["relevant_candidate_retention_rate"]
            and p0_removal == c2["boundary_candidate_removal_rate"]
        ),
    }


def _scope_contract_allowed(
    *,
    case: RetrievalEvaluationCaseV2,
    chunk: KnowledgeChunkV2,
    effective_mode: str,
) -> bool:
    operational_scope = set(case.runtime_context.operational_solution_scope)
    excluded = set(chunk.excluded_solution_ids)
    if operational_scope and excluded & operational_scope:
        return False
    if effective_mode == "primary_in_scope":
        return bool(chunk.primary_solution_id) and chunk.primary_solution_id in operational_scope
    if effective_mode == "full_applicable_scope":
        applicable = set(chunk.applicable_solution_ids)
        return bool(applicable) and applicable.issubset(operational_scope)
    if effective_mode == "global_reusable":
        return True
    raise ValueError(f"Unsupported effective_mode: {effective_mode}")


def _relevant_item_identity(
    *,
    document_id: str,
    chunk_id: str,
    expected_document_ids: set[str],
    expected_chunk_ids: set[str],
) -> str | None:
    if chunk_id in expected_chunk_ids:
        return chunk_id
    if document_id in expected_document_ids:
        return document_id
    return None


def _without_nondeterministic_fields(payload: dict[str, Any]) -> dict[str, Any]:
    clone = json.loads(json.dumps(payload, ensure_ascii=False))
    for field_name in NON_DETERMINISTIC_FIELDS:
        clone.pop(field_name, None)
    return clone


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
