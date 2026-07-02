from __future__ import annotations

import hashlib
import inspect

from evaluation.retrieval import metadata_authoring_v2_2 as module


ATTEMPT_1_PACKET_SHA256 = "314135ac2e1d73dc12980bc097fbbb1e58bf9117b044a47c5cbc19e44ac927a9"
ATTEMPT_1_MAPPING_SHA256 = "f271a15bb6ccce131374a3b7ccfedb107abfa0e2afad6aa4a5a739dc3cfc8518"
ATTEMPT_1_MANIFEST_SHA256 = "7e1c5a20e0afa52ba19da9200b4590b39721e855eafc6689bcb3579a1116ec77"
ATTEMPT_1_DOC_SHA256 = "2d3909d090837f6a390a51a2156eba034e52df48ca37b38f39f210c2538f1c05"

FORMAL_RESULT_HASHES = {
    "lexical_results": "41bfa53dda9a65e78f82eeab064e0a9436b47bb423b3c52d995e3b661e552bad",
    "lexical_summary": "c5a48e917a897bd3ab76b2f815fdc07796e69ff0c9117534e50d0b13058f67e0",
    "vector_results": "9db04530b0240d00175dd5f386b7cc4cea030266ba90bb3180063a5c320244c4",
    "vector_summary": "766801ae928598de3e9ed23097f497764eeeac84e09da56ad6ee60b61cc8d585",
    "hybrid_results": "c5a3ace3ce08914fc7af7426e2c20143863d123b9e5ea3cfff314c0cd8dc5c46",
    "hybrid_summary": "d9543f66c64ff065ba5be0e6cc80a1a97dcafc1caa3fcb4622b6704052679d74",
    "comparison": "92c405e623246dacc154d935f31069f4e31b96e55c8886eea9ec9d314aea618d",
}


def _patch_output_paths(tmp_path, monkeypatch) -> None:
    tracked_packet = tmp_path / "tracked" / "retrieval_metadata_authoring_packet.v2_2.jsonl"
    tracked_mapping = tmp_path / "tracked" / "retrieval_metadata_authoring_mapping.v2_2.json"
    tracked_manifest = tmp_path / "tracked" / "retrieval_metadata_authoring_manifest.v2_2.json"
    tracked_doc = tmp_path / "tracked" / "38_Retrieval_Metadata_Blind_Protocol_V2_2.md"
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


def test_build_authoring_packet_signature_stays_knowledge_only() -> None:
    signature = inspect.signature(module.build_authoring_packet)
    assert list(signature.parameters) == ["documents", "chunks", "solution_catalog", "protocol_version"]


def test_plan_payload_keeps_cases_gold_and_results_forbidden() -> None:
    payload = module.build_plan_payload()
    assert payload["document_count"] == 20
    assert payload["chunk_count"] == 40
    assert payload["packet_contains_cases"] is False
    assert payload["packet_contains_gold"] is False
    assert payload["packet_contains_results"] is False
    assert payload["packet_contains_attempt_1_labels"] is False
    assert payload["packet_contains_failure_analysis"] is False
    assert payload["labels_prefilled"] is False


def test_packet_counts_and_no_original_ids() -> None:
    documents, chunks, scope = module.load_authoring_sources()
    payload = module.build_authoring_packet(documents, chunks, scope, module.PROTOCOL_VERSION)
    packet_text = payload["tracked_artifacts"][module.TRACKED_PACKET_PATH]

    assert len(payload["packet_records"]) == 20
    assert sum(len(record["chunks"]) for record in payload["packet_records"]) == 40
    for document in documents:
        assert document.document_id not in packet_text
    for chunk in chunks:
        assert chunk.chunk_id not in packet_text


def test_attempt_2_opaque_ids_differ_from_attempt_1() -> None:
    documents, chunks, scope = module.load_authoring_sources()
    payload = module.build_authoring_packet(documents, chunks, scope, module.PROTOCOL_VERSION)
    mapping = payload["mapping_payload"]

    assert all(opaque_id.startswith("DOC-AUTH2-") for opaque_id in mapping["document_id_to_opaque_document_id"].values())
    assert all(opaque_id.startswith("CHUNK-AUTH2-") for opaque_id in mapping["chunk_id_to_opaque_chunk_id"].values())
    assert payload["bundle_manifest_payload"]["opaque_ids_differ_from_attempt_1"] is True


def test_label_template_is_blank() -> None:
    documents, chunks, scope = module.load_authoring_sources()
    payload = module.build_authoring_packet(documents, chunks, scope, module.PROTOCOL_VERSION)
    for record in payload["label_template_records"]:
        assert record["document_default_mode"] is None
        assert record["document_confidence"] is None
        assert record["document_rationale"] is None
        assert record["document_manual_review_required"] is None
        for chunk_override in record["chunk_overrides"]:
            assert chunk_override["runtime_scope_match_mode"] is None
            assert chunk_override["confidence"] is None
            assert chunk_override["rationale"] is None
            assert chunk_override["manual_review_required"] is None


