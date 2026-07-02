from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evaluation.retrieval.storage import diff_json_objects, load_json_record, load_jsonl_records, write_many_atomic


TRACKED_AUTHORING_MANIFEST_PATH = Path("data/evaluation/retrieval/retrieval_metadata_authoring_manifest.v2_1.json")
TRACKED_LABELS_PATH = Path("data/evaluation/retrieval/retrieval_metadata_blind_labels.v2_1.jsonl")
TRACKED_REPORT_PATH = Path("data/evaluation/retrieval/retrieval_metadata_blind_authoring_report.v2_1.json")
TRACKED_FREEZE_MANIFEST_PATH = Path("data/evaluation/retrieval/retrieval_metadata_blind_label_freeze_manifest.v2_1.json")
TRACKED_DOC_PATH = Path("docs/34_Retrieval_Metadata_Blind_Label_Freeze.md")

EXPECTED_SOURCE_FILE_NAMES = (
    "AUTHORING_GUIDE.md",
    "authoring_packet.jsonl",
    "authoring_report.json",
    "bundle_manifest.json",
    "completed_labels.jsonl",
    "label_template.jsonl",
)

EXPECTED_INPUT_HASHES = {
    "authoring_packet.jsonl": "314135ac2e1d73dc12980bc097fbbb1e58bf9117b044a47c5cbc19e44ac927a9",
    "AUTHORING_GUIDE.md": "738a2afc587090de35b302a5575f23f66ac66119bf1e812b02e53138eecf16e7",
    "label_template.jsonl": "acd9ed60e0f945071f859f6b0f6d8f28dedd3ce23e9f8b2abf45e22d9428d79f",
}
EXPECTED_OUTPUT_HASHES = {
    "completed_labels.jsonl": "58729c71ba03adce96f7e89170a9bc52bf637a028a7cfb33f1acd1b504327e92",
    "authoring_report.json": "13fce4a4793b3854daeeba0f1d4786ffa72dbe64d9c6b7c6066b8333899ebbc3",
}
ALLOWED_MODES = {"primary_in_scope", "full_applicable_scope", "global_reusable"}
LEAK_MARKERS = (
    "RET2-",
    "evaluation_gold",
    "expected_document",
    "expected_chunk",
    "forbidden_document",
    "forbidden_solution",
    "recall_at_",
    "precision_at_",
    "eligible_for_rag",
    "selected_method",
    "41bfa53dda9a65e78f82eeab064e0a9436b47bb423b3c52d995e3b661e552bad",
    "c5a48e917a897bd3ab76b2f815fdc07796e69ff0c9117534e50d0b13058f67e0",
    "9db04530b0240d00175dd5f386b7cc4cea030266ba90bb3180063a5c320244c4",
    "766801ae928598de3e9ed23097f497764eeeac84e09da56ad6ee60b61cc8d585",
    "c5a3ace3ce08914fc7af7426e2c20143863d123b9e5ea3cfff314c0cd8dc5c46",
    "d9543f66c64ff065ba5be0e6cc80a1a97dcafc1caa3fcb4622b6704052679d74",
    "92c405e623246dacc154d935f31069f4e31b96e55c8886eea9ec9d314aea618d",
)


def build_plan_payload(*, source_dir: Path) -> dict[str, Any]:
    return {
        "mode": "plan",
        "source_dir_provided": str(source_dir),
        "expected_source_file_names": list(EXPECTED_SOURCE_FILE_NAMES),
        "tracked_outputs": {
            "labels": str(TRACKED_LABELS_PATH),
            "authoring_report": str(TRACKED_REPORT_PATH),
            "freeze_manifest": str(TRACKED_FREEZE_MANIFEST_PATH),
            "freeze_doc": str(TRACKED_DOC_PATH),
        },
        "freeze_scope": "validate_import_and_freeze_only",
        "evaluation_performed": False,
        "architecture_c_status": "blocked",
    }


