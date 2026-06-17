from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from evaluation.baselines import (
    BaselineArchitecture,
    BaselineRunRecord,
    BaselineRunStatus,
    StructuredBaselineRunRecord,
)
from llm.models import LLMUsage


def valid_record_payload(**overrides):
    started_at = datetime.now(UTC)
    payload = {
        "run_id": "A-DEV-01-20260101T000000Z-abcdef12",
        "architecture": BaselineArchitecture.A,
        "case_id": "DEV-01",
        "prompt_version": "baseline_a_v1",
        "prompt_sha256": "a" * 64,
        "model": "model-a",
        "provider": "openai_compatible",
        "started_at": started_at,
        "completed_at": started_at + timedelta(seconds=1),
        "latency_ms": 1000,
        "status": BaselineRunStatus.success,
        "usage": LLMUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        "output_directory": "data/runtime/baseline_runs/run",
        "input_file": "input_case.json",
        "prompt_file": "rendered_prompt.txt",
        "raw_response_file": "raw_response.txt",
        "error_type": None,
        "error_message": None,
        "git_commit": None,
    }
    payload.update(overrides)
    return payload


def test_valid_success_record_can_be_created() -> None:
    record = BaselineRunRecord.model_validate(valid_record_payload())

    assert record.status is BaselineRunStatus.success


def test_valid_failed_record_can_be_created() -> None:
    record = BaselineRunRecord.model_validate(
        valid_record_payload(
            status=BaselineRunStatus.failed,
            raw_response_file=None,
            error_type="RuntimeError",
            error_message="request failed",
        )
    )

    assert record.status is BaselineRunStatus.failed


def test_success_without_raw_response_file_fails() -> None:
    with pytest.raises(ValidationError, match="raw_response_file"):
        BaselineRunRecord.model_validate(valid_record_payload(raw_response_file=None))


def test_success_with_error_message_fails() -> None:
    with pytest.raises(ValidationError, match="error details"):
        BaselineRunRecord.model_validate(valid_record_payload(error_message="bad"))


def test_failed_without_error_message_fails() -> None:
    with pytest.raises(ValidationError, match="error_type and error_message"):
        BaselineRunRecord.model_validate(
            valid_record_payload(status=BaselineRunStatus.failed, raw_response_file=None)
        )


def test_completed_before_started_fails() -> None:
    started_at = datetime.now(UTC)

    with pytest.raises(ValidationError, match="completed_at"):
        BaselineRunRecord.model_validate(
            valid_record_payload(started_at=started_at, completed_at=started_at - timedelta(seconds=1))
        )


def test_prompt_sha256_format_error_fails() -> None:
    with pytest.raises(ValidationError, match="SHA256"):
        BaselineRunRecord.model_validate(valid_record_payload(prompt_sha256="not-a-sha"))


def test_case_id_format_error_fails() -> None:
    with pytest.raises(ValidationError, match="DEV-01"):
        BaselineRunRecord.model_validate(valid_record_payload(case_id="DEV-1"))


def test_model_dump_json_mode_succeeds() -> None:
    record = BaselineRunRecord.model_validate(valid_record_payload())

    dumped = record.model_dump(mode="json")

    assert dumped["architecture"] == "A"


def valid_structured_record_payload(**overrides):
    started_at = datetime.now(UTC)
    payload = {
        "run_id": "B-DEV-01-20260101T000000Z-abcdef12",
        "architecture": BaselineArchitecture.B,
        "case_id": "DEV-01",
        "prompt_version": "baseline_b_v1",
        "prompt_sha256": "b" * 64,
        "schema_version": "1.0",
        "model": "model-b",
        "provider": "openai_compatible",
        "started_at": started_at,
        "completed_at": started_at + timedelta(seconds=1),
        "latency_ms": 1000,
        "status": BaselineRunStatus.success,
        "usage": LLMUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        "output_directory": "data/runtime/baseline_runs/run",
        "input_file": "input_case.json",
        "system_prompt_file": "system_prompt.txt",
        "user_prompt_file": "user_prompt.txt",
        "raw_response_file": "raw_response.json",
        "parsed_report_file": "parsed_report.json",
        "validation_error_file": None,
        "error_type": None,
        "error_message": None,
        "git_commit": None,
    }
    payload.update(overrides)
    return payload


def test_valid_structured_success_record_can_be_created() -> None:
    record = StructuredBaselineRunRecord.model_validate(valid_structured_record_payload())

    assert record.architecture is BaselineArchitecture.B


def test_structured_success_missing_parsed_report_file_fails() -> None:
    with pytest.raises(ValidationError, match="parsed_report_file"):
        StructuredBaselineRunRecord.model_validate(
            valid_structured_record_payload(parsed_report_file=None)
        )


def test_structured_success_with_validation_error_file_fails() -> None:
    with pytest.raises(ValidationError, match="validation_error_file"):
        StructuredBaselineRunRecord.model_validate(
            valid_structured_record_payload(validation_error_file="validation_error.json")
        )


def test_structured_failed_missing_error_message_fails() -> None:
    with pytest.raises(ValidationError, match="error_type and error_message"):
        StructuredBaselineRunRecord.model_validate(
            valid_structured_record_payload(
                status=BaselineRunStatus.failed,
                parsed_report_file=None,
                raw_response_file=None,
                error_type="RuntimeError",
                error_message=None,
            )
        )


def test_schema_failed_missing_validation_error_file_fails() -> None:
    with pytest.raises(ValidationError, match="validation_error_file"):
        StructuredBaselineRunRecord.model_validate(
            valid_structured_record_payload(
                status=BaselineRunStatus.failed,
                parsed_report_file=None,
                raw_response_file="raw_response.json",
                validation_error_file=None,
                error_type="ValidationError",
                error_message="schema failed",
            )
        )


def test_structured_architecture_not_b_fails() -> None:
    with pytest.raises(ValidationError):
        StructuredBaselineRunRecord.model_validate(
            valid_structured_record_payload(architecture=BaselineArchitecture.A)
        )


def test_structured_model_dump_json_mode_succeeds() -> None:
    record = StructuredBaselineRunRecord.model_validate(valid_structured_record_payload())

    dumped = record.model_dump(mode="json")

    assert dumped["architecture"] == "B"
