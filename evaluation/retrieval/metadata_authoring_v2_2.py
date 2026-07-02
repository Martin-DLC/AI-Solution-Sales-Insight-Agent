from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from dataio.jsonl_loader import load_jsonl_models
from evaluation.retrieval.storage import (
    diff_json_objects,
    load_json_record,
    load_jsonl_records,
    write_many_atomic,
)
from knowledge_base.contracts_v2 import KnowledgeChunkV2, KnowledgeDocumentV2
from knowledge_base.dataset import DemoSolutionScope, load_demo_solution_scope

KB_DOCUMENTS_PATH = Path("data/knowledge_base/documents.v2.jsonl")
KB_CHUNKS_PATH = Path("data/knowledge_base/chunks.v2.jsonl")
DEMO_SCOPE_PATH = Path("data/knowledge_base/demo_solution_scope.v1.json")

TRACKED_PACKET_PATH = Path("data/evaluation/retrieval/retrieval_metadata_authoring_packet.v2_2.jsonl")
TRACKED_MAPPING_PATH = Path("data/evaluation/retrieval/retrieval_metadata_authoring_mapping.v2_2.json")
TRACKED_MANIFEST_PATH = Path("data/evaluation/retrieval/retrieval_metadata_authoring_manifest.v2_2.json")
TRACKED_DOC_PATH = Path("docs/38_Retrieval_Metadata_Blind_Protocol_V2_2.md")

RUNTIME_BUNDLE_DIR = Path("data/runtime/retrieval_metadata_blind_attempt_2")
RUNTIME_GUIDE_PATH = RUNTIME_BUNDLE_DIR / "AUTHORING_GUIDE.md"
RUNTIME_PACKET_PATH = RUNTIME_BUNDLE_DIR / "authoring_packet.jsonl"
RUNTIME_TEMPLATE_PATH = RUNTIME_BUNDLE_DIR / "label_template.jsonl"
RUNTIME_MANIFEST_PATH = RUNTIME_BUNDLE_DIR / "bundle_manifest.json"

PROTOCOL_VERSION = "retrieval_metadata_blind_authoring_v2_2"
BLIND_ATTEMPT_NUMBER = 2
OPAQUE_SALT = "retrieval-metadata-blind-v2.2-attempt-2"
ATTEMPT_1_PROTOCOL_VERSION = "retrieval_metadata_blind_authoring_v2_1"

PACKET_SOURCE_TYPES = [
    "knowledge_documents_v2",
    "knowledge_chunks_v2",
    "demo_solution_scope_v1",
    "knowledge_document_chunk_schema",
]

FORBIDDEN_SOURCE_TYPES = [
    "retrieval_cases",
    "evaluation_gold",
    "formal_results",
    "blind_attempt_1_labels",
    "blind_attempt_1_evaluation",
    "failure_pairs",
]

LEAK_MARKERS = (
    "RET2-",
    "evaluation_gold",
    "expected_document",
    "expected_chunk",
    "forbidden_document",
    "forbidden_solution",
    "false_exclusion",
    "false_inclusion",
    "perfect_existing_mode",
    "KB-SEC-001",
    "KB-PLAY-001",
    "Blind Attempt 1",
    "Formal Results Hash",
    "document_id_to_opaque_document_id",
    "opaque_document_id_to_document_id",
    "chunk_id_to_opaque_chunk_id",
    "opaque_chunk_id_to_chunk_id",
)


