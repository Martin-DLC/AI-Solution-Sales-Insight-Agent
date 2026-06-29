from __future__ import annotations

import json
from pathlib import Path

import scripts.run_lexical_retrieval_baseline as cli


def test_cli_plan_mode_prints_safe_summary(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["run_lexical_retrieval_baseline.py"])
    exit_code = cli.main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["knowledge_document_count"] == 20
    assert payload["chunk_count"] == 40
    assert "baseline_config" in payload


def test_cli_write_and_check_modes_use_atomic_outputs(tmp_path, monkeypatch, capsys) -> None:
    results_path = tmp_path / "lexical_results.jsonl"
    summary_path = tmp_path / "lexical_summary.json"
    monkeypatch.setattr(cli, "RESULTS_PATH", results_path)
    monkeypatch.setattr(cli, "SUMMARY_PATH", summary_path)

    monkeypatch.setattr(cli.sys, "argv", ["run_lexical_retrieval_baseline.py", "--write"])
    assert cli.main() == 0
    assert results_path.exists()
    assert summary_path.exists()

    monkeypatch.setattr(cli.sys, "argv", ["run_lexical_retrieval_baseline.py", "--check"])
    assert cli.main() == 0
    assert "up to date" in capsys.readouterr().out


def test_cli_check_reports_diff_paths(tmp_path, monkeypatch, capsys) -> None:
    results_path = tmp_path / "lexical_results.jsonl"
    summary_path = tmp_path / "lexical_summary.json"
    results_path.write_text("{}", encoding="utf-8")
    summary_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli, "RESULTS_PATH", results_path)
    monkeypatch.setattr(cli, "SUMMARY_PATH", summary_path)
    monkeypatch.setattr(cli.sys, "argv", ["run_lexical_retrieval_baseline.py", "--check"])

    exit_code = cli.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "results:length" in captured.err or "summary:" in captured.err
