from __future__ import annotations

import json

import scripts.run_vector_hybrid_retrieval as cli


def test_cli_plan_mode_does_not_load_model(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "get_embedding_dependency_report", lambda: {"sentence_transformers": False})
    monkeypatch.setattr(cli, "is_local_sentence_transformer_model_available", lambda _: False)
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py"])

    exit_code = cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "plan"


def test_cli_validate_mode_reports_dependency_status(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "get_embedding_dependency_report", lambda: {"sentence_transformers": False})
    monkeypatch.setattr(cli, "is_local_sentence_transformer_model_available", lambda _: False)
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--validate"])

    exit_code = cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "validate"
    assert payload["local_model_available"] is False


def test_cli_fake_smoke_succeeds(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "get_embedding_dependency_report", lambda: {"sentence_transformers": False})
    monkeypatch.setattr(cli, "is_local_sentence_transformer_model_available", lambda _: False)
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--fake-smoke"])

    exit_code = cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "fake_smoke"


def test_cli_write_requires_run(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--write"])

    exit_code = cli.main()

    assert exit_code == 2
    assert "--write must be used together with --run." in capsys.readouterr().err


def test_cli_allow_download_requires_run(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--allow-model-download"])

    exit_code = cli.main()

    assert exit_code == 2
    assert "--allow-model-download must be used together with --run." in capsys.readouterr().err


def test_cli_run_refuses_missing_local_model(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "is_local_sentence_transformer_model_available", lambda _: False)
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--run"])

    exit_code = cli.main()

    assert exit_code == 1
    assert "Local embedding model is unavailable" in capsys.readouterr().err
