from __future__ import annotations

import json
from pathlib import Path

import scripts.analyze_retrieval_v1_failures as analysis_cli


def test_cli_plan_mode_does_not_write_output(monkeypatch, tmp_path, capsys) -> None:
    output_path = tmp_path / "retrieval_failure_analysis.v1.json"
    monkeypatch.setattr(analysis_cli, "ANALYSIS_OUTPUT_PATH", output_path)
    monkeypatch.setattr(analysis_cli.sys, "argv", ["analyze_retrieval_v1_failures.py"])

    exit_code = analysis_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "plan"
    assert output_path.exists() is False


def test_cli_write_then_check_round_trips(monkeypatch, tmp_path, capsys) -> None:
    output_path = tmp_path / "retrieval_failure_analysis.v1.json"
    monkeypatch.setattr(analysis_cli, "ANALYSIS_OUTPUT_PATH", output_path)

    monkeypatch.setattr(analysis_cli.sys, "argv", ["analyze_retrieval_v1_failures.py", "--write"])
    write_exit_code = analysis_cli.main()
    write_payload = json.loads(capsys.readouterr().out)

    assert write_exit_code == 0
    assert output_path.exists() is True
    assert write_payload["analysis_version"] == "retrieval_failure_analysis_v1"

    monkeypatch.setattr(analysis_cli.sys, "argv", ["analyze_retrieval_v1_failures.py", "--check"])
    check_exit_code = analysis_cli.main()
    check_output = capsys.readouterr().out

    assert check_exit_code == 0
    assert "up to date" in check_output


def test_cli_write_contains_all_frozen_hashes(monkeypatch, tmp_path, capsys) -> None:
    output_path = tmp_path / "retrieval_failure_analysis.v1.json"
    monkeypatch.setattr(analysis_cli, "ANALYSIS_OUTPUT_PATH", output_path)
    monkeypatch.setattr(analysis_cli.sys, "argv", ["analyze_retrieval_v1_failures.py", "--write"])

    exit_code = analysis_cli.main()
    capsys.readouterr()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert set(payload["frozen_artifact_hashes"]) == set(analysis_cli.ARTIFACT_PATHS)
    assert payload["no_input_artifacts_modified"] is True


def test_cli_check_detects_difference(monkeypatch, tmp_path, capsys) -> None:
    output_path = tmp_path / "retrieval_failure_analysis.v1.json"
    monkeypatch.setattr(analysis_cli, "ANALYSIS_OUTPUT_PATH", output_path)
    output_path.write_text(json.dumps({"analysis_version": "wrong"}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(analysis_cli.sys, "argv", ["analyze_retrieval_v1_failures.py", "--check"])

    exit_code = analysis_cli.main()
    stderr = capsys.readouterr().err

    assert exit_code == 1
    assert "analysis_version" in stderr
