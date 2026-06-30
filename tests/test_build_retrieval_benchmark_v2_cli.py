from __future__ import annotations

import json

import scripts.build_retrieval_benchmark_v2 as cli


def test_cli_plan_mode_prints_safe_summary(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["build_retrieval_benchmark_v2.py"])

    exit_code = cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "plan"
    assert payload["document_count"] == 20
    assert payload["chunk_count"] == 40
    assert payload["case_count"] == 16
    assert payload["feasible_case_count"] == 16


def test_cli_write_and_check_modes_use_atomic_outputs(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "V2_SCOPE_MIGRATION_PATH", tmp_path / "solution_scope_migration.v2.json")
    monkeypatch.setattr(cli, "V2_DOCUMENTS_PATH", tmp_path / "documents.v2.jsonl")
    monkeypatch.setattr(cli, "V2_CHUNKS_PATH", tmp_path / "chunks.v2.jsonl")
    monkeypatch.setattr(cli, "V2_MANIFEST_PATH", tmp_path / "manifest.v2.json")
    monkeypatch.setattr(cli, "V2_CASE_MIGRATION_PATH", tmp_path / "retrieval_case_migration.v2.json")
    monkeypatch.setattr(cli, "V2_CASES_PATH", tmp_path / "retrieval_cases.v2.jsonl")
    monkeypatch.setattr(cli, "V2_FEASIBILITY_PATH", tmp_path / "retrieval_case_feasibility.v2.json")
    monkeypatch.setattr(cli, "V2_CONFIG_PATH", tmp_path / "retrieval_benchmark_config.v2.json")

    monkeypatch.setattr(cli.sys, "argv", ["build_retrieval_benchmark_v2.py", "--write"])
    assert cli.main() == 0
    assert (tmp_path / "documents.v2.jsonl").exists()
    assert (tmp_path / "retrieval_cases.v2.jsonl").exists()

    monkeypatch.setattr(cli.sys, "argv", ["build_retrieval_benchmark_v2.py", "--check"])
    assert cli.main() == 0
    assert "up to date" in capsys.readouterr().out


def test_cli_write_is_blocked_when_feasibility_is_not_zero(monkeypatch, capsys) -> None:
    artifacts = cli.build_all_artifacts()
    artifacts["retrieval_case_feasibility"]["summary"]["infeasible_case_count"] = 1

    monkeypatch.setattr(cli, "build_all_artifacts", lambda: artifacts)
    monkeypatch.setattr(cli.sys, "argv", ["build_retrieval_benchmark_v2.py", "--write"])

    exit_code = cli.main()

    assert exit_code == 1
    assert "blocked" in capsys.readouterr().err
