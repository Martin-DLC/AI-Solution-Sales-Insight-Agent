from __future__ import annotations

from pathlib import Path

from agent.workflow_c.state import WorkflowNodeName
from evaluation.model_benchmark.clients import ReplayBenchmarkRecord, create_replay_client_factory
from evaluation.model_benchmark.dataset import load_node_benchmark_cases
from evaluation.model_benchmark.models import ModelBenchmarkConfig, ModelTier
from evaluation.model_benchmark.runner import NodeModelBenchmarkRunner

from tests.test_model_benchmark_executor import _payload_for_case, _replay_record


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "data/evaluation/model_benchmark/node_cases.jsonl"


def _config(config_id: str = "replay-fast") -> ModelBenchmarkConfig:
    return ModelBenchmarkConfig(
        config_id=config_id,
        provider="replay",
        model=f"{config_id}-model",
        tier=ModelTier.fast,
        temperature=0,
        max_tokens=2048,
        enabled=True,
    )


def _selected_cases():
    cases = load_node_benchmark_cases(CASES_PATH)
    return [
        next(case for case in cases if case.node_name is WorkflowNodeName.fact_extraction),
        next(case for case in cases if case.node_name is WorkflowNodeName.information_gap),
    ]


def _records_for(cases, config_id: str = "replay-fast") -> list[ReplayBenchmarkRecord]:
    records = []
    for case in cases:
        record = _replay_record(case, _payload_for_case(case))
        records.append(record.model_copy(update={"model_config_id": config_id}))
    return records


def test_runner_filters_cases_and_models_and_writes_report(tmp_path: Path) -> None:
    cases = _selected_cases()
    configs = [_config("replay-fast"), _config("replay-balanced")]
    records = _records_for(cases, "replay-fast") + _records_for(cases, "replay-balanced")
    runner = NodeModelBenchmarkRunner(
        cases=cases,
        model_configs=configs,
        client_factory=create_replay_client_factory(replay_records=records),
        output_root=tmp_path,
    )

    report = runner.run(
        case_ids=[cases[0].benchmark_case_id],
        model_config_ids=["replay-balanced"],
    )

    assert report.manifest.planned_run_count == 1
    assert report.manifest.completed_run_count == 1
    assert report.manifest.passed_count == 1
    assert Path(report.manifest.output_directory).is_relative_to(tmp_path)
    assert Path(report.manifest.output_directory).joinpath("run_manifest.json").exists()


def test_runner_continues_after_request_error_by_default(tmp_path: Path) -> None:
    cases = _selected_cases()
    config = _config()
    records = [_records_for([cases[1]])[0]]
    runner = NodeModelBenchmarkRunner(
        cases=cases,
        model_configs=[config],
        client_factory=create_replay_client_factory(replay_records=records),
        output_root=tmp_path,
    )

    report = runner.run()

    assert report.manifest.completed_run_count == 2
    assert report.manifest.request_error_count == 1
    assert report.manifest.passed_count == 1


def test_runner_fail_fast_stops_after_first_failed_run(tmp_path: Path) -> None:
    cases = _selected_cases()
    config = _config()
    runner = NodeModelBenchmarkRunner(
        cases=cases,
        model_configs=[config],
        client_factory=create_replay_client_factory(replay_records=[]),
        output_root=tmp_path,
    )

    report = runner.run(fail_fast=True)

    assert report.manifest.completed_run_count == 1
    assert report.manifest.request_error_count == 1


def test_runner_plan_and_validate_do_not_create_runtime(tmp_path: Path) -> None:
    cases = _selected_cases()
    runner = NodeModelBenchmarkRunner(
        cases=cases,
        model_configs=[],
        client_factory=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no client")),
        output_root=tmp_path,
    )

    plan = runner.plan()
    assert plan.selected_case_count == 2
    assert plan.planned_run_count == 0
    assert not any(tmp_path.iterdir())
