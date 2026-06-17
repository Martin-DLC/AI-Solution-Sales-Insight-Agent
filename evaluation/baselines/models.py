from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Self

from pydantic import field_validator, model_validator

from llm.models import LLMUsage
from schemas.common_models import StrictBaseModel


class BaselineArchitecture(str, Enum):
    A = "A"


class BaselineRunStatus(str, Enum):
    success = "success"
    failed = "failed"


class BaselineRunRecord(StrictBaseModel):
    run_id: str
    architecture: BaselineArchitecture
    case_id: str
    prompt_version: str
    prompt_sha256: str
    model: str
    provider: str
    started_at: datetime
    completed_at: datetime
    latency_ms: int
    status: BaselineRunStatus
    usage: LLMUsage
    output_directory: str
    input_file: str
    prompt_file: str
    raw_response_file: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    git_commit: str | None = None

    @field_validator("case_id")
    @classmethod
    def case_id_must_match_expected_format(cls, value: str) -> str:
        if not re.fullmatch(r"(DEV|TEST)-\d{2}", value):
            raise ValueError("Case ID must use the format DEV-01 or TEST-01.")
        return value

    @field_validator("prompt_sha256")
    @classmethod
    def prompt_sha256_must_be_valid(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("Prompt SHA256 must be a 64-character lowercase hexadecimal string.")
        return value

    @field_validator("latency_ms")
    @classmethod
    def latency_must_not_be_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Baseline run latency must be zero or greater.")
        return value

    @model_validator(mode="after")
    def validate_run_record(self) -> Self:
        if self.architecture is not BaselineArchitecture.A:
            raise ValueError("Baseline run architecture must be A for this runner.")
        if self.completed_at < self.started_at:
            raise ValueError("Baseline run completed_at cannot be earlier than started_at.")
        if self.status is BaselineRunStatus.success:
            if not self.raw_response_file:
                raise ValueError("Successful Baseline A runs must include raw_response_file.")
            if self.error_type is not None or self.error_message is not None:
                raise ValueError("Successful Baseline A runs must not include error details.")
        if self.status is BaselineRunStatus.failed:
            if not self.error_type or not self.error_message:
                raise ValueError("Failed Baseline A runs must include error_type and error_message.")
        return self
