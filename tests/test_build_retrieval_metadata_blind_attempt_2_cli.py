from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_cli_module():
    script_path = Path("scripts/build_retrieval_metadata_blind_attempt_2.py")
    spec = importlib.util.spec_from_file_location("build_retrieval_metadata_blind_attempt_2", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load build_retrieval_metadata_blind_attempt_2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plan_mode_does_not_write(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    calls: list[object] = []

    monkeypatch.setattr(module, "build_plan_payload", lambda: {"mode": "plan", "blind_attempt_number": 2})
    monkeypatch.setattr(module, "write_authoring_outputs", lambda payload: calls.append(payload))
    monkeypatch.setattr(module.sys, "argv", ["build_retrieval_metadata_blind_attempt_2.py"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "plan"
    assert calls == []


def test_check_mode_reports_match(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    monkeypatch.setattr(module, "check_authoring_outputs", lambda: (True, []))
    monkeypatch.setattr(module.sys, "argv", ["build_retrieval_metadata_blind_attempt_2.py", "--check"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "blind_attempt_2_outputs_match"
    assert payload["differences"] == []


def test_write_mode_reports_attempt_2_status(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    fake_payload = {
        "bundle_manifest_payload": {
            "protocol_version": 2.2,
            "blind_attempt_number": 2,
            "document_count": 20,
            "chunk_count": 40,
            "packet_contains_cases": False,
            "packet_contains_gold": False,
            "packet_contains_results": False,
            "packet_contains_attempt_1_labels": False,
            "labels_prefilled": False,
            "opaque_ids_differ_from_attempt_1": True,
        }
    }
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(module, "load_authoring_sources", lambda: (["docs"], ["chunks"], "scope"))
    monkeypatch.setattr(module, "build_authoring_packet", lambda documents, chunks, scope, protocol_version: fake_payload)
    monkeypatch.setattr(module, "write_authoring_outputs", lambda payload: calls.append(payload))
    monkeypatch.setattr(module.sys, "argv", ["build_retrieval_metadata_blind_attempt_2.py", "--write"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert calls == [fake_payload]
    assert payload["mode"] == "write"
    assert payload["blind_attempt_number"] == 2
    assert payload["document_count"] == 20
    assert payload["chunk_count"] == 40
    assert payload["packet_contains_attempt_1_labels"] is False
    assert payload["opaque_ids_differ_from_attempt_1"] is True
