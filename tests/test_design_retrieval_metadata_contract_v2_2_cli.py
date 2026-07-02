from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from evaluation.retrieval import metadata_contract_v2_2_design as module


def _load_cli_module():
    script_path = Path("scripts/design_retrieval_metadata_contract_v2_2.py")
    spec = importlib.util.spec_from_file_location("design_retrieval_metadata_contract_v2_2", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load design_retrieval_metadata_contract_v2_2.py")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def test_plan_mode_does_not_run_full_analysis(monkeypatch, capsys) -> None:
    cli = _load_cli_module()

    def fail_build() -> None:
        raise AssertionError("plan mode should not build the full proposal payload")

    monkeypatch.setattr(cli, "build_metadata_contract_v2_2_payload", fail_build)
    monkeypatch.setattr(cli, "sys", cli.sys)
    monkeypatch.setattr(cli.sys, "argv", ["design_retrieval_metadata_contract_v2_2.py"])

    exit_code = cli.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["mode"] == "plan"
    assert payload["writes_output_files"] is False


def test_write_mode_writes_outputs(monkeypatch, tmp_path, capsys) -> None:
    cli = _load_cli_module()
    json_path = tmp_path / "proposal.json"
    doc_path = tmp_path / "proposal.md"
    monkeypatch.setattr(module, "TRACKED_PROPOSAL_OUTPUT_PATH", json_path)
    monkeypatch.setattr(module, "TRACKED_PROPOSAL_DOC_PATH", doc_path)
    monkeypatch.setattr(cli, "TRACKED_PROPOSAL_OUTPUT_PATH", json_path)
    monkeypatch.setattr(cli, "TRACKED_PROPOSAL_DOC_PATH", doc_path)
    monkeypatch.setattr(cli.sys, "argv", ["design_retrieval_metadata_contract_v2_2.py", "--write"])

    exit_code = cli.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert json_path.exists()
    assert doc_path.exists()
    assert payload["mode"] == "write"
    assert payload["best_schema_variant"] == "D0"
    assert payload["all_40_chunks_have_perfect_assignment"] is True


def test_check_mode_is_stable(monkeypatch, tmp_path, capsys) -> None:
    cli = _load_cli_module()
    json_path = tmp_path / "proposal.json"
    doc_path = tmp_path / "proposal.md"
    monkeypatch.setattr(module, "TRACKED_PROPOSAL_OUTPUT_PATH", json_path)
    monkeypatch.setattr(module, "TRACKED_PROPOSAL_DOC_PATH", doc_path)
    monkeypatch.setattr(cli, "TRACKED_PROPOSAL_OUTPUT_PATH", json_path)
    monkeypatch.setattr(cli, "TRACKED_PROPOSAL_DOC_PATH", doc_path)
    module.write_metadata_contract_v2_2_outputs(module.build_metadata_contract_v2_2_payload())
    monkeypatch.setattr(cli.sys, "argv", ["design_retrieval_metadata_contract_v2_2.py", "--check"])

    exit_code = cli.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["mode"] == "check"
    assert payload["status"] == "metadata_contract_v2_2_outputs_match"
    assert payload["differences"] == []
