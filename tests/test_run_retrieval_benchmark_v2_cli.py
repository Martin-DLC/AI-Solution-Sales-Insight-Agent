from __future__ import annotations

import json

import scripts.run_retrieval_benchmark_v2 as cli


def test_plan_mode_prints_safe_summary(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["run_retrieval_benchmark_v2.py"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "plan"
    assert payload["formal_results_exist"] is False


def test_validate_mode_passes_without_loading_model(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["run_retrieval_benchmark_v2.py", "--validate"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "validate"
    assert payload["formal_results_exist"] is False


def test_fake_smoke_uses_fake_provider(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["run_retrieval_benchmark_v2.py", "--fake-smoke"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "fake_smoke"
    assert payload["case_count"] == 2
    assert payload["network_access_attempted"] is False


def test_offline_model_smoke_can_report_unavailable_without_network(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "is_local_sentence_transformer_model_available", lambda *args, **kwargs: False)
    monkeypatch.setattr(cli.sys, "argv", ["run_retrieval_benchmark_v2.py", "--offline-model-smoke"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "offline_model_smoke"
    assert payload["status"] == "local_model_unavailable"


def test_check_mode_reports_formal_results_not_generated(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["run_retrieval_benchmark_v2.py", "--check"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "check"
    assert payload["status"] == "formal_results_not_generated"
