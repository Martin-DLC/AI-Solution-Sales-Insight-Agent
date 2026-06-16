from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DatasetSplit(str, Enum):
    development = "development"
    holdout = "holdout"


class Difficulty(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class SourceType(str, Enum):
    customer_profile = "customer_profile"
    meeting_transcript = "meeting_transcript"
    salesperson_note = "salesperson_note"
    known_constraint = "known_constraint"


class InputBaseModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


def _require_text(value: str, field_label: str) -> str:
    if not value:
        raise ValueError(f"{field_label} is required and cannot be empty.")
    return value


def _deduplicate_preserve_order(values: list[str], field_label: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            raise ValueError(f"{field_label} cannot include empty values.")
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


class Participant(InputBaseModel):
    name_or_role: str
    organization_role: str | None = None
    source_type: SourceType = SourceType.meeting_transcript

    @field_validator("name_or_role")
    @classmethod
    def name_or_role_must_not_be_empty(cls, value: str) -> str:
        return _require_text(value, "Participant name or role")


class CustomerProfile(InputBaseModel):
    company_name: str
    industry: str
    company_size: str
    main_business: list[str] = Field(default_factory=list)
    digital_maturity: str | None = None
    current_systems: list[str] = Field(default_factory=list)
    publicly_stated_goals: list[str] = Field(default_factory=list)
    known_participants: list[Participant] = Field(default_factory=list)

    @field_validator("company_name")
    @classmethod
    def company_name_must_not_be_empty(cls, value: str) -> str:
        return _require_text(value, "Company name")

    @field_validator("industry")
    @classmethod
    def industry_must_not_be_empty(cls, value: str) -> str:
        return _require_text(value, "Industry")

    @field_validator("company_size")
    @classmethod
    def company_size_must_not_be_empty(cls, value: str) -> str:
        return _require_text(value, "Company size")


class MeetingInput(InputBaseModel):
    participants: list[Participant]
    transcript: str

    @field_validator("transcript")
    @classmethod
    def transcript_must_be_long_enough(cls, value: str) -> str:
        if not value:
            raise ValueError("Meeting transcript is required and cannot be empty.")
        if len(value) < 100:
            raise ValueError(
                "Meeting transcript must contain at least 100 characters after trimming whitespace."
            )
        return value


class SalespersonNote(InputBaseModel):
    content: str
    verified: bool = False

    @field_validator("content")
    @classmethod
    def content_must_not_be_empty(cls, value: str) -> str:
        return _require_text(value, "Salesperson note content")


class KnownConstraint(InputBaseModel):
    category: str
    description: str
    severity: Literal["low", "medium", "high", "critical"] = "medium"

    @field_validator("category")
    @classmethod
    def category_must_not_be_empty(cls, value: str) -> str:
        return _require_text(value, "Constraint category")

    @field_validator("description")
    @classmethod
    def description_must_not_be_empty(cls, value: str) -> str:
        return _require_text(value, "Constraint description")


class EvaluationCaseInput(InputBaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    case_id: str
    case_name: str
    dataset_split: DatasetSplit
    difficulty: Difficulty
    scenario_tags: list[str]
    industry: str
    company_size: str
    current_sales_stage: str
    customer_profile: CustomerProfile
    meeting: MeetingInput
    salesperson_notes: list[SalespersonNote]
    known_constraints: list[KnownConstraint]
    available_solution_library: list[str]

    @field_validator("case_id")
    @classmethod
    def case_id_must_match_expected_format(cls, value: str) -> str:
        if not re.fullmatch(r"(DEV|TEST)-\d{2}", value):
            raise ValueError("Case ID must use the format DEV-01 or TEST-01.")
        return value

    @field_validator("case_name")
    @classmethod
    def case_name_must_not_be_empty(cls, value: str) -> str:
        return _require_text(value, "Case name")

    @field_validator("industry")
    @classmethod
    def industry_must_not_be_empty(cls, value: str) -> str:
        return _require_text(value, "Industry")

    @field_validator("company_size")
    @classmethod
    def company_size_must_not_be_empty(cls, value: str) -> str:
        return _require_text(value, "Company size")

    @field_validator("current_sales_stage")
    @classmethod
    def current_sales_stage_must_not_be_empty(cls, value: str) -> str:
        return _require_text(value, "Current sales stage")

    @field_validator("scenario_tags")
    @classmethod
    def scenario_tags_must_not_be_empty(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("Scenario tags must include at least one tag.")
        return _deduplicate_preserve_order(values, "Scenario tags")

    @field_validator("available_solution_library")
    @classmethod
    def solution_library_must_not_be_empty(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError(
                "Available solution library must include at least one solution ID or name."
            )
        return _deduplicate_preserve_order(values, "Available solution library")