def freeze_blind_labels(*, source_dir: Path) -> dict[str, Any]:
    source_validation = validate_source_directory(source_dir=source_dir)
    labels_bytes = (source_dir / "completed_labels.jsonl").read_bytes()
    report_bytes = (source_dir / "authoring_report.json").read_bytes()
    labels_records = _parse_jsonl_bytes(labels_bytes)
    template_records = _parse_jsonl_bytes((source_dir / "label_template.jsonl").read_bytes())
    report_payload = json.loads(report_bytes.decode("utf-8"))

    label_stats = validate_labels_payload(
        labels_records=labels_records,
        template_records=template_records,
    )
    validate_authoring_report(report_payload=report_payload, label_stats=label_stats)

    run_leak_scanner(
        file_name="completed_labels.jsonl",
        content=labels_bytes.decode("utf-8"),
    )
    run_leak_scanner(
        file_name="authoring_report.json",
        content=report_bytes.decode("utf-8"),
    )

    labels_hash = _sha256_bytes(labels_bytes)
    report_hash = _sha256_bytes(report_bytes)
    freeze_manifest = build_freeze_manifest(
        source_validation=source_validation,
        label_stats=label_stats,
        completed_labels_sha256=labels_hash,
        authoring_report_sha256=report_hash,
    )
    doc_text = render_freeze_markdown(freeze_manifest=freeze_manifest)

    return {
        "source_validation": source_validation,
        "labels_bytes": labels_bytes,
        "report_bytes": report_bytes,
        "freeze_manifest": freeze_manifest,
        "doc_text": doc_text,
    }


def write_frozen_outputs(payload: dict[str, Any]) -> None:
    items = [
        (TRACKED_LABELS_PATH, payload["labels_bytes"].decode("utf-8")),
        (TRACKED_REPORT_PATH, payload["report_bytes"].decode("utf-8")),
        (TRACKED_FREEZE_MANIFEST_PATH, json.dumps(payload["freeze_manifest"], ensure_ascii=False, indent=2, sort_keys=True) + "\n"),
        (TRACKED_DOC_PATH, payload["doc_text"]),
    ]
    write_many_atomic(items)


def check_frozen_outputs() -> tuple[bool, list[str]]:
    differences: list[str] = []
    if not TRACKED_LABELS_PATH.exists():
        differences.append(f"Missing tracked labels: {TRACKED_LABELS_PATH}")
    if not TRACKED_REPORT_PATH.exists():
        differences.append(f"Missing tracked report: {TRACKED_REPORT_PATH}")
    if not TRACKED_FREEZE_MANIFEST_PATH.exists():
        differences.append(f"Missing tracked freeze manifest: {TRACKED_FREEZE_MANIFEST_PATH}")
    if not TRACKED_DOC_PATH.exists():
        differences.append(f"Missing tracked freeze doc: {TRACKED_DOC_PATH}")
    if differences:
        return False, differences

    labels_bytes = TRACKED_LABELS_PATH.read_bytes()
    report_bytes = TRACKED_REPORT_PATH.read_bytes()
    labels_records = _parse_jsonl_bytes(labels_bytes)
    template_records = _parse_jsonl_bytes((Path("data/runtime/retrieval_metadata_blind_authoring_v2_1") / "label_template.jsonl").read_bytes())
    label_stats = validate_labels_payload(labels_records=labels_records, template_records=template_records)
    report_payload = json.loads(report_bytes.decode("utf-8"))
    validate_authoring_report(report_payload=report_payload, label_stats=label_stats)
    run_leak_scanner(file_name=TRACKED_LABELS_PATH.name, content=labels_bytes.decode("utf-8"))
    run_leak_scanner(file_name=TRACKED_REPORT_PATH.name, content=report_bytes.decode("utf-8"))

    manifest_payload = load_json_record(TRACKED_FREEZE_MANIFEST_PATH)
    recomputed_manifest = build_freeze_manifest_from_tracked(
        label_stats=label_stats,
        completed_labels_sha256=_sha256_bytes(labels_bytes),
        authoring_report_sha256=_sha256_bytes(report_bytes),
    )
    differences.extend(diff_json_objects(manifest_payload, recomputed_manifest, path="freeze_manifest"))

    rendered_doc = render_freeze_markdown(freeze_manifest=recomputed_manifest)
    tracked_doc = TRACKED_DOC_PATH.read_text(encoding="utf-8")
    if tracked_doc != rendered_doc:
        differences.append(f"Tracked freeze doc drifted: {TRACKED_DOC_PATH}")
    return (not differences, differences)


