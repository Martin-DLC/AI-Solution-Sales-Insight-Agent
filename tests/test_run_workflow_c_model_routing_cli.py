from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent.workflow_c.runtime import ArchitectureCRunResult, WorkflowCRunMetadata, WorkflowCRunStatus
from scripts import run_workflow_c


def _success_metadata(output_directory: Path) -> WorkflowCRunMetadata:
    now = datetime.now(UTC)
    return WorkflowCRunMetadata(
        run_id="C-DEV-01-20260628T000000Z-routing",
        architecture="C",
        workflow_version="c_skeleton_v1",
        case_id="DEV-01",
        configured_model="default-model",
        response_models=["fallback-model"],
        started_at=now,
        completed_at=now,
        latency_ms=12,
        status=WorkflowCRunStatus.success,
        workflow_status="awaiting_human_review",
        final_validation_passed=True,
        final_report_available=True,
        human_review_required=True,
        failure_count=0,
        warning_count=0,
        llm_call_count=11,
        prompt_tokens=11,
        completion_tokens=22,
        total_tokens=33,
        output_directory=str(output_directory),
        git_commit="abc123",
        model_routing_enabled=True,
        routing_policy_version="v1",
        routing_matrix_file="data/evaluation/model_benchmark/node_model_routing_matrix.v1.json",
        model_configs_file="data/evaluation/model_benchmark/model_configs.deepseek_v4.json",
        routed_nodes=[
            "fact_extraction",
            "underlying_pain",
            "information_gap",
            "solution_recommendation",
        ],
        unavailable_routed_nodes=[],
        fallback_call_count=1,
        models_used=["fallback-model", "default-model"],
    )


def test_dry_run_with_model_routing_prints_safe_plan(
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        run_workflow_c.LLMConfig,
        "from_env",
        lambda: (_ for _ in ()).throw(AssertionError("from_env should not run")),
    )

    result = run_workflow_c.main(["--case", "DEV-01", "--model-routing"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Model routing: enabled" in output
    assert "fact_extraction:" in output
    assert "unbenchmarked nodes:" in output


def test_dry_run_with_model_routing_does_not_create_runtime_directory(tmp_path: Path) -> None:
    output_root = tmp_path / "runs"

    result = run_workflow_c.main(
        ["--case", "DEV-01", "--model-routing", "--output-root", str(output_root)]
    )

    assert result == 0
    assert not output_root.exists()


def test_live_without_model_routing_keeps_single_model_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[str] = []

    class FakeRunner:
        def __init__(self, workflow_llm, *, output_root):
            created.append(type(workflow_llm).__name__)

        def run_case(self, case):
            return ArchitectureCRunResult(
                metadata=_success_metadata(tmp_path / "run"),
                snapshot=None,
                output_directory=tmp_path / "run",
                call_records=[],
            )

    class FakeRealWorkflowLLMClient:
        def __init__(self, llm_client, config):
            pass

    monkeypatch.setattr(run_workflow_c.LLMConfig, "from_env", lambda: object())
    monkeypatch.setattr(run_workflow_c, "create_llm_client", lambda config: object())
    monkeypatch.setattr(run_workflow_c, "RealWorkflowLLMClient", FakeRealWorkflowLLMClient)
    monkeypatch.setattr(run_workflow_c, "ArchitectureCRunner", FakeRunner)

    result = run_workflow_c.main(["--case", "DEV-01", "--live", "--output-root", str(tmp_path)])

    assert result == 0
    assert created == ["FakeRealWorkflowLLMClient"]


def test_live_with_model_routing_uses_routed_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[str] = []

    class FakeRunner:
        def __init__(self, workflow_llm, *, output_root):
            created.append(type(workflow_llm).__name__)

        def run_case(self, case):
            return ArchitectureCRunResult(
                metadata=_success_metadata(tmp_path / "run"),
                snapshot=None,
                output_directory=tmp_path / "run",
                call_records=[],
            )

    monkeypatch.setattr(run_workflow_c.LLMConfig, "from_env", lambda: object())
    monkeypatch.setattr(run_workflow_c, "create_llm_client", lambda config: object())
    monkeypatch.setattr(run_workflow_c, "ArchitectureCRunner", FakeRunner)

    result = run_workflow_c.main(
        [
            "--case",
            "DEV-01",
            "--live",
            "--model-routing",
            "--output-root",
            str(tmp_path),
        ]
    )

    assert result == 0
    assert created == ["RoutedWorkflowLLMClient"]


def test_missing_routing_matrix_fails_before_request(
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        run_workflow_c.LLMConfig,
        "from_env",
        lambda: (_ for _ in ()).throw(AssertionError("from_env should not run")),
    )

    result = run_workflow_c.main(
        [
            "--case",
            "DEV-01",
            "--model-routing",
            "--routing-matrix",
            "data/evaluation/model_benchmark/missing-routing-matrix.json",
        ]
    )

    output = capsys.readouterr()
    assert result == 1
    assert "Model routing setup failed" in output.err
    assert "sk-" not in output.err
