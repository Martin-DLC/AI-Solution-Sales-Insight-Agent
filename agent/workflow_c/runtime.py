from __future__ import annotations

import json
import secrets
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from agent.workflow_c.failures import redact_secrets
from agent.workflow_c.graph import run_architecture_c_skeleton
from agent.workflow_c.real_llm import RealWorkflowLLMClient, WorkflowLLMCallRecord
from agent.workflow_c.services import WorkflowServices
from agent.workflow_c.state import ArchitectureCStateSnapshot
from llm import LLMUsage
from schemas.common_models import StrictBaseModel
from schemas.input_models import EvaluationCaseInput


class WorkflowCRunStatus(str, Enum):
    success = "success"
    failed = "failed"


class WorkflowCRunMetadata(StrictBaseModel):
    run_id: str
    architecture: Literal["C"]
    workflow_version: str
    case_id: str
    configured_model: str
    response_models: list[str] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime
    latency_ms: int
    status: WorkflowCRunStatus
    workflow_status: str | None = None
    final_validation_passed: bool | None = None
    final_report_available: bool
    human_review_required: bool
    failure_count: int
    warning_count: int
    llm_call_count: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    output_directory: str
    git_commit: str | None = None
    error_type: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_metadata(self) -> "WorkflowCRunMetadata":
        if self.completed_at < self.started_at:
            raise ValueError("completed_at cannot be earlier than started_at.")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must be greater than or equal to 0.")
        if self.llm_call_count < 0:
            raise ValueError("llm_call_count must be greater than or equal to 0.")
        if self.status is WorkflowCRunStatus.success:
            if self.error_type is not None or self.error_message is not None:
                raise ValueError("Successful runs must not contain error fields.")
        if self.status is WorkflowCRunStatus.failed:
            if not self.error_type or not self.error_message:
                raise ValueError("Failed runs must include error_type and error_message.")
        return self


@dataclass(frozen=True)
class ArchitectureCRunResult:
    metadata: WorkflowCRunMetadata
    snapshot: ArchitectureCStateSnapshot | None
    output_directory: Path
    call_records: list[WorkflowLLMCallRecord]


class ArchitectureCRunError(Exception):
    def __init__(self, result: ArchitectureCRunResult) -> None:
        self.result = result
        super().__init__(result.metadata.error_message or result.metadata.error_type or "Workflow C run failed.")


