from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_cli_module():
    script_path = Path("scripts/freeze_retrieval_metadata_blind_labels_v2.py")
    spec = importlib.util.spec_from_file_location("freeze_retrieval_metadata_blind_labels_v2", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load freeze_retrieval_metadata_blind_labels_v2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plan_mode_does_not_write(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    calls: list[object] = []

    monkeypatch.setattr(
        module,
        "build_plan_payload",
        lambda source_dir, protocol_version="2.1", attempt_number=1: {
            "mode": "plan",
            "source_dir_provided": str(source_dir),
            "protocol_version": protocol_version,
            "blind_attempt_number": attempt_number,
        },
    )
    monkeypatch.setattr(module, "write_frozen_outputs", lambda payload: calls.append(payload))
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "freeze_retrieval_metadata_blind_labels_v2.py",
            "--protocol-version",
            "2.1",
            "--attempt-number",
            "1",
            "--source-dir",
            "/tmp/source",
        ],
    )

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["mode"] == "plan"
    assert payload["protocol_version"] == "2.1"
    assert payload["blind_attempt_number"] == 1
    assert calls == []


def test_write_requires_source_dir(capsys, monkeypatch) -> None:
    module = _load_cli_module()
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(module.sys, "argv", ["freeze_retrieval_metadata_blind_labels_v2.py", "--write"])

    exit_code = module.main()
    assert exit_code == 2
    assert "--source-dir is required with --write." in capsys.readouterr().err


def test_check_mode_reports_match(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    monkeypatch.setattr(module, "check_frozen_outputs", lambda protocol_version="2.1", attempt_number=1: (True, []))
    monkeypatch.setattr(
        module,
        "_tracked_outputs_for_variant",
        lambda protocol_version="2.1", attempt_number=1: {
            "labels": module.TRACKED_LABELS_PATH,
            "authoring_report": module.TRACKED_REPORT_PATH,
            "freeze_manifest": module.TRACKED_FREEZE_MANIFEST_PATH,
            "freeze_doc": module.TRACKED_DOC_PATH,
        },
    )
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "freeze_retrieval_metadata_blind_labels_v2.py",
            "--protocol-version",
            "2.1",
            "--attempt-number",
            "1",
            "--check",
        ],
    )

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "blind_label_freeze_outputs_match"
    assert payload["protocol_version"] == "2.1"
    assert payload["blind_attempt_number"] == 1


def test_write_mode_reports_freeze_state(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    fake_payload = {
        "protocol_version": "2.1",
        "attempt_number": 1,
        "freeze_manifest": {
            "document_count": 20,
            "chunk_count": 40,
            "evaluation_performed": False,
            "p0_validation_status": "pending",
            "architecture_c_status": "blocked",
        }
    }
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        module,
        "freeze_blind_labels",
        lambda source_dir, protocol_version="2.1", attempt_number=1: fake_payload | {
            "protocol_version": protocol_version,
            "attempt_number": attempt_number,
        },
    )
    monkeypatch.setattr(module, "write_frozen_outputs", lambda payload: calls.append(payload))
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "freeze_retrieval_metadata_blind_labels_v2.py",
            "--protocol-version",
            "2.1",
            "--attempt-number",
            "1",
            "--source-dir",
            "/tmp/source",
            "--write",
        ],
    )

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert calls == [fake_payload]
    assert payload["mode"] == "write"
    assert payload["protocol_version"] == "2.1"
    assert payload["blind_attempt_number"] == 1
    assert payload["document_count"] == 20
    assert payload["chunk_count"] == 40
    assert payload["evaluation_performed"] is False
    assert payload["p0_validation_status"] == "pending"


def test_write_mode_supports_protocol_version_2_2(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    fake_payload = {
        "protocol_version": "2.2",
        "attempt_number": 2,
        "freeze_manifest": {
            "document_count": 20,
            "chunk_count": 40,
            "evaluation_performed": False,
            "p0_validation_status": "pending",
            "architecture_c_status": "blocked",
        },
        "tracked_paths": {
            "labels": Path("data/evaluation/retrieval/retrieval_metadata_blind_labels.v2_2.jsonl"),
            "authoring_report": Path("data/evaluation/retrieval/retrieval_metadata_blind_authoring_report.v2_2.json"),
            "freeze_manifest": Path("data/evaluation/retrieval/retrieval_metadata_blind_label_freeze_manifest.v2_2.json"),
            "freeze_doc": Path("docs/34_Retrieval_Metadata_Blind_Label_Freeze.md"),
        },
    }
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        module,
        "freeze_blind_labels",
        lambda source_dir, protocol_version="2.1", attempt_number=1: fake_payload | {
            "protocol_version": protocol_version,
            "attempt_number": attempt_number,
        },
    )
    monkeypatch.setattr(module, "write_frozen_outputs", lambda payload: calls.append(payload))
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "freeze_retrieval_metadata_blind_labels_v2.py",
            "--protocol-version",
            "2.2",
            "--attempt-number",
            "2",
            "--source-dir",
            "/tmp/source",
            "--write",
        ],
    )

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["mode"] == "write"
    assert payload["protocol_version"] == "2.2"
    assert payload["blind_attempt_number"] == 2
    assert calls[0]["protocol_version"] == "2.2"
    assert calls[0]["attempt_number"] == 2
