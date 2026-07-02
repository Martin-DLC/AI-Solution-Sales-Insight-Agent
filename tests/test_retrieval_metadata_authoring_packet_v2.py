from __future__ import annotations

import inspect
import json
from pathlib import Path

from evaluation.retrieval import metadata_authoring_v2 as module


def _patch_output_paths(tmp_path, monkeypatch) -> None:
    tracked_packet = tmp_path / "tracked" / "retrieval_metadata_authoring_packet.v2_1.jsonl"
    tracked_mapping = tmp_path / "tracked" / "retrieval_metadata_authoring_mapping.v2_1.json"
    tracked_manifest = tmp_path / "tracked" / "retrieval_metadata_authoring_manifest.v2_1.json"
    tracked_doc = tmp_path / "tracked" / "33_Retrieval_Metadata_Blind_Authoring_Protocol.md"
    bundle_dir = tmp_path / "runtime_bundle"

    monkeypatch.setattr(module, "TRACKED_PACKET_PATH", tracked_packet)
    monkeypatch.setattr(module, "TRACKED_MAPPING_PATH", tracked_mapping)
    monkeypatch.setattr(module, "TRACKED_MANIFEST_PATH", tracked_manifest)
    monkeypatch.setattr(module, "TRACKED_DOC_PATH", tracked_doc)
    monkeypatch.setattr(module, "RUNTIME_BUNDLE_DIR", bundle_dir)
    monkeypatch.setattr(module, "RUNTIME_GUIDE_PATH", bundle_dir / "AUTHORING_GUIDE.md")
    monkeypatch.setattr(module, "RUNTIME_PACKET_PATH", bundle_dir / "authoring_packet.jsonl")
    monkeypatch.setattr(module, "RUNTIME_TEMPLATE_PATH", bundle_dir / "label_template.jsonl")
    monkeypatch.setattr(module, "RUNTIME_MANIFEST_PATH", bundle_dir / "bundle_manifest.json")


def test_build_authoring_packet_signature_excludes_cases_gold_and_results() -> None:
    signature = inspect.signature(module.build_authoring_packet)
    assert list(signature.parameters) == ["documents", "chunks", "solution_catalog", "protocol_version"]


def test_packet_counts_and_no_original_ids() -> None:
    documents, chunks, scope = module.load_authoring_sources()
    payload = module.build_authoring_packet(documents, chunks, scope, module.PROTOCOL_VERSION)
    packet_records = payload["packet_records"]
    packet_text = payload["tracked_artifacts"][module.TRACKED_PACKET_PATH]

    assert len(packet_records) == 20
    assert sum(len(record["chunks"]) for record in packet_records) == 40
    for document in documents:
        assert document.document_id not in packet_text
    for chunk in chunks:
        assert chunk.chunk_id not in packet_text


def test_mapping_contains_complete_bidirectional_correspondence() -> None:
    documents, chunks, scope = module.load_authoring_sources()
    payload = module.build_authoring_packet(documents, chunks, scope, module.PROTOCOL_VERSION)
    mapping = payload["mapping_payload"]

    assert len(mapping["document_id_to_opaque_document_id"]) == 20
    assert len(mapping["opaque_document_id_to_document_id"]) == 20
    assert len(mapping["chunk_id_to_opaque_chunk_id"]) == 40
    assert len(mapping["opaque_chunk_id_to_chunk_id"]) == 40
    for source_id, opaque_id in mapping["document_id_to_opaque_document_id"].items():
        assert mapping["opaque_document_id_to_document_id"][opaque_id] == source_id
    for source_id, opaque_id in mapping["chunk_id_to_opaque_chunk_id"].items():
        assert mapping["opaque_chunk_id_to_chunk_id"][opaque_id] == source_id


def test_label_template_is_blank() -> None:
    documents, chunks, scope = module.load_authoring_sources()
    payload = module.build_authoring_packet(documents, chunks, scope, module.PROTOCOL_VERSION)

    for record in payload["label_template_records"]:
        assert record["document_default_mode"] is None
        assert record["document_confidence"] is None
        assert record["document_rationale"] is None
        for chunk_override in record["chunk_overrides"]:
            assert chunk_override["runtime_scope_match_mode"] is None
            assert chunk_override["confidence"] is None
            assert chunk_override["rationale"] is None
            assert chunk_override["manual_review_required"] is None


