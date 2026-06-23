from __future__ import annotations

from enum import Enum
from typing import Self, TypeVar

from pydantic import Field, field_validator, model_validator

from schemas.common_models import StrictBaseModel

T = TypeVar("T")


class WorkflowActionType(str, Enum):
    clarification = "clarification"
    qualification = "qualification"
    stakeholder_alignment = "stakeholder_alignment"
    technical_validation = "technical_validation"
    poc_planning = "poc_planning"
    solution_review = "solution_review"
    commercial_proposal = "commercial_proposal"
    procurement = "procurement"
    contracting = "contracting"
    follow_up = "follow_up"


def deduplicate_preserving_order(values: list[T]) -> list[T]:
    seen: set[T] = set()
    result: list[T] = []
    for value in values:
        if type(value) is str and not value:
            raise ValueError("Trace list fields cannot include empty values.")
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


class RiskTrace(StrictBaseModel):
    risk_id: str
    related_gap_ids: list[str] = Field(default_factory=list)
    related_opportunity_ids: list[str] = Field(default_factory=list)

    @field_validator("related_gap_ids", "related_opportunity_ids")
    @classmethod
    def trace_ids_are_unique(cls, values: list[str]) -> list[str]:
        return deduplicate_preserving_order(values)

    @model_validator(mode="after")
    def validate_trace(self) -> Self:
        if not self.related_gap_ids and not self.related_opportunity_ids:
            raise ValueError("Risk trace must reference at least one gap or AI opportunity.")
        return self


class ActionTrace(StrictBaseModel):
    action_id: str
    related_risk_ids: list[str] = Field(default_factory=list)
    action_type: WorkflowActionType

    @field_validator("related_risk_ids")
    @classmethod
    def related_risk_ids_are_unique(cls, values: list[str]) -> list[str]:
        return deduplicate_preserving_order(values)