def validate_source_directory(*, source_dir: Path) -> dict[str, Any]:
    if not source_dir.exists():
        raise ValueError(f"Source directory does not exist: {source_dir}")
    if not source_dir.is_dir():
        raise ValueError(f"Source path is not a directory: {source_dir}")

    entries = sorted(source_dir.iterdir(), key=lambda item: item.name)
    file_names = [entry.name for entry in entries if entry.is_file()]
    subdirs = [entry.name for entry in entries if entry.is_dir()]
    if subdirs:
        raise ValueError(f"Source directory must not contain subdirectories: {subdirs}")
    if sorted(file_names) != sorted(EXPECTED_SOURCE_FILE_NAMES):
        raise ValueError("Source directory must contain exactly the expected 6 files.")
    for forbidden_name in (".git", ".env", "AGENTS.md"):
        if forbidden_name in file_names:
            raise ValueError(f"Source directory contains forbidden file: {forbidden_name}")
    if any("mapping" in name.casefold() for name in file_names):
        raise ValueError("Source directory must not contain mapping files.")

    file_hashes = {name: _sha256_file(source_dir / name) for name in file_names}
    for name, expected_hash in EXPECTED_INPUT_HASHES.items():
        if file_hashes[name] != expected_hash:
            raise ValueError(f"Input hash mismatch for {name}.")
    for name, expected_hash in EXPECTED_OUTPUT_HASHES.items():
        if file_hashes[name] != expected_hash:
            raise ValueError(f"Output hash mismatch for {name}.")

    bundle_manifest = json.loads((source_dir / "bundle_manifest.json").read_text(encoding="utf-8"))
    authoring_manifest = load_json_record(TRACKED_AUTHORING_MANIFEST_PATH)
    for key in ("packet_sha256", "guide_sha256", "template_sha256", "document_count", "chunk_count"):
        if bundle_manifest[key] != authoring_manifest[key]:
            raise ValueError(f"Blind bundle manifest drifted on key: {key}")

    return {
        "file_names": file_names,
        "file_hashes": file_hashes,
        "workspace_validation_passed": True,
        "input_hashes_unchanged": True,
        "document_count": bundle_manifest["document_count"],
        "chunk_count": bundle_manifest["chunk_count"],
        "bundle_manifest_sha256": _sha256_file(source_dir / "bundle_manifest.json"),
    }


