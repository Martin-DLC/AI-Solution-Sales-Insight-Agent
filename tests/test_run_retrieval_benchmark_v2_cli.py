from __future__ import annotations

import json

import scripts.run_retrieval_benchmark_v2 as cli


def test_plan_mode_prints_safe_summary(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "formal_v2_results_exist", lambda: False)
    monkeypatch.setattr(cli.sys, "argv", ["run_retrieval_benchmark_v2.py"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "plan"
    assert payload["formal_results_exist"] is False


def test_validate_mode_passes_without_loading_model(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "formal_v2_results_exist", lambda: False)
    monkeypatch.setattr(cli.sys, "argv", ["run_retrieval_benchmark_v2.py", "--validate"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "validate"
    assert payload["formal_results_exist"] is False


def test_validate_mode_still_passes_when_formal_results_exist(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "formal_v2_results_exist", lambda: True)
    monkeypatch.setattr(cli.sys, "argv", ["run_retrieval_benchmark_v2.py", "--validate"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "validate"
    assert payload["formal_results_exist"] is True


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
    monkeypatch.setattr(cli, "_build_core_validation_payload", lambda: {"mode": "validate", "formal_results_exist": False})
    monkeypatch.setattr(
        cli,
        "inspect_formal_result_state",
        lambda: {
            "state": cli.FORMAL_RESULT_STATE_NOT_GENERATED,
            "existing_paths": {},
            "missing_paths": {},
            "formal_results_exist": False,
        },
    )
    monkeypatch.setattr(cli.sys, "argv", ["run_retrieval_benchmark_v2.py", "--check"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "check"
    assert payload["status"] == "formal_results_not_generated"


def test_formal_readiness_reports_true_without_running_cases(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "_build_core_validation_payload",
        lambda: {
            "benchmark_config_hash": "bench",
            "document_count": 20,
            "chunk_count": 40,
            "case_count": 16,
            "feasible_case_count": 16,
            "formal_results_exist": False,
        },
    )
    monkeypatch.setattr(
        cli,
        "inspect_formal_result_state",
        lambda: {
            "state": cli.FORMAL_RESULT_STATE_NOT_GENERATED,
            "existing_paths": {},
            "missing_paths": {},
            "formal_results_exist": False,
        },
    )
    monkeypatch.setattr(
        cli,
        "_load_vector_config",
        lambda: type(
            "Cfg",
            (),
            {
                "cache_directory": "data/runtime/retrieval_embeddings",
                "model_name_or_path": "intfloat/multilingual-e5-small",
                "model_revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
            },
        )(),
    )
    monkeypatch.setattr(cli, "_network_is_blocked", lambda: True)
    monkeypatch.setattr(cli, "_directory_writable", lambda _path: True)
    monkeypatch.setattr(cli, "is_local_sentence_transformer_model_available", lambda *args, **kwargs: True)
    monkeypatch.setattr(cli.sys, "argv", ["run_retrieval_benchmark_v2.py", "--formal-readiness"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "formal_readiness"
    assert payload["ready_for_single_formal_run"] is True


def test_formal_readiness_reports_false_when_formal_results_exist(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "_build_core_validation_payload",
        lambda: {
            "benchmark_config_hash": "bench",
            "document_count": 20,
            "chunk_count": 40,
            "case_count": 16,
            "feasible_case_count": 16,
            "formal_results_exist": True,
        },
    )
    monkeypatch.setattr(
        cli,
        "inspect_formal_result_state",
        lambda: {
            "state": cli.FORMAL_RESULT_STATE_COMPLETE,
            "existing_paths": {"lexical_results": "x"},
            "missing_paths": {},
            "formal_results_exist": True,
        },
    )
    monkeypatch.setattr(
        cli,
        "_load_vector_config",
        lambda: type(
            "Cfg",
            (),
            {
                "cache_directory": "data/runtime/retrieval_embeddings",
                "model_name_or_path": "intfloat/multilingual-e5-small",
                "model_revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
            },
        )(),
    )
    monkeypatch.setattr(cli, "_network_is_blocked", lambda: True)
    monkeypatch.setattr(cli, "_directory_writable", lambda _path: True)
    monkeypatch.setattr(cli, "is_local_sentence_transformer_model_available", lambda *args, **kwargs: True)
    monkeypatch.setattr(cli.sys, "argv", ["run_retrieval_benchmark_v2.py", "--formal-readiness"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ready_for_single_formal_run"] is False
    assert "formal_results_already_exist" in payload["readiness_reasons"]


def test_run_without_write_is_rejected(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["run_retrieval_benchmark_v2.py", "--run"])

    assert cli.main() == 2
    assert "fixed command" in capsys.readouterr().err
