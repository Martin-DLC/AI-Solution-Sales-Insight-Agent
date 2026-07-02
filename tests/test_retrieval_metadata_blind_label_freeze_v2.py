from __future__ import annotations

import json
from pathlib import Path

from evaluation.retrieval import metadata_label_freeze_v2 as module


SOURCE_DIR = Path("/Users/baba/retrieval-metadata-blind-authoring-v2_1.gTtoAX")


def _patch_output_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(module, "TRACKED_LABELS_PATH", tmp_path / "retrieval_metadata_blind_labels.v2_1.jsonl")
    monkeypatch.setattr(module, "TRACKED_REPORT_PATH", tmp_path / "retrieval_metadata_blind_authoring_report.v2_1.json")
    monkeypatch.setattr(module, "TRACKED_FREEZE_MANIFEST_PATH", tmp_path / "retrieval_metadata_blind_label_freeze_manifest.v2_1.json")
    monkeypatch.setattr(module, "TRACKED_DOC_PATH", tmp_path / "34_Retrieval_Metadata_Blind_Label_Freeze.md")


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