def test_opaque_ids_are_unique_and_stable() -> None:
    documents, chunks, scope = module.load_authoring_sources()
    payload_a = module.build_authoring_packet(documents, chunks, scope, module.PROTOCOL_VERSION)
    payload_b = module.build_authoring_packet(documents, chunks, scope, module.PROTOCOL_VERSION)
    mapping_a = payload_a["mapping_payload"]
    mapping_b = payload_b["mapping_payload"]

    assert payload_a["bundle_manifest_payload"]["packet_sha256"] == payload_b["bundle_manifest_payload"]["packet_sha256"]
    assert len(set(mapping_a["document_id_to_opaque_document_id"].values())) == 20
    assert len(set(mapping_a["chunk_id_to_opaque_chunk_id"].values())) == 40
    assert mapping_a == mapping_b


def test_guide_uses_only_abstract_examples() -> None:
    guide = module.render_blind_authoring_guide(protocol_version=module.PROTOCOL_VERSION)
    assert "KB-" not in guide
    assert "RET2-" not in guide
    assert "gold" not in guide.casefold() or "不包含任何案例、Query、Gold" in guide


def test_leak_scanner_blocks_forbidden_markers() -> None:
    documents, chunks, _scope = module.load_authoring_sources()
    try:
        module.run_leak_scanner(
            files={"bad.jsonl": '{"note":"RET2-001"}'},
            document_ids=[document.document_id for document in documents],
            chunk_ids=[chunk.chunk_id for chunk in chunks],
        )
    except ValueError as exc:
        assert "RET2-" in str(exc)
    else:
        raise AssertionError("Leak scanner should reject forbidden markers.")


def test_write_outputs_and_check_are_stable(tmp_path, monkeypatch) -> None:
    _patch_output_paths(tmp_path, monkeypatch)
    documents, chunks, scope = module.load_authoring_sources()
    payload = module.build_authoring_packet(documents, chunks, scope, module.PROTOCOL_VERSION)
    module.write_authoring_outputs(payload)

    assert module.TRACKED_PACKET_PATH.exists()
    assert module.TRACKED_MAPPING_PATH.exists()
    assert module.TRACKED_MANIFEST_PATH.exists()
    assert module.TRACKED_DOC_PATH.exists()
    assert module.RUNTIME_GUIDE_PATH.exists()
    assert module.RUNTIME_PACKET_PATH.exists()
    assert module.RUNTIME_TEMPLATE_PATH.exists()
    assert module.RUNTIME_MANIFEST_PATH.exists()
    assert not (module.RUNTIME_BUNDLE_DIR / "retrieval_metadata_authoring_mapping.v2_1.json").exists()

    ok, differences = module.check_authoring_outputs()
    assert ok is True
    assert differences == []


def test_bundle_manifest_keeps_architecture_c_blocked() -> None:
    documents, chunks, scope = module.load_authoring_sources()
    payload = module.build_authoring_packet(documents, chunks, scope, module.PROTOCOL_VERSION)
    manifest = payload["bundle_manifest_payload"]

    assert manifest["packet_contains_cases"] is False
    assert manifest["packet_contains_gold"] is False
    assert manifest["packet_contains_results"] is False
    assert manifest["packet_contains_original_ids"] is False
    assert manifest["labels_prefilled"] is False
    assert manifest["document_count"] == 20
    assert manifest["chunk_count"] == 40
    assert manifest["architecture_c_status"] == "blocked"


def test_plan_payload_stays_knowledge_only() -> None:
    payload = module.build_plan_payload()
    assert payload["document_count"] == 20
    assert payload["chunk_count"] == 40
    assert "case_inputs" in payload["forbidden_source_types"]
    assert "gold_labels" in payload["forbidden_source_types"]
    assert payload["labels_prefilled"] is False