def validate_labels_payload(*, labels_records: list[dict[str, Any]], template_records: list[dict[str, Any]]) -> dict[str, Any]:
    if len(labels_records) != 20:
        raise ValueError(f"completed_labels.jsonl must contain exactly 20 document records; got {len(labels_records)}.")
    if len(template_records) != 20:
        raise ValueError(f"label_template.jsonl must contain exactly 20 document records; got {len(template_records)}.")

    template_document_ids = [record["opaque_document_id"] for record in template_records]
    label_document_ids = [record["opaque_document_id"] for record in labels_records]
    if label_document_ids != template_document_ids:
        raise ValueError("completed_labels.jsonl must preserve label_template.jsonl document order.")
    if len(set(label_document_ids)) != 20:
        raise ValueError("completed_labels.jsonl must cover 20 unique opaque document IDs.")

    template_chunk_ids = []
    label_chunk_ids = []
    document_default_mode_counts = {mode: 0 for mode in ALLOWED_MODES}
    chunk_override_mode_counts = {mode: 0 for mode in ALLOWED_MODES}
    manual_review_document_count = 0
    manual_review_chunk_count = 0
    chunk_override_count = 0

    for template_record, label_record in zip(template_records, labels_records):
        mode = label_record.get("document_default_mode")
        if mode not in ALLOWED_MODES:
            raise ValueError("Document default mode must be one of the allowed runtime_scope_match_mode values.")
        document_default_mode_counts[mode] += 1
        if label_record.get("manual_review_required") is True:
            manual_review_document_count += 1
        template_overrides = template_record["chunk_overrides"]
        label_overrides = label_record["chunk_overrides"]
        if len(template_overrides) != len(label_overrides):
            raise ValueError("Chunk override count must match the template.")
        template_chunk_ids.extend(item["opaque_chunk_id"] for item in template_overrides)
        label_chunk_ids.extend(item["opaque_chunk_id"] for item in label_overrides)
        if [item["opaque_chunk_id"] for item in label_overrides] != [item["opaque_chunk_id"] for item in template_overrides]:
            raise ValueError("Chunk override order must match the template.")
        for chunk_override in label_overrides:
            chunk_mode = chunk_override.get("runtime_scope_match_mode")
            if chunk_mode is not None:
                if chunk_mode not in ALLOWED_MODES:
                    raise ValueError("Chunk override mode must be one of the allowed runtime_scope_match_mode values.")
                chunk_override_mode_counts[chunk_mode] += 1
                chunk_override_count += 1
            if chunk_override.get("manual_review_required") is True:
                manual_review_chunk_count += 1

    if len(set(label_chunk_ids)) != 40 or len(label_chunk_ids) != 40:
        raise ValueError("completed_labels.jsonl must cover 40 unique opaque chunk IDs.")
    if label_chunk_ids != template_chunk_ids:
        raise ValueError("completed_labels.jsonl must preserve label_template.jsonl chunk order.")

    if document_default_mode_counts != {"primary_in_scope": 11, "full_applicable_scope": 8, "global_reusable": 1}:
        raise ValueError("Document default mode distribution does not match the frozen blind-label output.")
    if chunk_override_count != 3:
        raise ValueError("Chunk override count must equal 3.")
    if chunk_override_mode_counts != {"primary_in_scope": 3, "full_applicable_scope": 0, "global_reusable": 0}:
        raise ValueError("Chunk override mode distribution does not match the frozen blind-label output.")
    if manual_review_document_count != 0 or manual_review_chunk_count != 0:
        raise ValueError("Manual review counts must remain zero in the frozen blind-label output.")

    return {
        "document_count": 20,
        "chunk_count": 40,
        "document_default_mode_counts": document_default_mode_counts,
        "chunk_override_count": chunk_override_count,
        "chunk_override_mode_counts": chunk_override_mode_counts,
        "manual_review_document_count": manual_review_document_count,
        "manual_review_chunk_count": manual_review_chunk_count,
    }


def validate_authoring_report(*, report_payload: dict[str, Any], label_stats: dict[str, Any]) -> None:
    if report_payload.get("document_count") != label_stats["document_count"]:
        raise ValueError("Authoring report document_count does not match frozen labels.")
    if report_payload.get("chunk_count") != label_stats["chunk_count"]:
        raise ValueError("Authoring report chunk_count does not match frozen labels.")
    if report_payload.get("completed_document_count") != label_stats["document_count"]:
        raise ValueError("Authoring report completed_document_count does not match frozen labels.")
    if report_payload.get("chunk_override_count") != label_stats["chunk_override_count"]:
        raise ValueError("Authoring report chunk_override_count does not match frozen labels.")
    if report_payload.get("manual_review_document_count") != label_stats["manual_review_document_count"]:
        raise ValueError("Authoring report manual_review_document_count does not match frozen labels.")
    if report_payload.get("manual_review_chunk_count") != label_stats["manual_review_chunk_count"]:
        raise ValueError("Authoring report manual_review_chunk_count does not match frozen labels.")
    if report_payload.get("document_default_mode_counts") != label_stats["document_default_mode_counts"]:
        raise ValueError("Authoring report document_default_mode_counts do not match frozen labels.")
    if report_payload.get("chunk_override_mode_counts") != label_stats["chunk_override_mode_counts"]:
        raise ValueError("Authoring report chunk_override_mode_counts do not match frozen labels.")
    if report_payload.get("external_files_accessed") is not False:
        raise ValueError("Authoring report must state external_files_accessed=false.")
    if report_payload.get("network_accessed") is not False:
        raise ValueError("Authoring report must state network_accessed=false.")
    if report_payload.get("cases_or_gold_accessed") is not False:
        raise ValueError("Authoring report must state cases_or_gold_accessed=false.")
    if report_payload.get("evaluation_performed") is not False:
        raise ValueError("Authoring report must state evaluation_performed=false.")


