from __future__ import annotations

import json

import scripts.plan_retrieval_v2_migration as migration_cli


def test_cli_plan_mode_does_not_write_file(monkeypatch, tmp_path, capsys) -> None:
    output_path = tmp_path / "retrieval_v2_migration_plan.json"
    monkeypatch.setattr(migration_cli, "PLAN_OUTPUT_PATH", output_path)
    monkeypatch.setattr(migration_cli.sys, "argv", ["plan_retrieval_v2_migration.py"])

    exit_code = migration_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "plan"
    assert output_path.exists() is False


def test_cli_write_then_check_round_trips(monkeypatch, tmp_path, capsys) -> None:
    output_path = tmp_path / "retrieval_v2_migration_plan.json"
    monkeypatch.setattr(migration_cli, "PLAN_OUTPUT_PATH", output_path)

    monkeypatch.setattr(migration_cli.sys, "argv", ["plan_retrieval_v2_migration.py", "--write"])
    write_exit_code = migration_cli.main()
    write_payload = json.loads(capsys.readouterr().out)
    assert write_exit_code == 0
    assert write_payload["plan_version"] == "retrieval_v2_migration_plan_v1"

    monkeypatch.setattr(migration_cli.sys, "argv", ["plan_retrieval_v2_migration.py", "--check"])
    check_exit_code = migration_cli.main()
    check_output = capsys.readouterr().out
    assert check_exit_code == 0
    assert "up to date" in check_output


def test_cli_check_detects_difference(monkeypatch, tmp_path, capsys) -> None:
    output_path = tmp_path / "retrieval_v2_migration_plan.json"
    monkeypatch.setattr(migration_cli, "PLAN_OUTPUT_PATH", output_path)
    output_path.write_text(json.dumps({"plan_version": "wrong"}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(migration_cli.sys, "argv", ["plan_retrieval_v2_migration.py", "--check"])

    exit_code = migration_cli.main()
    stderr = capsys.readouterr().err
    assert exit_code == 1
    assert "plan_version" in stderr