def build_plan_payload() -> dict[str, Any]:
    documents, chunks, solution_scope = load_authoring_sources()
    return {
        "mode": "plan",
        "protocol_version": 2.2,
        "blind_attempt_number": BLIND_ATTEMPT_NUMBER,
        "schema_changed": False,
        "mode_enum_changed": False,
        "runtime_schema_changed": False,
        "change_scope": "guide_and_protocol_only",
        "input_paths": {
            "documents": str(KB_DOCUMENTS_PATH),
            "chunks": str(KB_CHUNKS_PATH),
            "solution_scope": str(DEMO_SCOPE_PATH),
        },
        "tracked_outputs": {
            "packet": str(TRACKED_PACKET_PATH),
            "mapping": str(TRACKED_MAPPING_PATH),
            "manifest": str(TRACKED_MANIFEST_PATH),
            "protocol_doc": str(TRACKED_DOC_PATH),
        },
        "runtime_bundle_outputs": {
            "guide": str(RUNTIME_GUIDE_PATH),
            "packet": str(RUNTIME_PACKET_PATH),
            "template": str(RUNTIME_TEMPLATE_PATH),
            "manifest": str(RUNTIME_MANIFEST_PATH),
        },
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "selected_solution_count": len(solution_scope.selected_solution_ids),
        "packet_contains_cases": False,
        "packet_contains_queries": False,
        "packet_contains_gold": False,
        "packet_contains_results": False,
        "packet_contains_attempt_1_labels": False,
        "packet_contains_failure_analysis": False,
        "labels_prefilled": False,
        "original_ids_exposed": False,
        "writes_output_files": False,
        "blind_authoring_only": True,
        "retriever_v2_status": "blocked_by_candidate_recall",
        "architecture_c_status": "blocked",
    }


def load_authoring_sources() -> tuple[list[KnowledgeDocumentV2], list[KnowledgeChunkV2], DemoSolutionScope]:
    documents = load_jsonl_models(KB_DOCUMENTS_PATH, KnowledgeDocumentV2)
    chunks = load_jsonl_models(KB_CHUNKS_PATH, KnowledgeChunkV2)
    solution_scope = load_demo_solution_scope(DEMO_SCOPE_PATH)
    return documents, chunks, solution_scope


def build_authoring_packet(
    documents: list[KnowledgeDocumentV2],
    chunks: list[KnowledgeChunkV2],
    solution_catalog: DemoSolutionScope,
    protocol_version: str,
) -> dict[str, Any]:
    document_map = _build_opaque_mapping(
        prefix="DOC-AUTH2",
        source_ids=[document.document_id for document in documents],
        protocol_version=protocol_version,
    )
    chunk_map = _build_opaque_mapping(
        prefix="CHUNK-AUTH2",
        source_ids=[chunk.chunk_id for chunk in chunks],
        protocol_version=protocol_version,
    )
    attempt_1_document_map = _build_opaque_mapping(
        prefix="DOC-AUTH",
        source_ids=[document.document_id for document in documents],
        protocol_version=ATTEMPT_1_PROTOCOL_VERSION,
    )
    attempt_1_chunk_map = _build_opaque_mapping(
        prefix="CHUNK-AUTH",
        source_ids=[chunk.chunk_id for chunk in chunks],
        protocol_version=ATTEMPT_1_PROTOCOL_VERSION,
    )

    chunks_by_document: dict[str, list[KnowledgeChunkV2]] = defaultdict(list)
    for chunk in chunks:
        chunks_by_document[chunk.document_id].append(chunk)
    for chunk_list in chunks_by_document.values():
        chunk_list.sort(key=lambda item: item.chunk_index)

    packet_records = [
        _build_packet_record(
            document=document,
            chunks=chunks_by_document.get(document.document_id, []),
            document_opaque_id=document_map["forward"][document.document_id],
            chunk_map=chunk_map["forward"],
        )
        for document in documents
    ]
    label_template_records = [
        _build_label_template_record(
            document=document,
            chunks=chunks_by_document.get(document.document_id, []),
            document_opaque_id=document_map["forward"][document.document_id],
            chunk_map=chunk_map["forward"],
        )
        for document in documents
    ]
    mapping_payload = {
        "protocol_version": 2.2,
        "blind_attempt_number": BLIND_ATTEMPT_NUMBER,
        "opaque_salt_label": OPAQUE_SALT,
        "document_id_to_opaque_document_id": document_map["forward"],
        "opaque_document_id_to_document_id": document_map["reverse"],
        "chunk_id_to_opaque_chunk_id": chunk_map["forward"],
        "opaque_chunk_id_to_chunk_id": chunk_map["reverse"],
    }

    packet_text = _jsonl_text(packet_records)
    template_text = _jsonl_text(label_template_records)
    mapping_text = _json_text(mapping_payload)
    guide_text = render_blind_authoring_guide(protocol_version=protocol_version)
    protocol_doc_text = render_protocol_markdown(protocol_version=protocol_version)

    bundle_manifest_payload = _build_manifest_payload(
        documents=documents,
        chunks=chunks,
        solution_catalog=solution_catalog,
        packet_text=packet_text,
        guide_text=guide_text,
        template_text=template_text,
        mapping_text=mapping_text,
        opaque_ids_differ_from_attempt_1=(
            set(document_map["forward"].values()).isdisjoint(set(attempt_1_document_map["forward"].values()))
            and set(chunk_map["forward"].values()).isdisjoint(set(attempt_1_chunk_map["forward"].values()))
        ),
    )
    bundle_manifest_text = _json_text(bundle_manifest_payload)

    leak_scan_files = {
        "AUTHORING_GUIDE.md": guide_text,
        "authoring_packet.jsonl": packet_text,
        "label_template.jsonl": template_text,
        "bundle_manifest.json": bundle_manifest_text,
    }
    run_leak_scanner(
        files=leak_scan_files,
        document_ids=[document.document_id for document in documents],
        chunk_ids=[chunk.chunk_id for chunk in chunks],
        attempt_1_opaque_ids=list(attempt_1_document_map["forward"].values()) + list(attempt_1_chunk_map["forward"].values()),
    )

    return {
        "protocol_version": protocol_version,
        "packet_records": packet_records,
        "label_template_records": label_template_records,
        "mapping_payload": mapping_payload,
        "bundle_manifest_payload": bundle_manifest_payload,
        "tracked_artifacts": {
            TRACKED_PACKET_PATH: packet_text,
            TRACKED_MAPPING_PATH: mapping_text,
            TRACKED_MANIFEST_PATH: bundle_manifest_text,
            TRACKED_DOC_PATH: protocol_doc_text,
        },
        "runtime_bundle_artifacts": {
            RUNTIME_GUIDE_PATH: guide_text,
            RUNTIME_PACKET_PATH: packet_text,
            RUNTIME_TEMPLATE_PATH: template_text,
            RUNTIME_MANIFEST_PATH: bundle_manifest_text,
        },
    }


