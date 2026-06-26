from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from scripts.run_node_model_benchmark import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "data/evaluation/model_benchmark/node_cases.jsonl"
CONFIGS_PATH = PROJECT_ROOT / "data/evaluation/model_benchmark/model_configs.deepseek_v4.json"


def test_live_requires_confirm(capsys) -> None:
    exit_code = main(["--cases-file", str(CASES_PATH), "--live", "--configs", str(CONFIGS_PATH), "--max-budget-cny", "5"])
    assert exit_code == 1
    assert "--confirm-live" in capsys.readouterr().err


def test_live_requires_budget(capsys) -> None:
    exit_code = main(["--cases-file", str(CASES_PATH), "--live", "--configs", str(CONFIGS_PATH), "--confirm-live"])
    assert exit_code == 1
    assert "--max-budget-cny" in capsys.readouterr().err


def test_live_requires_configs(capsys) -> None:
    exit_code = main(["--cases-file", str(CASES_PATH), "--live", "--confirm-live", "--max-budget-cny", "5"])
    assert exit_code == 1
    assert "--configs" in capsys.readouterr().err


def test_live_rejects_replay_combination(capsys) -> None:
    exit_code = main([
        "--cases-file", str(CASES_PATH), "--live", "--confirm-live", "--max-budget-cny", "5",
        "--configs", str(CONFIGS_PATH), "--replay", "dummy.jsonl"
    ])
    assert exit_code == 1
    assert "--live cannot be used together with --replay" in capsys.readouterr().err


def test_live_rejects_non_positive_budget(capsys) -> None:
    exit_code = main([
        "--cases-file", str(CASES_PATH), "--live", "--confirm-live", "--max-budget-cny", "0",
        "--configs", str(CONFIGS_PATH)
    ])
    assert exit_code == 1
    assert "Budget must be greater than 0" in capsys.readouterr().err


def test_live_missing_api_key_returns_request_error(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    from evaluation.model_benchmark.live_clients import create_deepseek_live_client_factory

    monkeypatch.setattr(
        "scripts.run_node_model_benchmark.create_deepseek_live_client_factory",
        lambda: create_deepseek_live_client_factory(load_env=False),
    )
    exit_code = main([
        "--cases-file", str(CASES_PATH),
        "--output-root", str(tmp_path / "runs"),
        "--live", "--confirm-live", "--max-budget-cny", "5",
        "--configs", str(CONFIGS_PATH),
        "--case", "NB-FE-01",
    ])
    assert exit_code == 1
    assert "LLM_API_KEY" in capsys.readouterr().err


def test_plan_validate_and_replay_do_not_construct_live_factory(monkeypatch, tmp_path: Path, capsys) -> None:
    called = {"live_factory": 0}

    def fake_factory():
        called["live_factory"] += 1
        raise AssertionError("live factory should not be called")

    monkeypatch.setattr("scripts.run_node_model_benchmark.create_deepseek_live_client_factory", fake_factory)

    assert main(["--cases-file", str(CASES_PATH), "--output-root", str(tmp_path / "plan")]) == 0
    assert main(["--cases-file", str(CASES_PATH), "--output-root", str(tmp_path / "validate"), "--validate"]) == 0
    assert called["live_factory"] == 0
    capsys.readouterr()


def test_live_single_case_prints_three_planned_calls(monkeypatch, capsys, tmp_path: Path) -> None:
    class FakeRunner:
        def __init__(self, *, cases, model_configs, client_factory, output_root, capture_debug_artifacts=False):
            self.cases = cases
            self.model_configs = model_configs
        def _filter_cases(self, case_ids):
            return [case for case in self.cases if case.benchmark_case_id in set(case_ids)]
        def _filter_model_configs(self, model_config_ids):
            return list(self.model_configs)
        def run(self, **kwargs):
            return SimpleNamespace(manifest=SimpleNamespace(
                run_id="MB-TEST",
                output_directory=str(tmp_path / "runs/MB-TEST"),
                completed_run_count=3,
                passed_count=3,
                failed_count=0,
                request_error_count=0,
                estimated_cost_cny=Decimal("0.010000"),
                stopped_by_budget=False,
            ))

    monkeypatch.setattr("scripts.run_node_model_benchmark.NodeModelBenchmarkRunner", FakeRunner)
    monkeypatch.setattr("scripts.run_node_model_benchmark.create_deepseek_live_client_factory", lambda: object())
    exit_code = main([
        "--cases-file", str(CASES_PATH),
        "--output-root", str(tmp_path / "runs"),
        "--live", "--confirm-live", "--max-budget-cny", "5",
        "--configs", str(CONFIGS_PATH),
        "--case", "NB-FE-01",
    ])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Planned runs: 3" in output


def test_live_single_model_filter_prints_matching_call_count(monkeypatch, capsys, tmp_path: Path) -> None:
    class FakeRunner:
        def __init__(self, *, cases, model_configs, client_factory, output_root, capture_debug_artifacts=False):
            self.cases = cases
            self.model_configs = model_configs
        def _filter_cases(self, case_ids):
            return self.cases[:2]
        def _filter_model_configs(self, model_config_ids):
            return [config for config in self.model_configs if config.config_id in set(model_config_ids)]
        def run(self, **kwargs):
            return SimpleNamespace(manifest=SimpleNamespace(
                run_id="MB-TEST",
                output_directory=str(tmp_path / "runs/MB-TEST"),
                completed_run_count=2,
                passed_count=2,
                failed_count=0,
                request_error_count=0,
                estimated_cost_cny=Decimal("0.010000"),
                stopped_by_budget=False,
            ))

    monkeypatch.setattr("scripts.run_node_model_benchmark.NodeModelBenchmarkRunner", FakeRunner)
    monkeypatch.setattr("scripts.run_node_model_benchmark.create_deepseek_live_client_factory", lambda: object())
    exit_code = main([
        "--cases-file", str(CASES_PATH),
        "--output-root", str(tmp_path / "runs"),
        "--live", "--confirm-live", "--max-budget-cny", "5",
        "--configs", str(CONFIGS_PATH),
        "--model-config", "ds-v4-flash-non-thinking",
    ])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Planned runs: 2" in output