def test_guide_clarifies_scope_modes_vs_runtime_filters() -> None:
    guide = module.render_blind_authoring_guide(protocol_version=module.PROTOCOL_VERSION)
    assert "document_type" in guide
    assert "industries" in guide
    assert "tags" in guide
    assert "effective_on" in guide
    assert "security" in guide
    assert "readiness" in guide
    assert "multi_solution" in guide
    assert "cross_cutting_requirement" in guide
    assert "global_reusable" in guide
    assert "primary_in_scope" in guide
    assert "full_applicable_scope" in guide


def test_protocol_doc_states_no_schema_or_runtime_changes() -> None:
    protocol = module.render_protocol_markdown(protocol_version=module.PROTOCOL_VERSION)
    assert "Do not add `any_applicable_scope`." in protocol
    assert "Do not add runtime fields." in protocol
    assert "guide-and-protocol clarification only" in protocol


def test_bundle_runtime_dir_excludes_mapping(tmp_path, monkeypatch) -> None:
    _patch_output_paths(tmp_path, monkeypatch)
    documents, chunks, scope = module.load_authoring_sources()
    payload = module.build_authoring_packet(documents, chunks, scope, module.PROTOCOL_VERSION)
    module.write_authoring_outputs(payload)

    assert module.RUNTIME_GUIDE_PATH.exists()
    assert module.RUNTIME_PACKET_PATH.exists()
    assert module.RUNTIME_TEMPLATE_PATH.exists()
    assert module.RUNTIME_MANIFEST_PATH.exists()
    assert not (module.RUNTIME_BUNDLE_DIR / "retrieval_metadata_authoring_mapping.v2_2.json").exists()


def test_leak_scanner_blocks_attempt_1_and_case_markers() -> None:
    documents, chunks, _scope = module.load_authoring_sources()
    try:
        module.run_leak_scanner(
            files={"bad.jsonl": '{"note":"RET2-001 DOC-AUTH-1234567890abcdef"}'},
            document_ids=[document.document_id for document in documents],
            chunk_ids=[chunk.chunk_id for chunk in chunks],
            attempt_1_opaque_ids=["DOC-AUTH-1234567890abcdef"],
        )
    except ValueError as exc:
        assert "RET2-" in str(exc) or "Attempt 1 opaque_id" in str(exc)
    else:
        raise AssertionError("Leak scanner should reject forbidden markers.")


def test_write_outputs_and_check_are_stable(tmp_path, monkeypatch) -> None:
    _patch_output_paths(tmp_path, monkeypatch)
    documents, chunks, scope = module.load_authoring_sources()
    payload = module.build_authoring_packet(documents, chunks, scope, module.PROTOCOL_VERSION)
    module.write_authoring_outputs(payload)

    ok, differences = module.check_authoring_outputs()
    assert module.TRACKED_PACKET_PATH.exists()
    assert module.TRACKED_MAPPING_PATH.exists()
    assert module.TRACKED_MANIFEST_PATH.exists()
    assert module.TRACKED_DOC_PATH.exists()
    assert ok is True
    assert differences == []


def test_attempt_1_and_formal_result_hashes_remain_unchanged() -> None:
    assert hashlib.sha256(
        module.Path("data/evaluation/retrieval/retrieval_metadata_authoring_packet.v2_1.jsonl").read_bytes()
    ).hexdigest() == ATTEMPT_1_PACKET_SHA256
    assert hashlib.sha256(
        module.Path("data/evaluation/retrieval/retrieval_metadata_authoring_mapping.v2_1.json").read_bytes()
    ).hexdigest() == ATTEMPT_1_MAPPING_SHA256
    assert hashlib.sha256(
        module.Path("data/evaluation/retrieval/retrieval_metadata_authoring_manifest.v2_1.json").read_bytes()
    ).hexdigest() == ATTEMPT_1_MANIFEST_SHA256
    assert hashlib.sha256(
        module.Path("docs/33_Retrieval_Metadata_Blind_Authoring_Protocol.md").read_bytes()
    ).hexdigest() == ATTEMPT_1_DOC_SHA256

    path_map = {
        "lexical_results": "data/evaluation/retrieval/lexical_baseline_results.v2.jsonl",
        "lexical_summary": "data/evaluation/retrieval/lexical_baseline_summary.v2.json",
        "vector_results": "data/evaluation/retrieval/vector_baseline_results.v2.jsonl",
        "vector_summary": "data/evaluation/retrieval/vector_baseline_summary.v2.json",
        "hybrid_results": "data/evaluation/retrieval/hybrid_baseline_results.v2.jsonl",
        "hybrid_summary": "data/evaluation/retrieval/hybrid_baseline_summary.v2.json",
        "comparison": "data/evaluation/retrieval/retrieval_method_comparison.v2.json",
    }
    for key, path in path_map.items():
        assert hashlib.sha256(module.Path(path).read_bytes()).hexdigest() == FORMAL_RESULT_HASHES[key]