def write_authoring_outputs(payload: dict[str, Any]) -> None:
    items: list[tuple[str | Path, str]] = []
    for path, content in payload["tracked_artifacts"].items():
        items.append((path, content))
    for path, content in payload["runtime_bundle_artifacts"].items():
        items.append((path, content))
    write_many_atomic(items)


def check_authoring_outputs() -> tuple[bool, list[str]]:
    documents, chunks, solution_scope = load_authoring_sources()
    recomputed = build_authoring_packet(documents, chunks, solution_scope, PROTOCOL_VERSION)
    differences: list[str] = []

    tracked_packet = _load_jsonl_if_exists(TRACKED_PACKET_PATH)
    if tracked_packet is None:
        differences.append(f"Missing tracked packet: {TRACKED_PACKET_PATH}")
    else:
        differences.extend(diff_json_objects(tracked_packet, recomputed["packet_records"], path="tracked_packet"))

    tracked_mapping = _load_json_if_exists(TRACKED_MAPPING_PATH)
    if tracked_mapping is None:
        differences.append(f"Missing tracked mapping: {TRACKED_MAPPING_PATH}")
    else:
        differences.extend(diff_json_objects(tracked_mapping, recomputed["mapping_payload"], path="tracked_mapping"))

    tracked_manifest = _load_json_if_exists(TRACKED_MANIFEST_PATH)
    if tracked_manifest is None:
        differences.append(f"Missing tracked manifest: {TRACKED_MANIFEST_PATH}")
    else:
        differences.extend(diff_json_objects(tracked_manifest, recomputed["bundle_manifest_payload"], path="tracked_manifest"))

    tracked_doc = _load_text_if_exists(TRACKED_DOC_PATH)
    if tracked_doc is None:
        differences.append(f"Missing tracked protocol doc: {TRACKED_DOC_PATH}")
    elif tracked_doc != recomputed["tracked_artifacts"][TRACKED_DOC_PATH]:
        differences.append(f"Tracked protocol doc drifted: {TRACKED_DOC_PATH}")

    runtime_guide = _load_text_if_exists(RUNTIME_GUIDE_PATH)
    if runtime_guide is None:
        differences.append(f"Missing runtime guide: {RUNTIME_GUIDE_PATH}")
    elif runtime_guide != recomputed["runtime_bundle_artifacts"][RUNTIME_GUIDE_PATH]:
        differences.append(f"Runtime guide drifted: {RUNTIME_GUIDE_PATH}")

    runtime_packet = _load_text_if_exists(RUNTIME_PACKET_PATH)
    if runtime_packet is None:
        differences.append(f"Missing runtime authoring packet: {RUNTIME_PACKET_PATH}")
    elif runtime_packet != recomputed["runtime_bundle_artifacts"][RUNTIME_PACKET_PATH]:
        differences.append(f"Runtime authoring packet drifted: {RUNTIME_PACKET_PATH}")

    runtime_template = _load_text_if_exists(RUNTIME_TEMPLATE_PATH)
    if runtime_template is None:
        differences.append(f"Missing runtime label template: {RUNTIME_TEMPLATE_PATH}")
    elif runtime_template != recomputed["runtime_bundle_artifacts"][RUNTIME_TEMPLATE_PATH]:
        differences.append(f"Runtime label template drifted: {RUNTIME_TEMPLATE_PATH}")

    runtime_manifest = _load_json_if_exists(RUNTIME_MANIFEST_PATH)
    if runtime_manifest is None:
        differences.append(f"Missing runtime bundle manifest: {RUNTIME_MANIFEST_PATH}")
    else:
        differences.extend(diff_json_objects(runtime_manifest, recomputed["bundle_manifest_payload"], path="runtime_manifest"))

    return (not differences, differences)


