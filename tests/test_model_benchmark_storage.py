from __future__ import annotations

import json
from pathlib import Path

from agent.workflow_c.state import WorkflowNodeName
from evaluation.model_benchmark.clients import ReplayBenchmarkRecord, create_replay_client_factory
from evaluation.model_benchmark.executor import NodeModelBenchmarkExecutor
from evaluation.model_benchmark.models import ModelBenchmarkConfig, ModelTier
from evaluation.model_benchmark.dataset import load_node_benchmark_cases
from evaluation.model_benchmark.storage import write_benchmark_case_artifact

from tests.test_model_benchmark_executor import _payload_for_case, _replay_record


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _config() -> ModelBenchmarkConfig:
    return ModelBenchmarkConfig(
        config_id="replay-fast",
        provider="replay",
        model="replay-model",
        tier=ModelTier.fast,
        temperature=0,
        max_tokens=2048,
    )


def test_storage_writes_case_artifact_and_call_files(tmp_path: Path) -> None:
    case = next(
        case
        for case in load_node_benchmark_cases(PROJECT_ROOT / "data/evaluation/model_benchmark/node_cases.jsonl")
        if case.node_name is WorkflowNodeName.fact_extraction
    )
    config = _config()
    factory = create_replay_client_factory(
        replay_records=[_replay_record(case, _payload_for_case(case))]
    )
    execution = NodeModelBenchmarkExecutor().execute_case(
        case,
        config,
        client=factory(config, case),
        run_id="run-storage",
    )

    artifact_dir = write_benchmark_case_artifact(
        execution.artifact,
        artifact_dir=tmp_path / "case-artifact",
        call_records=execution.call_records,
    )

    assert artifact_dir.joinpath("artifact.json").exists()
    assert artifact_dir.joinpath("observation.json").exists()
    assert artifact_dir.joinpath("assertion_results.json").exists()
    assert artifact_dir.joinpath("run_result.json").exists()
    call_dir = artifact_dir / "llm_calls/01_fact_extraction"
    assert call_dir.joinpath("metadata.json").exists()
    assert call_dir.joinpath("messages.json").exists()
    assert call_dir.joinpath("raw_response.txt").exists()
    assert call_dir.joinpath("parsed_response.json").exists()
    result = json.loads(artifact_dir.joinpath("run_result.json").read_text(encoding="utf-8"))
    assert result["benchmark_case_id"] == case.benchmark_case_id
    assert result["status"] == "passed"
