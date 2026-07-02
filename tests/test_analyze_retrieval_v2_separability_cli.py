from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_cli_module():
    script_path = Path("scripts/analyze_retrieval_v2_separability.py")
    spec = importlib.util.spec_from_file_location("analyze_retrieval_v2_separability", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load analyze_retrieval_v2_separability.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plan_mode_does_not_build_full_analysis(monkeypatch, capsys) -> None:
    module = _load_cli_module()

    def fail_build() -> None:
        raise AssertionError("plan mode should not build the full separability payload")

    monkeypatch.setattr(module, "build_separability_payload", fail_build)
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(module.sys, "argv", ["analyze_retrieval_v2_separability.py"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["mode"] == "plan"
    assert payload["diagnostic_only"] is True


def test_check_mode_returns_zero_when_outputs_match(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    monkeypatch.setattr(module, "check_separability_outputs", lambda: (True, []))
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(module.sys, "argv", ["analyze_retrieval_v2_separability.py", "--check"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "separability_outputs_match"
    assert payload["differences"] == []


def test_write_mode_reports_tracked_output_paths(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    fake_payload = {
        "analysis_version": "retrieval_v2_runtime_separability_v1",
        "diagnostic_only": True,
        "retriever_v2_ready_for_implementation": False,
        "runtime_contract_upgrade_required": True,
        "benchmark_case_upgrade_required": False,
        "recommended_next_step": "upgrade_runtime_or_knowledge_metadata_contracts_before_retriever_v2",
        "architecture_c_status": "blocked",
    }
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(module, "build_separability_payload", lambda: fake_payload)
    monkeypatch.setattr(module, "write_separability_outputs", lambda payload: calls.append(payload))
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(module.sys, "argv", ["analyze_retrieval_v2_separability.py", "--write"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert calls == [fake_payload]
    assert payload["mode"] == "write"
    assert payload["architecture_c_status"] == "blocked"