class ArchitectureCRunner:
    def __init__(
        self,
        workflow_llm: RealWorkflowLLMClient,
        *,
        output_root: str | Path = "data/runtime/workflow_c_runs",
    ) -> None:
        self.workflow_llm = workflow_llm
        self.output_root = Path(output_root)

    def run_case(self, case: EvaluationCaseInput) -> ArchitectureCRunResult:
        started_at = datetime.now(UTC)
        run_id = self._generate_run_id(case.case_id, started_at)
        output_directory = self.output_root / run_id
        output_directory.mkdir(parents=True, exist_ok=False)
        _write_json(output_directory / "input_case.json", case.model_dump(mode="json"))
        git_commit = _read_git_commit()

        snapshot: ArchitectureCStateSnapshot | None = None
        try:
            snapshot = run_architecture_c_skeleton(
                case,
                WorkflowServices(llm=self.workflow_llm),
            )
        except Exception as exc:
            completed_at = datetime.now(UTC)
            call_records = self._call_records()
            self._write_llm_calls(output_directory, call_records)
            metadata = self._build_metadata(
                run_id=run_id,
                case=case,
                started_at=started_at,
                completed_at=completed_at,
                output_directory=output_directory,
                snapshot=None,
                call_records=call_records,
                status=WorkflowCRunStatus.failed,
                git_commit=git_commit,
                error_type=exc.__class__.__name__,
                error_message=_safe_error_message(exc),
            )
            _write_json(output_directory / "run_metadata.json", metadata.model_dump(mode="json"))
            result = ArchitectureCRunResult(
                metadata=metadata,
                snapshot=None,
                output_directory=output_directory,
                call_records=call_records,
            )
            raise ArchitectureCRunError(result) from exc

        completed_at = datetime.now(UTC)
        call_records = self._call_records()
        self._write_snapshot_outputs(output_directory, snapshot)
        self._write_llm_calls(output_directory, call_records)
        metadata = self._build_metadata(
            run_id=run_id,
            case=case,
            started_at=started_at,
            completed_at=completed_at,
            output_directory=output_directory,
            snapshot=snapshot,
            call_records=call_records,
            status=WorkflowCRunStatus.success,
            git_commit=git_commit,
            error_type=None,
            error_message=None,
        )
        _write_json(output_directory / "run_metadata.json", metadata.model_dump(mode="json"))
        return ArchitectureCRunResult(
            metadata=metadata,
            snapshot=snapshot,
            output_directory=output_directory,
            call_records=call_records,
        )

    def _call_records(self) -> list[WorkflowLLMCallRecord]:
        return list(getattr(self.workflow_llm, "call_records", []))

    def _write_snapshot_outputs(
        self,
        output_directory: Path,
        snapshot: ArchitectureCStateSnapshot,
    ) -> None:
        _write_json(output_directory / "workflow_state.json", snapshot.model_dump(mode="json"))
        if snapshot.report_draft is not None:
            _write_json(output_directory / "report_draft.json", snapshot.report_draft.model_dump(mode="json"))
        if snapshot.final_validation_result is not None:
            _write_json(
                output_directory / "final_validation_result.json",
                snapshot.final_validation_result.model_dump(mode="json"),
            )
        if snapshot.final_report is not None:
            _write_json(output_directory / "final_report.json", snapshot.final_report.model_dump(mode="json"))

    def _write_llm_calls(
        self,
        output_directory: Path,
        call_records: list[WorkflowLLMCallRecord],
    ) -> None:
        if not call_records:
            return
        root = output_directory / "llm_calls"
        for record in call_records:
            call_dir = root / f"{record.sequence:02d}_{record.node_name.value}"
            call_dir.mkdir(parents=True, exist_ok=False)
            metadata = record.model_dump(mode="json", exclude={"messages", "raw_content", "parsed_json"})
            _write_json(call_dir / "metadata.json", metadata)
            _write_json(call_dir / "messages.json", record.messages)
            if record.raw_content is not None:
                (call_dir / "raw_response.txt").write_text(record.raw_content, encoding="utf-8")
            if record.parsed_json is not None:
                _write_json(call_dir / "parsed_response.json", record.parsed_json)

    def _build_metadata(
        self,
        *,
        run_id: str,
        case: EvaluationCaseInput,
        started_at: datetime,
        completed_at: datetime,
        output_directory: Path,
        snapshot: ArchitectureCStateSnapshot | None,
        call_records: list[WorkflowLLMCallRecord],
        status: WorkflowCRunStatus,
        git_commit: str | None,
        error_type: str | None,
        error_message: str | None,
    ) -> WorkflowCRunMetadata:
        usage = _sum_usage(record.usage for record in call_records)
        response_models = [
            model
            for model in (record.response_model for record in call_records)
            if model is not None
        ]
        final_validation = snapshot.final_validation_result if snapshot is not None else None
        return WorkflowCRunMetadata(
            run_id=run_id,
            architecture="C",
            workflow_version=snapshot.workflow_version if snapshot is not None else "c_skeleton_v1",
            case_id=case.case_id,
            configured_model=_configured_model(self.workflow_llm),
            response_models=response_models,
            started_at=started_at,
            completed_at=completed_at,
            latency_ms=max(0, int((completed_at - started_at).total_seconds() * 1000)),
            status=status,
            workflow_status=snapshot.workflow_status.value if snapshot is not None else None,
            final_validation_passed=final_validation.passed if final_validation is not None else None,
            final_report_available=snapshot.final_report is not None if snapshot is not None else False,
            human_review_required=snapshot.human_review_required if snapshot is not None else True,
            failure_count=len(snapshot.failures) if snapshot is not None else 0,
            warning_count=len(snapshot.warnings) if snapshot is not None else 0,
            llm_call_count=len(call_records),
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            output_directory=str(output_directory),
            git_commit=git_commit,
            error_type=error_type,
            error_message=error_message,
        )

    @staticmethod
    def _generate_run_id(case_id: str, started_at: datetime) -> str:
        timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
        return f"C-{case_id}-{timestamp}-{secrets.token_hex(4)}"


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    commit = result.stdout.strip()
    return commit or None


def _safe_error_message(error: Exception) -> str:
    message = redact_secrets(str(error) or error.__class__.__name__)
    if len(message) > 1000:
        return f"{message[:997]}..."
    return message


def _configured_model(workflow_llm: object) -> str:
    config = getattr(workflow_llm, "config", None)
    model = getattr(config, "model", None)
    return model if isinstance(model, str) and model else "unknown"


def _sum_usage(usages) -> LLMUsage:
    usage_items = list(usages)
    prompt = _sum_optional(value.prompt_tokens for value in usage_items)
    completion = _sum_optional(value.completion_tokens for value in usage_items)
    total = _sum_optional(value.total_tokens for value in usage_items)
    return LLMUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
    )


def _sum_optional(values) -> int | None:
    known = [value for value in values if value is not None]
    if not known:
        return None
    return sum(known)
