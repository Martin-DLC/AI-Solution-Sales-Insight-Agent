from __future__ import annotations

from decimal import Decimal
import json
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


def _live_config(config_id: str = "ds-v4-flash-non-thinking") -> ModelBenchmarkConfig:
    return ModelBenchmarkConfig(
        config_id=config_id,
        provider="deepseek",
        model="deepseek-v4-flash",
        tier=ModelTier.fast,
        thinking_mode="disabled",
        temperature=0,
        max_tokens=8192,
        pricing_profile_id="flash-v4-2026-06",
        api_key_env="LLM_API_KEY",
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


def test_runner_live_stops_when_budget_is_reached(tmp_path: Path) -> None:
    cases = _selected_cases()
    config = _live_config()
    records = _records_for(cases, config.config_id)
    runner = NodeModelBenchmarkRunner(
        cases=cases,
        model_configs=[config],
        client_factory=create_replay_client_factory(replay_records=records),
        output_root=tmp_path,
    )

    report = runner.run(
        execution_mode="live",
        max_budget_cny=Decimal("0.000020"),
        live_confirmed=True,
    )

    assert report.manifest.completed_run_count == 1
    assert report.manifest.stopped_by_budget is True
    assert report.manifest.estimated_cost_cny is not None


def test_runner_live_stops_after_unknown_cost_limit(tmp_path: Path) -> None:
    cases = _selected_cases()
    configs = [_live_config("ds-v4-flash-non-thinking"), _live_config("ds-v4-flash-non-thinking-2")]
    records = []
    for config in configs:
        for case in cases:
            record = _replay_record(case, _payload_for_case(case)).model_copy(
                update={
                    "model_config_id": config.config_id,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": None,
                }
            )
            records.append(record)
    runner = NodeModelBenchmarkRunner(
        cases=cases,
        model_configs=configs,
        client_factory=create_replay_client_factory(replay_records=records),
        output_root=tmp_path,
    )

    report = runner.run(
        execution_mode="live",
        max_budget_cny=Decimal("1"),
        live_confirmed=True,
        max_unknown_cost_runs=1,
    )

    assert report.manifest.completed_run_count == 2
    assert report.manifest.unknown_cost_run_count == 2
    assert report.manifest.stopped_by_budget is False
    assert report.manifest.stop_reason == "unknown_cost_limit"


def test_runner_live_request_errors_still_flush_case_results_and_stop_before_third_call(
    tmp_path: Path,
) -> None:
    cases = [next(case for case in _selected_cases() if case.node_name is WorkflowNodeName.fact_extraction)]
    configs = [
        _live_config("ds-v4-flash-non-thinking"),
        _live_config("ds-v4-flash-non-thinking-2"),
        _live_config("ds-v4-flash-non-thinking-3"),
    ]
    runner = NodeModelBenchmarkRunner(
        cases=cases,
        model_configs=configs,
        client_factory=create_replay_client_factory(replay_records=[]),
        output_root=tmp_path,
    )

    report = runner.run(
        execution_mode="live",
        max_budget_cny=Decimal("1"),
        live_confirmed=True,
        max_unknown_cost_runs=1,
    )

    root = Path(report.manifest.output_directory)
    case_results_path = root / "case_results.jsonl"
    lines = [line for line in case_results_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    parsed_lines = [json.loads(line) for line in lines]

    assert report.manifest.completed_run_count == 2
    assert report.manifest.request_error_count == 2
    assert report.manifest.unknown_cost_run_count == 2
    assert report.manifest.stopped_by_budget is False
    assert report.manifest.stop_reason == "unknown_cost_limit"
    assert case_results_path.exists()
    assert len(lines) == 2
    assert all(line["status"] == "request_error" for line in parsed_lines)
    assert all(line["error_type"] == "request_error" for line in parsed_lines)
    assert all(line["error_message"] for line in parsed_lines)
    assert "LLM_API_KEY" not in case_results_path.read_text(encoding="utf-8")

    first_case_dir = (
        root / "cases" / cases[0].benchmark_case_id / configs[0].config_id / WorkflowNodeName.fact_extraction.value
    )
    assert first_case_dir.joinpath("run_result.json").exists()
    assert first_case_dir.joinpath("observation.json").exists()
    assert first_case_dir.joinpath("assertion_results.json").exists()
    assert first_case_dir.joinpath("llm_calls/01_fact_extraction/metadata.json").exists()
    assert not first_case_dir.joinpath("llm_calls/01_fact_extraction/messages.json").exists()
    assert not first_case_dir.joinpath("llm_calls/01_fact_extraction/raw_response.txt").exists()


def test_runner_preserves_safe_request_error_type_in_run_results(tmp_path: Path) -> None:
    case = next(case for case in _selected_cases() if case.node_name is WorkflowNodeName.fact_extraction)
    config = _live_config()
    record = _replay_record(case, None).model_copy(
        update={
            "model_config_id": config.config_id,
            "request_error": True,
            "error_type": "provider_unsupported_parameter",
            "error_message": "Provider rejected an unsupported request parameter.",
        }
    )
    runner = NodeModelBenchmarkRunner(
        cases=[case],
        model_configs=[config],
        client_factory=create_replay_client_factory(replay_records=[record]),
        output_root=tmp_path,
    )

    report = runner.run(
        execution_mode="live",
        max_budget_cny=Decimal("1"),
        live_confirmed=True,
    )

    assert report.run_results[0].error_type == "provider_unsupported_parameter"
    assert report.run_results[0].error_message == "Provider rejected an unsupported request parameter."