def build_freeze_manifest(
    *,
    source_validation: dict[str, Any],
    label_stats: dict[str, Any],
    completed_labels_sha256: str,
    authoring_report_sha256: str,
) -> dict[str, Any]:
    authoring_manifest = load_json_record(TRACKED_AUTHORING_MANIFEST_PATH)
    return {
        "protocol_version": authoring_manifest["protocol_version"],
        "freeze_status": "frozen_before_evaluation",
        "source_workspace_type": "external_isolated_directory",
        "packet_sha256": authoring_manifest["packet_sha256"],
        "guide_sha256": authoring_manifest["guide_sha256"],
        "template_sha256": authoring_manifest["template_sha256"],
        "bundle_manifest_sha256": source_validation["bundle_manifest_sha256"],
        "completed_labels_sha256": completed_labels_sha256,
        "authoring_report_sha256": authoring_report_sha256,
        "document_count": label_stats["document_count"],
        "chunk_count": label_stats["chunk_count"],
        "document_default_mode_counts": label_stats["document_default_mode_counts"],
        "chunk_override_count": label_stats["chunk_override_count"],
        "chunk_override_mode_counts": label_stats["chunk_override_mode_counts"],
        "manual_review_document_count": label_stats["manual_review_document_count"],
        "manual_review_chunk_count": label_stats["manual_review_chunk_count"],
        "workspace_validation_passed": source_validation["workspace_validation_passed"],
        "input_hashes_unchanged": source_validation["input_hashes_unchanged"],
        "external_files_accessed": False,
        "network_accessed": False,
        "cases_or_gold_accessed": False,
        "evaluation_performed": False,
        "labels_modified_after_authoring": False,
        "labels_frozen_before_evaluation": True,
        "blind_authoring_attempt_status": "completed",
        "first_workspace_setup_failure": {
            "occurred": True,
            "before_packet_access": True,
            "labels_generated": False,
            "excluded_from_valid_attempt_count": True,
        },
        "valid_blind_authoring_attempt_number": 1,
        "evaluation_status": "not_started",
        "p0_validation_status": "pending",
        "metadata_v2_1_versioning_status": "blocked_pending_evaluation",
        "retriever_v2_status": "blocked",
        "architecture_c_status": "blocked",
        "generated_at": authoring_manifest["generated_at"],
    }


def build_freeze_manifest_from_tracked(
    *,
    label_stats: dict[str, Any],
    completed_labels_sha256: str,
    authoring_report_sha256: str,
) -> dict[str, Any]:
    authoring_manifest = load_json_record(TRACKED_AUTHORING_MANIFEST_PATH)
    return {
        "protocol_version": authoring_manifest["protocol_version"],
        "freeze_status": "frozen_before_evaluation",
        "source_workspace_type": "external_isolated_directory",
        "packet_sha256": authoring_manifest["packet_sha256"],
        "guide_sha256": authoring_manifest["guide_sha256"],
        "template_sha256": authoring_manifest["template_sha256"],
        "bundle_manifest_sha256": _sha256_file(TRACKED_AUTHORING_MANIFEST_PATH),
        "completed_labels_sha256": completed_labels_sha256,
        "authoring_report_sha256": authoring_report_sha256,
        "document_count": label_stats["document_count"],
        "chunk_count": label_stats["chunk_count"],
        "document_default_mode_counts": label_stats["document_default_mode_counts"],
        "chunk_override_count": label_stats["chunk_override_count"],
        "chunk_override_mode_counts": label_stats["chunk_override_mode_counts"],
        "manual_review_document_count": label_stats["manual_review_document_count"],
        "manual_review_chunk_count": label_stats["manual_review_chunk_count"],
        "workspace_validation_passed": True,
        "input_hashes_unchanged": True,
        "external_files_accessed": False,
        "network_accessed": False,
        "cases_or_gold_accessed": False,
        "evaluation_performed": False,
        "labels_modified_after_authoring": False,
        "labels_frozen_before_evaluation": True,
        "blind_authoring_attempt_status": "completed",
        "first_workspace_setup_failure": {
            "occurred": True,
            "before_packet_access": True,
            "labels_generated": False,
            "excluded_from_valid_attempt_count": True,
        },
        "valid_blind_authoring_attempt_number": 1,
        "evaluation_status": "not_started",
        "p0_validation_status": "pending",
        "metadata_v2_1_versioning_status": "blocked_pending_evaluation",
        "retriever_v2_status": "blocked",
        "architecture_c_status": "blocked",
        "generated_at": authoring_manifest["generated_at"],
    }