def render_protocol_markdown(*, protocol_version: str) -> str:
    lines = [
        "# Retrieval Metadata Blind Authoring Protocol v2.2",
        "",
        "## 1. Why v2.2 Exists",
        "",
        "- Blind Attempt 1 failed and remains permanently frozen.",
        "- Metadata Contract v2.2 analysis concluded that we do not need a new enum or a new runtime field.",
        "- The minimum change is guide-and-protocol clarification only.",
        "- This phase builds the blind packet for Attempt 2, but does not perform any labeling or evaluation.",
        "",
        "## 2. What Changes Relative to v2.1",
        "",
        "- Keep the same three modes: `primary_in_scope`, `full_applicable_scope`, `global_reusable`.",
        "- Do not add `any_applicable_scope`.",
        "- Do not add runtime fields.",
        "- Tighten the guide so annotators judge only solution-scope dependency, not topic or document class.",
        "",
        "## 3. Blind Boundary",
        "",
        "- Packet generation reads only KB documents, KB chunks, demo solution scope, and schema structure.",
        "- Packet generation must not read retrieval cases, queries, gold, formal results, Attempt 1 labels, Attempt 1 evaluation, or failure pairs.",
        "- The blind bundle must not expose mapping, original IDs, Attempt 1 opaque IDs, or any failure evidence.",
        "",
        "## 4. Opaque ID Design",
        "",
        f"- Salt label: `{OPAQUE_SALT}`",
        "- Document opaque IDs use prefix `DOC-AUTH2-...`.",
        "- Chunk opaque IDs use prefix `CHUNK-AUTH2-...`.",
        "- Opaque IDs are deterministic but carry no business meaning.",
        "- Mapping stays in tracked artifacts only and never enters the blind bundle.",
        "",
        "## 5. Solution Scope Dependency Only",
        "",
        "Annotators must answer exactly one question:",
        "",
        "> This evidence, at the solution-scope layer, depends on the primary solution only, all applicable solutions together, or no specific solution at all?",
        "",
        "This question must be answered without using:",
        "",
        "- document_type",
        "- industries",
        "- tags",
        "- effective_on",
        "- security / compliance / readiness topic names",
        "- the fact that a candidate is labeled `cross_cutting_requirement`",
        "- the fact that a candidate is labeled `multi_solution`",
        "",
        "Those conditions are handled by existing runtime filters and are not encoded into `runtime_scope_match_mode`.",
        "",
        "## 6. Allowed Modes",
        "",
        "### primary_in_scope",
        "",
        "- Use when the core conclusion is anchored to the primary solution.",
        "- Other solutions may appear as context, optional integration, downstream dependency, or affected system.",
        "- Mentioning multiple solutions does not automatically force `full_applicable_scope`.",
        "",
        "### full_applicable_scope",
        "",
        "- Use only when the core conclusion requires every applicable solution to be present together.",
        "- Typical semantics: joint delivery, end-to-end dependency, combined implementation, or a relationship claim that breaks if one participating solution is missing.",
        "- Do not choose this mode merely because the candidate is about security, readiness, multi-solution, or cross-cutting requirements.",
        "",
        "### global_reusable",
        "",
        "- Use when the core conclusion is independent of which solution is currently in operational scope.",
        "- Runtime filters may still restrict use by document type, industry, tags, date, or excluded solutions.",
        "",
        "## 7. Required Decision Order",
        "",
        "Annotators must follow this order exactly:",
        "",
        "1. Ignore document_type, industries, tags, and effective_on.",
        "2. Judge only solution-scope dependency.",
        "3. If the conclusion is independent of specific solutions, choose `global_reusable`.",
        "4. Else, if the conclusion remains valid when only the primary solution is in scope, choose `primary_in_scope`.",
        "5. Else, if the conclusion requires all applicable solutions together, choose `full_applicable_scope`.",
        "6. Else, mark `manual_review_required = true` and do not guess.",
        "",
        "## 8. Document Default + Chunk Override",
        "",
        "- Continue using `document_default_with_chunk_override`.",
        "- Document Default captures the majority dependency across the document.",
        "- Any chunk with a different dependency must override.",
        "- Override count must not be artificially minimized.",
        "",
        "## 9. Abstract Examples",
        "",
        "### primary_in_scope example",
        "",
        "> An order assistant must complete identity verification before calling a refund API. An identity system can provide the verification capability.",
        "",
        "The core conclusion constrains the order assistant. The identity system is context or dependency, not a jointly required scope condition.",
        "",
        "### full_applicable_scope example",
        "",
        "> A joint workflow is reliable only after both the service platform and order platform finish two-way event synchronization.",
        "",
        "The core conclusion depends on both solutions together.",
        "",
        "### global_reusable example",
        "",
        "> All production knowledge documents must preserve a version number and effective date.",
        "",
        "The rule does not depend on a specific solution being in operational scope.",
        "",
        "### Common traps",
        "",
        "- Security requirements are not automatically `full_applicable_scope`.",
        "- Mentioning multiple solutions is not automatically `full_applicable_scope`.",
        "- `cross_cutting_requirement` is not automatically `global_reusable`.",
        "- `readiness_requirement` is not automatically `full_applicable_scope`.",
        "",
        "## 10. Label Template Rules",
        "",
        "- All mode fields remain null until a human author fills them.",
        "- Rationales must explain:",
        "  - what the core conclusion is anchored to,",
        "  - whether the conclusion still holds without other applicable solutions,",
        "  - why the other two modes were rejected.",
        "",
        "## 11. Why This Session Must Not Label Attempt 2",
        "",
        "- The current session already knows Attempt 1 outcomes and v2.2 design conclusions.",
        "- Therefore it may build the packet, but it cannot act as an independent blind labeler.",
        "",
        "## 12. Next Step After This Packet",
        "",
        "1. Move the blind bundle into an isolated labeling workflow.",
        "2. Complete Attempt 2 labels without reading cases, gold, or results.",
        "3. Freeze labels.",
        "4. Run the one and only Attempt 2 evaluation.",
        "5. Stop boundary-contract research after Attempt 2, regardless of pass or fail.",
        "",
    ]
    return "\n".join(lines) + "\n"


