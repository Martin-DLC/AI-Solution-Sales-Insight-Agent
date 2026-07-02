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

    monkeypatch.setattr(module, "build_plan_payload", lambda source_dir: {"mode": "plan", "source_dir_provided": str(source_dir)})
    monkeypatch.setattr(module, "write_frozen_outputs", lambda payload: calls.append(payload))
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(module.sys, "argv", ["freeze_retrieval_metadata_blind_labels_v2.py", "--source-dir", "/tmp/source"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["mode"] == "plan"
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
    monkeypatch.setattr(module, "check_frozen_outputs", lambda: (True, []))
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(module.sys, "argv", ["freeze_retrieval_metadata_blind_labels_v2.py", "--check"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "blind_label_freeze_outputs_match"


def test_write_mode_reports_freeze_state(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    fake_payload = {
        "freeze_manifest": {
            "document_count": 20,
            "chunk_count": 40,
            "evaluation_performed": False,
            "p0_validation_status": "pending",
            "architecture_c_status": "blocked",
        }
    }
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(module, "freeze_blind_labels", lambda source_dir: fake_payload)
    monkeypatch.setattr(module, "write_frozen_outputs", lambda payload: calls.append(payload))
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(
        module.sys,
        "argv",
        ["freeze_retrieval_metadata_blind_labels_v2.py", "--source-dir", "/tmp/source", "--write"],
    )

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert calls == [fake_payload]
    assert payload["mode"] == "write"
    assert payload["document_count"] == 20
    assert payload["chunk_count"] == 40
    assert payload["evaluation_performed"] is False
    assert payload["p0_validation_status"] == "pending"
