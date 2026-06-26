from __future__ import annotations

import json
from pathlib import Path

from scripts.run_node_model_benchmark import main
from tests.test_model_benchmark_executor import _payload_for_case, _replay_record
from evaluation.model_benchmark.dataset import load_node_benchmark_cases
from evaluation.model_benchmark.models import ModelBenchmarkConfig, ModelTier


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "data/evaluation/model_benchmark/node_cases.jsonl"


def _write_config(path: Path, config_id: str = "replay-fast") -> None:
    config = ModelBenchmarkConfig(
        config_id=config_id,
        provider="replay",
        model="replay-model",
        tier=ModelTier.fast,
        temperature=0,
        max_tokens=2048,
    )
    path.write_text(json.dumps([config.model_dump(mode="json")], ensure_ascii=False), encoding="utf-8")


def _write_replay(path: Path, case, config_id: str = "replay-fast") -> None:
    record = _replay_record(case, _payload_for_case(case)).model_copy(
        update={"model_config_id": config_id}
    )
    path.write_text(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n", encoding="utf-8")


def test_cli_plan_does_not_create_runtime(tmp_path: Path, capsys) -> None:
    output_root = tmp_path / "runs"

    exit_code = main(["--cases-file", str(CASES_PATH), "--output-root", str(output_root)])

    assert exit_code == 0
    assert "Node Model Benchmark Plan" in capsys.readouterr().out
    assert not output_root.exists()


def test_cli_validate_does_not_create_runtime(tmp_path: Path, capsys) -> None:
    output_root = tmp_path / "runs"

    exit_code = main(
        ["--cases-file", str(CASES_PATH), "--output-root", str(output_root), "--validate"]
    )

    assert exit_code == 0
    assert "Benchmark dataset validation passed." in capsys.readouterr().out
    assert not output_root.exists()


def test_cli_replay_creates_runtime_only_in_output_root(tmp_path: Path, capsys) -> None:
    case = load_node_benchmark_cases(CASES_PATH)[0]
    configs_path = tmp_path / "configs.json"
    replay_path = tmp_path / "replay.jsonl"
    output_root = tmp_path / "runs"
    _write_config(configs_path)
    _write_replay(replay_path, case)

    exit_code = main(
        [
            "--cases-file",
            str(CASES_PATH),
            "--output-root",
            str(output_root),
            "--configs",
            str(configs_path),
            "--case",
            case.benchmark_case_id,
            "--replay",
            str(replay_path),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Run ID:" in output
    assert "Completed runs: 1" in output
    assert output_root.exists()
    assert len(list(output_root.iterdir())) == 1


def test_cli_replay_requires_configs(tmp_path: Path, capsys) -> None:
    exit_code = main(
        [
            "--cases-file",
            str(CASES_PATH),
            "--output-root",
            str(tmp_path / "runs"),
            "--replay",
            str(tmp_path / "missing.jsonl"),
        ]
    )

    assert exit_code == 1
    assert "--configs is required" in capsys.readouterr().err
