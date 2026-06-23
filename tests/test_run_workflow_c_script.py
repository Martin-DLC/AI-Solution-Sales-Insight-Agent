from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent.workflow_c.runtime import (
    ArchitectureCRunError,
    ArchitectureCRunResult,
    WorkflowCRunMetadata,
    WorkflowCRunStatus,
)
from scripts import run_workflow_c


def success_metadata(output_directory: Path) -> WorkflowCRunMetadata:
    now = datetime.now(UTC)
    return WorkflowCRunMetadata(
        run_id="C-DEV-01-20260624T000000Z-abcdef12",
        architecture="C",
        workflow_version="c_skeleton_v1",
        case_id="DEV-01",
        configured_model="fake-model",
        response_models=["fake-response-model"],
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
        prompt_tokens=1,
        completion_tokens=2,
        total_tokens=3,
        output_directory=str(output_directory),
        git_commit="abc123",
    )


def failed_metadata(output_directory: Path) -> WorkflowCRunMetadata:
    now = datetime.now(UTC)
    return WorkflowCRunMetadata(
        run_id="C-DEV-01-20260624T000000Z-abcdef12",
        architecture="C",
        workflow_version="c_skeleton_v1",
        case_id="DEV-01",
        configured_model="fake-model",
        response_models=[],
        started_at=now,
        completed_at=now,
        latency_ms=12,
        status=WorkflowCRunStatus.failed,
        workflow_status=None,
        final_validation_passed=None,
        final_report_available=False,
        human_review_required=True,
        failure_count=0,
        warning_count=0,
        llm_call_count=0,
        output_directory=str(output_directory),
        git_commit="abc123",
        error_type="RuntimeError",
        error_message="request failed",
    )


def test_dry_run_returns_zero() -> None:
    assert run_workflow_c.main(["--case", "DEV-01"]) == 0


def test_dry_run_does_not_create_llm_client(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_create_llm_client(config):
        nonlocal called
        called = True
        return object()

    monkeypatch.setattr(run_workflow_c, "create_llm_client", fake_create_llm_client)

    assert run_workflow_c.main(["--case", "DEV-01"]) == 0
    assert called is False


def test_dry_run_does_not_read_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        run_workflow_c.LLMConfig,
        "from_env",
        lambda: (_ for _ in ()).throw(AssertionError("from_env should not run")),
    )

    assert run_workflow_c.main(["--case", "DEV-01"]) == 0


def test_dry_run_does_not_create_runtime_directory(tmp_path: Path) -> None:
    output_root = tmp_path / "runs"

    result = run_workflow_c.main(["--case", "DEV-01", "--output-root", str(output_root)])

    assert result == 0
    assert not output_root.exists()


def test_dry_run_outputs_case_and_workflow_version(capsys) -> None:
    run_workflow_c.main(["--case", "DEV-01"])

    output = capsys.readouterr().out
    assert "Case ID: DEV-01" in output
    assert "Workflow version: c_skeleton_v1" in output
    assert "Live model call is disabled" in output


def test_live_success_path_uses_fake_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRunner:
        def __init__(self, workflow_llm, *, output_root):
            self.output_root = output_root

        def run_case(self, case):
            metadata = success_metadata(tmp_path / "run")
            return ArchitectureCRunResult(
                metadata=metadata,
                snapshot=None,
                output_directory=tmp_path / "run",
                call_records=[],
            )

    monkeypatch.setattr(run_workflow_c.LLMConfig, "from_env", lambda: object())
    monkeypatch.setattr(run_workflow_c, "create_llm_client", lambda config: object())
    monkeypatch.setattr(run_workflow_c, "RealWorkflowLLMClient", lambda llm_client, config: object())
    monkeypatch.setattr(run_workflow_c, "ArchitectureCRunner", FakeRunner)

    result = run_workflow_c.main(["--case", "DEV-01", "--live", "--output-root", str(tmp_path)])

    assert result == 0


def test_live_failure_returns_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRunner:
        def __init__(self, workflow_llm, *, output_root):
            self.output_root = output_root

        def run_case(self, case):
            metadata = failed_metadata(tmp_path / "run")
            result = ArchitectureCRunResult(
                metadata=metadata,
                snapshot=None,
                output_directory=tmp_path / "run",
                call_records=[],
            )
            raise ArchitectureCRunError(result)

    monkeypatch.setattr(run_workflow_c.LLMConfig, "from_env", lambda: object())
    monkeypatch.setattr(run_workflow_c, "create_llm_client", lambda config: object())
    monkeypatch.setattr(run_workflow_c, "RealWorkflowLLMClient", lambda llm_client, config: object())
    monkeypatch.setattr(run_workflow_c, "ArchitectureCRunner", FakeRunner)

    result = run_workflow_c.main(["--case", "DEV-01", "--live", "--output-root", str(tmp_path)])

    assert result == 1


def test_cli_output_does_not_contain_full_customer_content_or_test_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    class FakeRunner:
        def __init__(self, workflow_llm, *, output_root):
            pass

        def run_case(self, case):
            return ArchitectureCRunResult(
                metadata=success_metadata(tmp_path / "run"),
                snapshot=None,
                output_directory=tmp_path / "run",
                call_records=[],
            )

    monkeypatch.setattr(run_workflow_c.LLMConfig, "from_env", lambda: object())
    monkeypatch.setattr(run_workflow_c, "create_llm_client", lambda config: object())
    monkeypatch.setattr(run_workflow_c, "RealWorkflowLLMClient", lambda llm_client, config: object())
    monkeypatch.setattr(run_workflow_c, "ArchitectureCRunner", FakeRunner)

    run_workflow_c.main(["--case", "DEV-01", "--live", "--output-root", str(tmp_path)])
    output = capsys.readouterr()

    assert "sk-test-secret" not in output.out
    assert "sk-test-secret" not in output.err
    assert "客户资料" not in output.out
    assert "会议纪要" not in output.out


def test_cli_does_not_import_or_read_reference_pack() -> None:
    source = Path("scripts/run_workflow_c.py").read_text(encoding="utf-8")

    assert "load_reference_packs" not in source
    assert "development_reference" not in source
