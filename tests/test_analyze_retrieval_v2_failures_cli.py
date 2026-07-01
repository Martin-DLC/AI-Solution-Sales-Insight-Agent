from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_cli_module():
    script_path = Path("scripts/analyze_retrieval_v2_failures.py")
    spec = importlib.util.spec_from_file_location("analyze_retrieval_v2_failures", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load analyze_retrieval_v2_failures.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plan_mode_does_not_build_full_diagnosis(monkeypatch, capsys) -> None:
    module = _load_cli_module()

    def fail_build() -> None:
        raise AssertionError("plan mode should not build the full diagnosis payload")

    monkeypatch.setattr(module, "build_diagnosis_payload", fail_build)
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(module.sys, "argv", ["analyze_retrieval_v2_failures.py"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["mode"] == "plan"
    assert payload["diagnostic_only"] is True


def test_check_mode_returns_zero_when_outputs_match(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    monkeypatch.setattr(module, "check_diagnosis_outputs", lambda: (True, []))
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(module.sys, "argv", ["analyze_retrieval_v2_failures.py", "--check"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "diagnosis_outputs_match"
    assert payload["differences"] == []


def test_write_mode_reports_tracked_output_paths(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    fake_payload = {
        "diagnosis_version": "retrieval_v2_failure_diagnosis_v1",
        "diagnostic_only": True,
        "architecture_c_status": "blocked",
    }
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(module, "build_diagnosis_payload", lambda: fake_payload)
    monkeypatch.setattr(module, "write_diagnosis_outputs", lambda payload: calls.append(payload))
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(module.sys, "argv", ["analyze_retrieval_v2_failures.py", "--write"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert calls == [fake_payload]
    assert payload["mode"] == "write"
    assert payload["diagnostic_only"] is True
    assert payload["architecture_c_status"] == "blocked"
