from __future__ import annotations

import re
from enum import Enum
from typing import Self

from pydantic import Field, field_validator, model_validator

from schemas.common_models import IntentLevel, StrictBaseModel


class ReferenceSalesStage(str, Enum):
    market_research = "market_research"
    early_discovery = "early_discovery"
    discovery = "discovery"
    process_data_assessment = "process_data_assessment"
    solution_exploration = "solution_exploration"
    poc_planning = "poc_planning"
    procurement = "procurement"
    contracting = "contracting"
    unknown = "unknown"


def _deduplicate_text(values: list[str], field_label: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            raise ValueError(f"{field_label} cannot include empty values.")
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _deduplicate_stages(values: list[ReferenceSalesStage]) -> list[ReferenceSalesStage]:
    seen: set[ReferenceSalesStage] = set()
    result: list[ReferenceSalesStage] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


class HiddenReferencePack(StrictBaseModel):
    """Offline-only evaluation reference range.

    Hidden Reference Pack is only for offline Evaluation. It must not be passed
    into runtime Agent context. It is not a single required answer wording; it
    describes acceptable judgment ranges for evaluation.
    """

    case_id: str
    must_capture_facts: list[str] = Field(default_factory=list)
    acceptable_explicit_needs: list[str] = Field(default_factory=list)
    acceptable_underlying_pains: list[str] = Field(default_factory=list)
    expected_business_impacts: list[str] = Field(default_factory=list)
    expected_sales_stage_range: list[ReferenceSalesStage] = Field(default_factory=list)
    expected_intent_level: IntentLevel
    known_stakeholders: list[str] = Field(default_factory=list)
    missing_stakeholders: list[str] = Field(default_factory=list)
    critical_information_gaps: list[str] = Field(default_factory=list)
    acceptable_ai_opportunities: list[str] = Field(default_factory=list)
    solution_whitelist: list[str] = Field(default_factory=list)
    solution_blacklist: list[str] = Field(default_factory=list)
    solution_prerequisites: list[str] = Field(default_factory=list)
    critical_risks: list[str] = Field(default_factory=list)
    acceptable_next_actions: list[str] = Field(default_factory=list)
    forbidden_next_actions: list[str] = Field(default_factory=list)
    hard_failure_traps: list[str] = Field(default_factory=list)
    scoring_notes: str

    @field_validator("case_id")
    @classmethod
    def case_id_must_match_expected_format(cls, value: str) -> str:
        if not re.fullmatch(r"(DEV|TEST)-\d{2}", value):
            raise ValueError("Case ID must use the format DEV-01 or TEST-01.")
        return value

    @field_validator(
        "must_capture_facts",
        "acceptable_explicit_needs",
        "acceptable_underlying_pains",
        "expected_business_impacts",
        "known_stakeholders",
        "missing_stakeholders",
        "critical_information_gaps",
        "acceptable_ai_opportunities",
        "solution_whitelist",
        "solution_blacklist",
        "solution_prerequisites",
        "critical_risks",
        "acceptable_next_actions",
        "forbidden_next_actions",
        "hard_failure_traps",
    )
    @classmethod
    def text_lists_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Hidden reference list fields")

    @field_validator("expected_sales_stage_range")
    @classmethod
    def sales_stage_range_is_unique(
        cls, values: list[ReferenceSalesStage]
    ) -> list[ReferenceSalesStage]:
        return _deduplicate_stages(values)

    @field_validator("scoring_notes")
    @classmethod
    def scoring_notes_must_be_clear(cls, value: str) -> str:
        if len(value) < 20:
            raise ValueError("Scoring notes must contain at least 20 characters.")
        return value

    @model_validator(mode="after")
    def validate_required_reference_ranges(self) -> Self:
        required_lists = {
            "must_capture_facts": self.must_capture_facts,
            "acceptable_explicit_needs": self.acceptable_explicit_needs,
            "acceptable_underlying_pains": self.acceptable_underlying_pains,
            "expected_sales_stage_range": self.expected_sales_stage_range,
            "missing_stakeholders": self.missing_stakeholders,
            "critical_information_gaps": self.critical_information_gaps,
            "acceptable_ai_opportunities": self.acceptable_ai_opportunities,
            "solution_whitelist": self.solution_whitelist,
            "solution_blacklist": self.solution_blacklist,
            "solution_prerequisites": self.solution_prerequisites,
            "critical_risks": self.critical_risks,
            "acceptable_next_actions": self.acceptable_next_actions,
            "forbidden_next_actions": self.forbidden_next_actions,
            "hard_failure_traps": self.hard_failure_traps,
        }
        for field_name, values in required_lists.items():
            if not values:
                raise ValueError(
                    f"Hidden Reference Pack {self.case_id} must include at least one item in {field_name}."
                )
        return self
