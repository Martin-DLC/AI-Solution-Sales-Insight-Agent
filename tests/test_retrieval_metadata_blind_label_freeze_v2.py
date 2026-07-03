from __future__ import annotations

import json
import shutil
from pathlib import Path

from evaluation.retrieval import metadata_label_freeze_v2 as module


SOURCE_DIR = Path("/Users/baba/retrieval-metadata-blind-authoring-v2_1.gTtoAX")


def _patch_output_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(module, "TRACKED_LABELS_PATH", tmp_path / "retrieval_metadata_blind_labels.v2_1.jsonl")
    monkeypatch.setattr(module, "TRACKED_REPORT_PATH", tmp_path / "retrieval_metadata_blind_authoring_report.v2_1.json")
    monkeypatch.setattr(module, "TRACKED_FREEZE_MANIFEST_PATH", tmp_path / "retrieval_metadata_blind_label_freeze_manifest.v2_1.json")
    monkeypatch.setattr(module, "TRACKED_DOC_PATH", tmp_path / "34_Retrieval_Metadata_Blind_Label_Freeze.md")


def _patch_output_paths_v2_2(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(module, "TRACKED_LABELS_PATH_V2_2", tmp_path / "retrieval_metadata_blind_labels.v2_2.jsonl")
    monkeypatch.setattr(module, "TRACKED_REPORT_PATH_V2_2", tmp_path / "retrieval_metadata_blind_authoring_report.v2_2.json")
    monkeypatch.setattr(module, "TRACKED_FREEZE_MANIFEST_PATH_V2_2", tmp_path / "retrieval_metadata_blind_label_freeze_manifest.v2_2.json")
    monkeypatch.setattr(module, "TRACKED_DOC_PATH", tmp_path / "34_Retrieval_Metadata_Blind_Label_Freeze.md")


def _write_synthetic_v2_2_source_dir(tmp_path: Path) -> Path:
    source_dir = tmp_path / "blind_attempt_2_source"
    source_dir.mkdir()
    runtime_dir = Path("data/runtime/retrieval_metadata_blind_attempt_2")
    for file_name in ("AUTHORING_GUIDE.md", "authoring_packet.jsonl", "label_template.jsonl", "bundle_manifest.json"):
        shutil.copy2(runtime_dir / file_name, source_dir / file_name)

    template_records = [
        json.loads(line)
        for line in source_dir.joinpath("label_template.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    document_modes = (
        ["primary_in_scope"] * 6
        + ["full_applicable_scope"] * 8
        + ["global_reusable"] * 6
    )
    label_records = []
    chunk_override_modes = [
        "primary_in_scope",
        "primary_in_scope",
        "primary_in_scope",
        "global_reusable",
    ]
    chunk_override_cursor = 0
    for template_record, document_mode in zip(template_records, document_modes):
        label_overrides = []
        for template_override in template_record["chunk_overrides"]:
            label_override = {"opaque_chunk_id": template_override["opaque_chunk_id"]}
            if chunk_override_cursor < len(chunk_override_modes):
                label_override["runtime_scope_match_mode"] = chunk_override_modes[chunk_override_cursor]
                chunk_override_cursor += 1
            label_overrides.append(label_override)
        label_records.append(
            {
                "opaque_document_id": template_record["opaque_document_id"],
                "document_default_mode": document_mode,
                "manual_review_required": False,
                "chunk_overrides": label_overrides,
            }
        )

    source_dir.joinpath("completed_labels.jsonl").write_text(
        "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in label_records) + "\n",
        encoding="utf-8",
    )
    report_payload = {
        "document_count": 20,
        "chunk_count": 40,
        "completed_document_count": 20,
        "chunk_override_count": 4,
        "manual_review_document_count": 0,
        "manual_review_chunk_count": 0,
        "document_default_mode_counts": {
            "primary_in_scope": 6,
            "full_applicable_scope": 8,
            "global_reusable": 6,
        },
        "chunk_override_mode_counts": {
            "primary_in_scope": 3,
            "full_applicable_scope": 0,
            "global_reusable": 1,
        },
        "external_files_accessed": False,
        "network_accessed": False,
        "cases_or_gold_accessed": False,
        "evaluation_performed": False,
    }
    source_dir.joinpath("authoring_report.json").write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return source_dir


def test_external_directory_must_contain_exactly_six_files() -> None:
    source_validation = module.validate_source_directory(source_dir=SOURCE_DIR)
    assert sorted(source_validation["file_names"]) == sorted(module.EXPECTED_SOURCE_FILE_NAMES)


def test_source_hashes_match_frozen_values() -> None:
    source_validation = module.validate_source_directory(source_dir=SOURCE_DIR)
    for file_name, expected_hash in module.EXPECTED_INPUT_HASHES.items():
        assert source_validation["file_hashes"][file_name] == expected_hash
    for file_name, expected_hash in module.EXPECTED_OUTPUT_HASHES.items():
        assert source_validation["file_hashes"][file_name] == expected_hash


def test_freeze_validates_counts_and_mode_distribution() -> None:
    payload = module.freeze_blind_labels(source_dir=SOURCE_DIR)
    manifest = payload["freeze_manifest"]

    assert manifest["document_count"] == 20
    assert manifest["chunk_count"] == 40
    assert manifest["document_default_mode_counts"] == {
        "primary_in_scope": 11,
        "full_applicable_scope": 8,
        "global_reusable": 1,
    }
    assert manifest["chunk_override_count"] == 3
    assert manifest["chunk_override_mode_counts"] == {
        "primary_in_scope": 3,
        "full_applicable_scope": 0,
        "global_reusable": 0,
    }
    assert manifest["manual_review_document_count"] == 0
    assert manifest["manual_review_chunk_count"] == 0


def test_write_preserves_byte_level_hashes(tmp_path, monkeypatch) -> None:
    _patch_output_paths(tmp_path, monkeypatch)
    payload = module.freeze_blind_labels(source_dir=SOURCE_DIR)
    module.write_frozen_outputs(payload)

    assert module.TRACKED_LABELS_PATH.read_bytes() == payload["labels_bytes"]
    assert module.TRACKED_REPORT_PATH.read_bytes() == payload["report_bytes"]
    assert module._sha256_file(module.TRACKED_LABELS_PATH) == module.EXPECTED_OUTPUT_HASHES["completed_labels.jsonl"]
    assert module._sha256_file(module.TRACKED_REPORT_PATH) == module.EXPECTED_OUTPUT_HASHES["authoring_report.json"]


def test_freeze_manifest_has_no_absolute_path_and_blocks_evaluation() -> None:
    payload = module.freeze_blind_labels(source_dir=SOURCE_DIR)
    manifest = payload["freeze_manifest"]
    manifest_text = json.dumps(manifest, ensure_ascii=False, sort_keys=True)

    assert "/Users/baba/" not in manifest_text
    assert manifest["workspace_validation_passed"] is True
    assert manifest["input_hashes_unchanged"] is True
    assert manifest["external_files_accessed"] is False
    assert manifest["network_accessed"] is False
    assert manifest["cases_or_gold_accessed"] is False
    assert manifest["evaluation_performed"] is False
    assert manifest["p0_validation_status"] == "pending"
    assert manifest["metadata_v2_1_versioning_status"] == "blocked_pending_evaluation"
    assert manifest["retriever_v2_status"] == "blocked"
    assert manifest["architecture_c_status"] == "blocked"


def test_leak_scanner_blocks_forbidden_markers() -> None:
    try:
        module.run_leak_scanner(file_name="bad.json", content='{"note":"RET2-001"}')
    except ValueError as exc:
        assert "RET2-" in str(exc)
    else:
        raise AssertionError("Leak scanner should reject forbidden markers.")


def test_check_is_stable_after_write(tmp_path, monkeypatch) -> None:
    _patch_output_paths(tmp_path, monkeypatch)
    payload = module.freeze_blind_labels(source_dir=SOURCE_DIR)
    module.write_frozen_outputs(payload)
    ok, differences = module.check_frozen_outputs()
    assert ok is True
    assert differences == []


def test_v2_2_freeze_supports_versioned_outputs(tmp_path, monkeypatch) -> None:
    source_dir = _write_synthetic_v2_2_source_dir(tmp_path)
    _patch_output_paths_v2_2(tmp_path, monkeypatch)

    expected_label_hash = module._sha256_file(source_dir / "completed_labels.jsonl")
    expected_report_hash = module._sha256_file(source_dir / "authoring_report.json")
    monkeypatch.setattr(
        module,
        "EXPECTED_OUTPUT_HASHES_V2_2",
        {
            "completed_labels.jsonl": expected_label_hash,
            "authoring_report.json": expected_report_hash,
        },
    )

    payload = module.freeze_blind_labels(source_dir=source_dir, protocol_version="2.2", attempt_number=2)
    module.write_frozen_outputs(payload)

    assert module.TRACKED_LABELS_PATH_V2_2.read_bytes() == source_dir.joinpath("completed_labels.jsonl").read_bytes()
    assert module.TRACKED_REPORT_PATH_V2_2.read_bytes() == source_dir.joinpath("authoring_report.json").read_bytes()
    assert module.TRACKED_FREEZE_MANIFEST_PATH_V2_2.exists()

    manifest = payload["freeze_manifest"]
    assert manifest["protocol_version"] == "2.2"
    assert manifest["valid_blind_authoring_attempt_number"] == 2
    assert manifest["attempt_1_status"] == "failed_and_immutable"
    assert manifest["boundary_research_stop_rule"] == "evaluate_attempt_2_once_then_close"
    assert manifest["metadata_versioning_status"] == "blocked_pending_attempt_2_evaluation"
    assert manifest["retriever_v2_status"] == "blocked_by_candidate_recall"
    assert manifest["architecture_c_status"] == "blocked"

    ok, differences = module.check_frozen_outputs(protocol_version="2.2", attempt_number=2)
    assert ok is True
    assert differences == []
