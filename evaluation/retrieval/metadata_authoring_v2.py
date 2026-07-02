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
KB_MANIFEST_PATH = Path("data/knowledge_base/manifest.v2.json")
DEMO_SCOPE_PATH = Path("data/knowledge_base/demo_solution_scope.v1.json")

TRACKED_PACKET_PATH = Path("data/evaluation/retrieval/retrieval_metadata_authoring_packet.v2_1.jsonl")
TRACKED_MAPPING_PATH = Path("data/evaluation/retrieval/retrieval_metadata_authoring_mapping.v2_1.json")
TRACKED_MANIFEST_PATH = Path("data/evaluation/retrieval/retrieval_metadata_authoring_manifest.v2_1.json")
TRACKED_DOC_PATH = Path("docs/33_Retrieval_Metadata_Blind_Authoring_Protocol.md")

RUNTIME_BUNDLE_DIR = Path("data/runtime/retrieval_metadata_blind_authoring_v2_1")
RUNTIME_GUIDE_PATH = RUNTIME_BUNDLE_DIR / "AUTHORING_GUIDE.md"
RUNTIME_PACKET_PATH = RUNTIME_BUNDLE_DIR / "authoring_packet.jsonl"
RUNTIME_TEMPLATE_PATH = RUNTIME_BUNDLE_DIR / "label_template.jsonl"
RUNTIME_MANIFEST_PATH = RUNTIME_BUNDLE_DIR / "bundle_manifest.json"

PROTOCOL_VERSION = "retrieval_metadata_blind_authoring_v2_1"

PACKET_SOURCE_TYPES = [
    "knowledge_documents_v2",
    "knowledge_chunks_v2",
    "demo_solution_scope_v1",
    "knowledge_document_chunk_schema",
]

FORBIDDEN_SOURCE_TYPES = [
    "case_inputs",
    "query_inputs",
    "gold_labels",
    "formal_result_artifacts",
    "formal_summary_artifacts",
    "failure_diagnosis_artifacts",
    "candidate_generation_diagnostics",
    "separability_diagnostics",
    "runtime_contract_conflict_analysis",
]

LEAK_MARKERS = (
    "RET2-",
    "expected_document",
    "expected_chunk",
    "forbidden_document",
    "forbidden_solution",
    "evaluation_gold",
    "failed_case",
    "failure_taxonomy",
    "boundary_violating_candidate",
    "relevant_gold_candidate",
    "recall_at_",
    "precision_at_",
    "selected_method",
    "41bfa53dda9a65e78f82eeab064e0a9436b47bb423b3c52d995e3b661e552bad",
    "c5a48e917a897bd3ab76b2f815fdc07796e69ff0c9117534e50d0b13058f67e0",
    "9db04530b0240d00175dd5f386b7cc4cea030266ba90bb3180063a5c320244c4",
    "766801ae928598de3e9ed23097f497764eeeac84e09da56ad6ee60b61cc8d585",
    "c5a3ace3ce08914fc7af7426e2c20143863d123b9e5ea3cfff314c0cd8dc5c46",
    "d9543f66c64ff065ba5be0e6cc80a1a97dcafc1caa3fcb4622b6704052679d74",
    "92c405e623246dacc154d935f31069f4e31b96e55c8886eea9ec9d314aea618d",
)