def render_blind_authoring_guide(*, protocol_version: str) -> str:
    lines = [
        f"# Blind Authoring Guide ({protocol_version})",
        "",
        "This bundle contains knowledge content only. It does not include cases, queries, gold, results, or Attempt 1 evidence.",
        "",
        "## Step 1: Ignore non-scope filters",
        "",
        "Before choosing a mode, ignore:",
        "- document_type",
        "- industries",
        "- tags",
        "- effective_on",
        "",
        "Those are runtime filters, not solution-scope dependency.",
        "",
        "## Step 2: Judge only solution-scope dependency",
        "",
        "Ask whether the chunk's core conclusion depends on:",
        "- only the primary solution,",
        "- all applicable solutions together,",
        "- or no specific solution at all.",
        "",
        "## Step 3: Follow the fixed decision order",
        "",
        "1. If the core conclusion is solution-independent, choose `global_reusable`.",
        "2. Else, if the conclusion still holds when only the primary solution is in scope, choose `primary_in_scope`.",
        "3. Else, if the conclusion requires all applicable solutions together, choose `full_applicable_scope`.",
        "4. Else, set `manual_review_required = true`.",
        "",
        "## What runtime_scope_match_mode is NOT",
        "",
        "- not a document type",
        "- not a topic label",
        "- not a security level",
        "- not a readiness class",
        "- not a business priority",
        "- not a retrieval priority",
        "",
        "## Hard negatives",
        "",
        "- Do not choose `full_applicable_scope` just because the content is about security.",
        "- Do not choose `full_applicable_scope` just because the content is about readiness.",
        "- Do not choose any mode directly from `multi_solution` or `cross_cutting_requirement` alone.",
        "",
        "## Document Default + Chunk Override",
        "",
        "- Start with a document default if the majority of chunks share the same dependency.",
        "- Then inspect each chunk independently.",
        "- If a chunk's dependency differs, add an override.",
        "",
        "## Abstract examples",
        "",
        "- A primary assistant with optional identity verification context usually stays `primary_in_scope`.",
        "- A two-system synchronization rule usually becomes `full_applicable_scope`.",
        "- A universal versioning policy usually becomes `global_reusable`.",
        "",
        "## Rationale checklist",
        "",
        "For each filled rationale, answer:",
        "- What is the core conclusion anchored to?",
        "- If another applicable solution is missing, does the conclusion still hold?",
        "- Why are the other two modes wrong?",
        "",
    ]
    return "\n".join(lines) + "\n"