def render_freeze_markdown(*, freeze_manifest: dict[str, Any]) -> str:
    lines = [
        "# Retrieval Metadata Blind Label Freeze",
        "",
        "## P1合同假设背景",
        "",
        "- Runtime Boundary Contract v2.1 当前仍是 P1：content explainable but not blind validated。",
        "- 本阶段只负责导入并冻结 blind labels，不做任何效果评估。",
        "",
        "## Blind Packet来源隔离",
        "",
        "- 盲标只基于 authoring packet、guide、template 和 blind bundle manifest 完成。",
        "- 本阶段未读取 Mapping、Cases、Gold、正式 Results 或 Comparison。",
        "",
        "## Workspace Attempt说明",
        "",
        "- 第一次 workspace 设置失败发生在 packet 访问前。",
        "- 该失败没有生成标签，不计入有效 blind authoring attempt 数量。",
        "- 第一次有效 blind authoring attempt 已完成并被冻结。",
        "",
        "## 输入Hash",
        "",
        f"- packet_sha256: {freeze_manifest['packet_sha256']}",
        f"- guide_sha256: {freeze_manifest['guide_sha256']}",
        f"- template_sha256: {freeze_manifest['template_sha256']}",
        f"- bundle_manifest_sha256: {freeze_manifest['bundle_manifest_sha256']}",
        "",
        "## 输出Hash",
        "",
        f"- completed_labels_sha256: {freeze_manifest['completed_labels_sha256']}",
        f"- authoring_report_sha256: {freeze_manifest['authoring_report_sha256']}",
        "",
        "## 覆盖范围",
        "",
        f"- document_count: {freeze_manifest['document_count']}",
        f"- chunk_count: {freeze_manifest['chunk_count']}",
        "",
        "## Mode分布",
        "",
        f"- document_default_mode_counts: {json.dumps(freeze_manifest['document_default_mode_counts'], ensure_ascii=False, sort_keys=True)}",
        f"- chunk_override_count: {freeze_manifest['chunk_override_count']}",
        f"- chunk_override_mode_counts: {json.dumps(freeze_manifest['chunk_override_mode_counts'], ensure_ascii=False, sort_keys=True)}",
        "",
        "## Manual Review",
        "",
        f"- manual_review_document_count: {freeze_manifest['manual_review_document_count']}",
        f"- manual_review_chunk_count: {freeze_manifest['manual_review_chunk_count']}",
        "",
        "## 冻结边界",
        "",
        "- 标签在任何评估开始前被冻结。",
        "- 本阶段未加载 Mapping、Cases 或 Gold。",
        "- 本阶段未进行效果评估，也未计算 retention、boundary removal、recall 或 eligible。",
        "- 若后续评估失败，不得基于评估结果回改同一快照标签。",
        "",
        "## 下一阶段",
        "",
        "- 下一阶段是独立 Evaluation，而不是当前 freeze 阶段继续判断效果。",
        "- RET2-015 / RET2-016 仍是独立 Recall 问题。",
        "- Architecture C 仍为 blocked。",
        "",
    ]
    return "\n".join(lines)


def run_leak_scanner(*, file_name: str, content: str) -> None:
    for marker in LEAK_MARKERS:
        if marker in content:
            raise ValueError(f"Leak scanner detected forbidden marker '{marker}' in {file_name}.")
    if "KB-" in content:
        raise ValueError(f"Leak scanner detected original knowledge-base IDs in {file_name}.")
    lowered = content.casefold()
    if "mapping" in lowered:
        raise ValueError(f"Leak scanner detected mapping content in {file_name}.")


def _parse_jsonl_bytes(raw: bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError("Each JSONL record must be a JSON object.")
        records.append(payload)
    return records


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
