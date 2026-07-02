from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_cli_module():
    script_path = Path("scripts/design_retrieval_runtime_contract_v2.py")
    spec = importlib.util.spec_from_file_location("design_retrieval_runtime_contract_v2", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load design_retrieval_runtime_contract_v2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plan_mode_does_not_build_full_analysis(monkeypatch, capsys) -> None:
    module = _load_cli_module()

    def fail_build() -> None:
        raise AssertionError("plan mode should not build the full runtime contract payload")

    monkeypatch.setattr(module, "build_runtime_contract_design_payload", fail_build)
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(module.sys, "argv", ["design_retrieval_runtime_contract_v2.py"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["mode"] == "plan"
    assert payload["diagnostic_only"] is True


def test_check_mode_returns_zero_when_outputs_match(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    monkeypatch.setattr(module, "check_runtime_contract_outputs", lambda: (True, []))
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(module.sys, "argv", ["design_retrieval_runtime_contract_v2.py", "--check"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "runtime_contract_outputs_match"
    assert payload["differences"] == []


def test_write_mode_reports_contract_status(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    fake_payload = {
        "proposal_version": "retrieval_runtime_boundary_contract_v2_1_proposal_v1",
        "diagnostic_only": True,
        "evidence_classification": "P1_content_explainable_not_blind_validated",
        "proposed_upgrade_scope": "knowledge_metadata_only_v2_1",
        "final_upgrade_scope_decision": "pending_blind_authoring_validation",
        "boundary_contract_ready_for_versioning": False,
        "retriever_v2_ready_for_implementation": False,
        "architecture_c_status": "blocked",
    }
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(module, "build_runtime_contract_design_payload", lambda: fake_payload)
    monkeypatch.setattr(module, "write_runtime_contract_outputs", lambda payload: calls.append(payload))
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(module.sys, "argv", ["design_retrieval_runtime_contract_v2.py", "--write"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert calls == [fake_payload]
    assert payload["mode"] == "write"
    assert payload["evidence_classification"] == "P1_content_explainable_not_blind_validated"
    assert payload["proposed_upgrade_scope"] == "knowledge_metadata_only_v2_1"
    assert payload["final_upgrade_scope_decision"] == "pending_blind_authoring_validation"
    assert payload["architecture_c_status"] == "blocked"