def run_leak_scanner(
    *,
    files: dict[str, str],
    document_ids: list[str],
    chunk_ids: list[str],
    attempt_1_opaque_ids: list[str],
) -> None:
    for file_name, content in files.items():
        for marker in LEAK_MARKERS:
            if marker in content:
                raise ValueError(f"Blind bundle leak scanner detected forbidden marker '{marker}' in {file_name}.")
        for document_id in document_ids:
            if document_id in content:
                raise ValueError(
                    f"Blind bundle leak scanner detected original document_id '{document_id}' in {file_name}."
                )
        for chunk_id in chunk_ids:
            if chunk_id in content:
                raise ValueError(f"Blind bundle leak scanner detected original chunk_id '{chunk_id}' in {file_name}.")
        for opaque_id in attempt_1_opaque_ids:
            if opaque_id in content:
                raise ValueError(
                    f"Blind bundle leak scanner detected Attempt 1 opaque_id '{opaque_id}' in {file_name}."
                )


def _build_packet_record(
    *,
    document: KnowledgeDocumentV2,
    chunks: list[KnowledgeChunkV2],
    document_opaque_id: str,
    chunk_map: dict[str, str],
) -> dict[str, Any]:
    return {
        "opaque_document_id": document_opaque_id,
        "title": document.title,
        "summary": document.summary,
        "document_type": document.document_type.value,
        "scope_type": document.scope_type.value,
        "primary_solution": document.primary_solution_id,
        "applicable_solutions": list(document.applicable_solution_ids),
        "excluded_solutions": list(document.excluded_solution_ids),
        "industries": list(document.industries),
        "tags": list(document.tags),
        "effective_on": {
            "effective_from": document.effective_from.isoformat() if document.effective_from else None,
            "effective_until": document.effective_until.isoformat() if document.effective_until else None,
        },
        "chunks": [
            {
                "opaque_chunk_id": chunk_map[chunk.chunk_id],
                "citation_label": chunk.citation_label,
                "section_heading": str(chunk.metadata.get("section_title") or ""),
                "content": chunk.content,
                "scope_metadata": {
                    "scope_type": chunk.scope_type.value,
                    "primary_solution": chunk.primary_solution_id,
                    "applicable_solutions": list(chunk.applicable_solution_ids),
                    "excluded_solutions": list(chunk.excluded_solution_ids),
                    "scope_notes": chunk.scope_notes,
                },
                "differs_from_document_metadata": _chunk_differs_from_document(chunk=chunk, document=document),
            }
            for chunk in chunks
        ],
    }


