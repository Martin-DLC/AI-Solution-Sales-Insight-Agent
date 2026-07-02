from __future__ import annotations

import json

import scripts.analyze_retrieval_metadata_blind_failures_v2 as cli
from evaluation.retrieval import metadata_blind_failure_analysis_v2 as module


def test_plan_mode_does_not_run_analysis(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["analyze_retrieval_metadata_blind_failures_v2.py"])

    def _unexpected() -> dict[str, object]:
        raise AssertionError("plan mode must not run failure analysis")

    monkeypatch.setattr(cli, "run_blind_failure_analysis", _unexpected)

    exit_code = cli.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["mode"] == "plan"
    assert payload["writes_output_files"] is False


def test_write_mode_writes_outputs(monkeypatch, tmp_path, capsys) -> None:
    json_path = tmp_path / "failure_analysis.json"
    doc_path = tmp_path / "failure_analysis.md"
    monkeypatch.setattr(module, "TRACKED_FAILURE_ANALYSIS_JSON_PATH", json_path)
    monkeypatch.setattr(module, "TRACKED_FAILURE_ANALYSIS_DOC_PATH", doc_path)
    monkeypatch.setattr(cli.sys, "argv", ["analyze_retrieval_metadata_blind_failures_v2.py", "--write"])

    exit_code = cli.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert json_path.exists()
    assert doc_path.exists()
    assert payload["mode"] == "write"
    assert payload["unique_error_candidate_count"] == 11
    assert payload["metadata_v2_2_design_required"] is True


def test_check_mode_is_stable(monkeypatch, tmp_path, capsys) -> None:
    json_path = tmp_path / "failure_analysis.json"
    doc_path = tmp_path / "failure_analysis.md"
    monkeypatch.setattr(module, "TRACKED_FAILURE_ANALYSIS_JSON_PATH", json_path)
    monkeypatch.setattr(module, "TRACKED_FAILURE_ANALYSIS_DOC_PATH", doc_path)
    module.write_failure_analysis_outputs(module.run_blind_failure_analysis())
    monkeypatch.setattr(cli.sys, "argv", ["analyze_retrieval_metadata_blind_failures_v2.py", "--check"])

    exit_code = cli.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["mode"] == "check"
    assert payload["status"] == "blind_failure_analysis_outputs_match"
    assert payload["differences"] == []