def build_plan_payload() -> dict[str, Any]:
    documents, chunks, solution_scope = load_authoring_sources()
    return {
        "mode": "plan",
        "protocol_version": PROTOCOL_VERSION,
        "packet_source_types": PACKET_SOURCE_TYPES,
        "forbidden_source_types": FORBIDDEN_SOURCE_TYPES,
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
        "labels_prefilled": False,
        "architecture_c_status": "blocked",
        "blind_authoring_only": True,
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
        prefix="DOC-AUTH",
        source_ids=[document.document_id for document in documents],
        protocol_version=protocol_version,
    )
    chunk_map = _build_opaque_mapping(
        prefix="CHUNK-AUTH",
        source_ids=[chunk.chunk_id for chunk in chunks],
        protocol_version=protocol_version,
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
        "protocol_version": protocol_version,
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
        protocol_version=protocol_version,
        packet_text=packet_text,
        guide_text=guide_text,
        template_text=template_text,
        mapping_text=mapping_text,
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
        differences.extend(
            diff_json_objects(tracked_manifest, recomputed["bundle_manifest_payload"], path="tracked_manifest")
        )

    tracked_doc = _load_text_if_exists(TRACKED_DOC_PATH)
    if tracked_doc is None:
        differences.append(f"Missing tracked protocol doc: {TRACKED_DOC_PATH}")
    elif tracked_doc != recomputed["tracked_artifacts"][TRACKED_DOC_PATH]:
        differences.append(f"Tracked protocol doc drifted: {TRACKED_DOC_PATH}")

    runtime_packet = _load_text_if_exists(RUNTIME_PACKET_PATH)
    if runtime_packet is None:
        differences.append(f"Missing runtime authoring packet: {RUNTIME_PACKET_PATH}")
    elif runtime_packet != recomputed["runtime_bundle_artifacts"][RUNTIME_PACKET_PATH]:
        differences.append(f"Runtime authoring packet drifted: {RUNTIME_PACKET_PATH}")

    runtime_guide = _load_text_if_exists(RUNTIME_GUIDE_PATH)
    if runtime_guide is None:
        differences.append(f"Missing runtime guide: {RUNTIME_GUIDE_PATH}")
    elif runtime_guide != recomputed["runtime_bundle_artifacts"][RUNTIME_GUIDE_PATH]:
        differences.append(f"Runtime guide drifted: {RUNTIME_GUIDE_PATH}")

    runtime_template = _load_text_if_exists(RUNTIME_TEMPLATE_PATH)
    if runtime_template is None:
        differences.append(f"Missing runtime label template: {RUNTIME_TEMPLATE_PATH}")
    elif runtime_template != recomputed["runtime_bundle_artifacts"][RUNTIME_TEMPLATE_PATH]:
        differences.append(f"Runtime label template drifted: {RUNTIME_TEMPLATE_PATH}")

    runtime_manifest = _load_json_if_exists(RUNTIME_MANIFEST_PATH)
    if runtime_manifest is None:
        differences.append(f"Missing runtime bundle manifest: {RUNTIME_MANIFEST_PATH}")
    else:
        differences.extend(
            diff_json_objects(runtime_manifest, recomputed["bundle_manifest_payload"], path="runtime_manifest")
        )

    return (not differences, differences)


def render_protocol_markdown(*, protocol_version: str) -> str:
    lines = [
        "# Retrieval Metadata Blind Authoring Protocol v2.1",
        "",
        "## 为什么当前合同仍是P1",
        "",
        "- Runtime Boundary Contract 当前仅是 P1：content explainable but not blind validated。",
        "- `runtime_scope_match_mode` 的规则可以被设计为不读取 Gold，但当前并未完成盲标、冻结与独立评估。",
        "- 在盲标完成前，Metadata v2.1 不能正式版本化，Retriever v2 不能实现，Architecture C 继续 blocked。",
        "",
        "## Blind Authoring目标",
        "",
        "- 仅基于 Knowledge Base 内容与静态 Metadata 生成盲标包。",
        "- 将原始 Document / Chunk ID 与 authoring 视图隔离。",
        "- 让人工作者先给出静态标签，再进入冻结与独立评估。",
        "",
        "## Packet允许的数据来源",
        "",
        "- Knowledge Documents v2",
        "- Knowledge Chunks v2",
        "- Demo Solution Scope",
        "- Knowledge Base Manifest v2",
        "- 与 Document / Chunk Schema 相关的静态定义",
        "",
        "## 禁止的数据来源",
        "",
        "- Retrieval Cases",
        "- Queries",
        "- Evaluation Gold",
        "- Formal Results / Summaries / Comparison",
        "- Failure Taxonomy 与 Diagnosis",
        "- Candidate Generation / Separability / Runtime Contract 冲突分析",
        "",
        "## Opaque ID设计",
        "",
        f"- Opaque ID 使用 `{protocol_version}` 与 source ID 做 SHA-256 截断，得到稳定但无业务语义的 blind authoring 标识。",
        "- Blind Bundle 中只出现 opaque ID。",
        "- 原始 ID 与 opaque ID 的双向映射只保存在密封 Mapping 文件中，不能带入 blind bundle。",
        "",
        "## Document Default + Chunk Override",
        "",
        "- 先判断 Document 默认值。",
        "- 再判断某些 Chunk 是否需要覆盖 Document 默认值。",
        "- 如果不能仅凭内容与静态 Metadata 确定，应标记 `manual_review_required`。",
        "",
        "## 三种mode定义",
        "",
        "### primary_in_scope",
        "",
        "- 当证据主要服务某个 primary solution。",
        "- 即使文档同时提到其他方案，只要该 primary solution 在 Runtime scope 中，证据即可安全使用。",
        "",
        "### full_applicable_scope",
        "",
        "- 只有当 Candidate 声明的全部 applicable solutions 同时位于 Runtime scope 中，证据才安全使用。",
        "",
        "### global_reusable",
        "",
        "- 证据不依赖具体 solution 组合，在允许的 document type、行业、时间等条件下可全局复用。",
        "",
        "## 人工审核条件",
        "",
        "- multi-solution 语义不清晰",
        "- cross-cutting requirement 既像共享前置条件又像局部边界",
        "- Document 默认值与某个 Chunk 的具体语义明显不同",
        "- 作者无法仅根据知识内容判断静态模式",
        "",
        "## Label Freeze流程",
        "",
        "1. 先基于 blind bundle 独立赋值。",
        "2. 提交空白模板的完整填充版本。",
        "3. 在冻结前不得回看 Cases、Gold 或正式结果。",
        "4. 先冻结标签，再进行独立评估。",
        "",
        "## 为什么标签完成前不能加载Cases和Gold",
        "",
        "- 一旦作者在赋值阶段看到 Case、Query 或 Gold，标签就不再是 blind authoring。",
        "- 当前阶段必须把知识内容判断与评测结果完全隔离。",
        "",
        "## 为什么当前Codex会话不能承担盲标",
        "",
        "- 当前会话已经知道 Runtime Contract 的分析背景。",
        "- 因此本会话只能构建 blind authoring packet，不能执行真正盲标。",
        "",
        "## 新会话与隔离目录要求",
        "",
        "- 盲标应在新会话中进行。",
        "- 新会话只读取 blind bundle，不读取 mapping、cases、gold 或 results。",
        "- 隔离目录必须先于任何评估工具开放。",
        "",
        "## 标签提交必须先于评估",
        "",
        "- 任何 retention / boundary / recall 评估都必须发生在标签冻结之后。",
        "",
        "## 失败后禁止回改同一批标签",
        "",
        "- 如果冻结后评估失败，不应在同一批标签上继续回改。",
        "- 应开启新版本 blind authoring round，而不是污染已冻结标签。",
        "",
        "## RET2-015/016仍是独立Recall问题",
        "",
        "- Blind Authoring 只能验证 Metadata 侧静态合同是否可行。",
        "- RET2-015 / RET2-016 仍属于 candidate recall 问题，不会因本 packet 自动消失。",
        "",
        "## Architecture C继续blocked",
        "",
        "- 在 blind authoring、label freeze 与独立评估完成前，Architecture C 仍然 blocked。",
        "",
    ]
    return "\n".join(lines)


def render_blind_authoring_guide(*, protocol_version: str) -> str:
    lines = [
        f"# Blind Authoring Guide ({protocol_version})",
        "",
        "本指南只服务 Metadata v2.1 盲标，不包含任何案例、Query、Gold 或正式结果。",
        "",
        "## 赋值顺序",
        "",
        "1. 先阅读 Document 标题、摘要、正文和静态 scope metadata。",
        "2. 判断是否存在一个合理的 Document 默认 mode。",
        "3. 再逐个检查 Chunk 是否需要 override。",
        "4. 若无法仅凭内容与静态 metadata 判断，标记 manual_review_required。",
        "",
        "## 允许的三种mode",
        "",
        "- `primary_in_scope`: 只要 primary solution 在 scope 中即可安全使用。",
        "- `full_applicable_scope`: 必须全部 applicable solutions 都在 scope 中才安全。",
        "- `global_reusable`: 不依赖具体 solution 组合，可全局复用。",
        "",
        "## 禁止做的事情",
        "",
        "- 不要猜测用户 Query。",
        "- 不要根据某个场景可能想要什么答案来赋值。",
        "- 不要根据过往失败或命中情况反推标签。",
        "- 不要尝试恢复原始 Document / Chunk ID。",
        "",
        "## 抽象例子",
        "",
        "- 一个强调某主方案实施步骤、其他方案只作为背景提及的证据，通常更接近 `primary_in_scope`。",
        "- 一个明确要求多个方案共同存在才成立的组合能力说明，通常更接近 `full_applicable_scope`。",
        "- 一个描述全局商业承诺边界或统一安全政策的证据，通常更接近 `global_reusable`。",
        "",
        "## 提交要求",
        "",
        "- 所有字段在提交前必须完整填写或显式标注 manual_review_required。",
        "- 不允许在模板中新增自定义枚举。",
        "",
    ]
    return "\n".join(lines)


def run_leak_scanner(*, files: dict[str, str], document_ids: list[str], chunk_ids: list[str]) -> None:
    for file_name, content in files.items():
        for marker in LEAK_MARKERS:
            if marker in content:
                raise ValueError(f"Blind bundle leak scanner detected forbidden marker '{marker}' in {file_name}.")
        for document_id in document_ids:
            if document_id in content:
                raise ValueError(f"Blind bundle leak scanner detected original document_id '{document_id}' in {file_name}.")
        for chunk_id in chunk_ids:
            if chunk_id in content:
                raise ValueError(f"Blind bundle leak scanner detected original chunk_id '{chunk_id}' in {file_name}.")


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
    protocol_version: str,
    packet_text: str,
    guide_text: str,
    template_text: str,
    mapping_text: str,
) -> dict[str, Any]:
    generated_at = max(document.updated_at for document in documents).isoformat().replace("+00:00", "Z")
    source_document_hash = _sha256_file(KB_DOCUMENTS_PATH)
    source_chunk_hash = _sha256_file(KB_CHUNKS_PATH)
    return {
        "protocol_version": protocol_version,
        "packet_source_types": PACKET_SOURCE_TYPES,
        "forbidden_source_types": FORBIDDEN_SOURCE_TYPES,
        "packet_contains_cases": False,
        "packet_contains_queries": False,
        "packet_contains_gold": False,
        "packet_contains_results": False,
        "packet_contains_failure_labels": False,
        "packet_contains_original_ids": False,
        "labels_prefilled": False,
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "selected_solution_count": len(solution_catalog.selected_solution_ids),
        "packet_sha256": _sha256_text(packet_text),
        "guide_sha256": _sha256_text(guide_text),
        "template_sha256": _sha256_text(template_text),
        "mapping_sha256": _sha256_text(mapping_text),
        "source_document_hash": source_document_hash,
        "source_chunk_hash": source_chunk_hash,
        "generated_at": generated_at,
        "architecture_c_status": "blocked",
        "blind_authoring_only": True,
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
    digest = hashlib.sha256(f"{protocol_version}:{source_id}".encode("utf-8")).hexdigest()[:16]
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
    return "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for record in records) + "\n"


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