def _build_label_template_record(
    *,
    document: KnowledgeDocumentV2,
    chunks: list[KnowledgeChunkV2],
    document_opaque_id: str,
    chunk_map: dict[str, str],
) -> dict[str, Any]:
    return {
        "opaque_document_id": document_opaque_id,
        "document_default_mode": None,
        "document_confidence": None,
        "document_rationale": None,
        "document_manual_review_required": None,
        "chunk_overrides": [
            {
                "opaque_chunk_id": chunk_map[chunk.chunk_id],
                "runtime_scope_match_mode": None,
                "confidence": None,
                "rationale": None,
                "manual_review_required": None,
            }
            for chunk in chunks
        ],
    }


def _build_manifest_payload(
    *,
    documents: list[KnowledgeDocumentV2],
    chunks: list[KnowledgeChunkV2],
    solution_catalog: DemoSolutionScope,
    packet_text: str,
    guide_text: str,
    template_text: str,
    mapping_text: str,
    opaque_ids_differ_from_attempt_1: bool,
) -> dict[str, Any]:
    generated_at = max(document.updated_at for document in documents).isoformat().replace("+00:00", "Z")
    return {
        "protocol_version": 2.2,
        "blind_attempt_number": BLIND_ATTEMPT_NUMBER,
        "schema_changed": False,
        "mode_enum_changed": False,
        "runtime_schema_changed": False,
        "change_scope": "guide_and_protocol_only",
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "selected_solution_count": len(solution_catalog.selected_solution_ids),
        "packet_contains_cases": False,
        "packet_contains_queries": False,
        "packet_contains_gold": False,
        "packet_contains_results": False,
        "packet_contains_attempt_1_labels": False,
        "packet_contains_failure_analysis": False,
        "labels_prefilled": False,
        "original_ids_exposed": False,
        "opaque_ids_differ_from_attempt_1": opaque_ids_differ_from_attempt_1,
        "packet_sha256": _sha256_text(packet_text),
        "guide_sha256": _sha256_text(guide_text),
        "template_sha256": _sha256_text(template_text),
        "mapping_sha256": _sha256_text(mapping_text),
        "source_document_hash": _sha256_file(KB_DOCUMENTS_PATH),
        "source_chunk_hash": _sha256_file(KB_CHUNKS_PATH),
        "generated_at": generated_at,
        "retriever_v2_status": "blocked_by_candidate_recall",
        "architecture_c_status": "blocked",
    }


def _build_opaque_mapping(*, prefix: str, source_ids: list[str], protocol_version: str) -> dict[str, dict[str, str]]:
    forward: dict[str, str] = {}
    reverse: dict[str, str] = {}
    for source_id in source_ids:
        opaque_id = _make_opaque_id(prefix=prefix, source_id=source_id, protocol_version=protocol_version)
        if opaque_id in reverse:
            raise ValueError(f"Opaque ID collision detected for {prefix}.")
        forward[source_id] = opaque_id
        reverse[opaque_id] = source_id
    return {"forward": forward, "reverse": reverse}


def _make_opaque_id(*, prefix: str, source_id: str, protocol_version: str) -> str:
    digest = hashlib.sha256(f"{OPAQUE_SALT}:{protocol_version}:{source_id}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _chunk_differs_from_document(*, chunk: KnowledgeChunkV2, document: KnowledgeDocumentV2) -> bool:
    return any(
        (
            chunk.scope_type != document.scope_type,
            chunk.primary_solution_id != document.primary_solution_id,
            list(chunk.applicable_solution_ids) != list(document.applicable_solution_ids),
            list(chunk.excluded_solution_ids) != list(document.excluded_solution_ids),
            chunk.scope_notes != document.scope_notes,
        )
    )


def _jsonl_text(records: list[dict[str, Any]]) -> str:
    return "\n".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for record in records
    ) + "\n"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_text_if_exists(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return load_json_record(path)


def _load_jsonl_if_exists(path: Path) -> list[dict[str, Any]] | None:
    if not path.exists():
        return None
    return load_jsonl_records(path)
