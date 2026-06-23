from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent.workflow_c import FakeWorkflowLLMClient
from agent.workflow_c.real_llm import WorkflowLLMCallRecord
from agent.workflow_c.runtime import (
    ArchitectureCRunError,
    ArchitectureCRunner,
    WorkflowCRunStatus,
)
from agent.workflow_c.state import WorkflowNodeName
from dataio.runtime_cases import load_runtime_cases
from llm import LLMConfig, LLMMessage, LLMUsage


class RecordingWorkflowLLM:
    def __init__(self, *, api_key: str = "sk-test-secret") -> None:
        self.delegate = FakeWorkflowLLMClient.with_default_batch4b_responses()
        self.config = LLMConfig(
            api_key=api_key,
            base_url="https://api.example.com",
            model="configured-model",
        )
        self.call_records: list[WorkflowLLMCallRecord] = []

    def complete_json_for_node(self, node_name: WorkflowNodeName, messages: list[LLMMessage]):
        sequence = len(self.call_records) + 1
        started_at = datetime.now(UTC)
        result = self.delegate.complete_json_for_node(node_name, messages)
        completed_at = datetime.now(UTC)
        self.call_records.append(
            WorkflowLLMCallRecord(
                sequence=sequence,
                node_name=node_name,
                status="success",
                started_at=started_at,
                completed_at=completed_at,
                latency_ms=result.latency_ms,
                configured_model=self.config.model,
                response_model=result.model,
                usage=result.usage,
                messages=[{"role": message.role.value, "content": message.content} for message in messages],
                raw_content=result.content,
                parsed_json=result.parsed_json,
            )
        )
        return result


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def run_success(tmp_path: Path):
    runner = ArchitectureCRunner(RecordingWorkflowLLM(), output_root=tmp_path)
    return runner.run_case(dev_01_case())


def test_success_run_creates_independent_directory(tmp_path: Path) -> None:
    result = run_success(tmp_path)

    assert result.output_directory.is_dir()


def test_success_run_saves_core_artifacts(tmp_path: Path) -> None:
    result = run_success(tmp_path)

    for name in [
        "input_case.json",
        "workflow_state.json",
        "report_draft.json",
        "final_validation_result.json",
        "run_metadata.json",
    ]:
        assert (result.output_directory / name).exists()


def test_success_run_saves_final_report_when_available(tmp_path: Path) -> None:
    result = run_success(tmp_path)

    assert result.snapshot is not None
    assert result.snapshot.final_report is not None
    assert (result.output_directory / "final_report.json").exists()


def test_success_run_saves_llm_call_directories(tmp_path: Path) -> None:
    result = run_success(tmp_path)

    calls_root = result.output_directory / "llm_calls"
    assert calls_root.is_dir()
    assert (calls_root / "01_fact_extraction" / "metadata.json").exists()
    assert (calls_root / "01_fact_extraction" / "messages.json").exists()
    assert (calls_root / "01_fact_extraction" / "raw_response.txt").exists()
    assert (calls_root / "01_fact_extraction" / "parsed_response.json").exists()


def test_llm_call_order_and_node_names_are_recorded(tmp_path: Path) -> None:
    result = run_success(tmp_path)

    assert [record.sequence for record in result.call_records] == list(range(1, 12))
    assert result.call_records[0].node_name is WorkflowNodeName.fact_extraction
    assert result.call_records[-1].node_name is WorkflowNodeName.next_best_action


def test_metadata_sums_token_usage(tmp_path: Path) -> None:
    result = run_success(tmp_path)

    assert result.metadata.llm_call_count == 11
    assert result.metadata.prompt_tokens == 33
    assert result.metadata.completion_tokens == 44
    assert result.metadata.total_tokens == 77


def test_metadata_records_final_validation_state(tmp_path: Path) -> None:
    result = run_success(tmp_path)

    assert result.metadata.final_validation_passed is True
    assert result.metadata.final_report_available is True
    assert result.metadata.human_review_required is True
    assert result.metadata.status is WorkflowCRunStatus.success


def test_failure_still_saves_metadata_without_final_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(case, services):
        raise RuntimeError("runtime failed")

    monkeypatch.setattr("agent.workflow_c.runtime.run_architecture_c_skeleton", boom)
    runner = ArchitectureCRunner(RecordingWorkflowLLM(), output_root=tmp_path)

    with pytest.raises(ArchitectureCRunError) as exc_info:
        runner.run_case(dev_01_case())

    output_directory = exc_info.value.result.output_directory
    metadata = json.loads((output_directory / "run_metadata.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "failed"
    assert metadata["error_type"] == "RuntimeError"
    assert not (output_directory / "final_report.json").exists()


def test_custom_output_root_is_used(tmp_path: Path) -> None:
    result = run_success(tmp_path / "custom-root")

    assert "custom-root" in str(result.output_directory)


def test_two_runs_have_different_run_ids(tmp_path: Path) -> None:
    first = run_success(tmp_path)
    second = run_success(tmp_path)

    assert first.metadata.run_id != second.metadata.run_id


def test_artifacts_do_not_contain_test_api_key(tmp_path: Path) -> None:
    result = run_success(tmp_path)

    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in result.output_directory.rglob("*")
        if path.is_file()
    )
    assert "sk-test-secret" not in combined


def test_runtime_does_not_read_reference_pack() -> None:
    source = Path("agent/workflow_c/runtime.py").read_text(encoding="utf-8")

    assert "load_reference_packs" not in source
    assert "development_reference" not in source
