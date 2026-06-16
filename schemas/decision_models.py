from __future__ import annotations

from typing import Self

from pydantic import Field, field_validator, model_validator

from schemas.common_models import (
    ActionOwner,
    ActionPriority,
    ConfidenceLevel,
    DealScoreDimensionName,
    DealScoreLevel,
    EvidenceReference,
    StrictBaseModel,
)


DEAL_SCORE_WEIGHTS: dict[DealScoreDimensionName, int] = {
    DealScoreDimensionName.business_need: 20,
    DealScoreDimensionName.business_value: 15,
    DealScoreDimensionName.budget: 15,
    DealScoreDimensionName.authority: 15,
    DealScoreDimensionName.timeline: 10,
    DealScoreDimensionName.solution_fit: 15,
    DealScoreDimensionName.delivery_readiness: 10,
}


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


def score_level_for_total(total_score: int) -> DealScoreLevel:
    if 80 <= total_score <= 100:
        return DealScoreLevel.high
    if 65 <= total_score <= 79:
        return DealScoreLevel.medium_high
    if 45 <= total_score <= 64:
        return DealScoreLevel.medium
    if 25 <= total_score <= 44:
        return DealScoreLevel.low
    return DealScoreLevel.very_low


class DealScoreDimension(StrictBaseModel):
    dimension: DealScoreDimensionName
    score: int
    max_score: int
    reasoning: str
    evidence: list[EvidenceReference]

    @field_validator("reasoning")
    @classmethod
    def reasoning_must_be_clear(cls, value: str) -> str:
        if len(value) < 10:
            raise ValueError("Deal score dimension reasoning must contain at least 10 characters.")
        return value

    @model_validator(mode="after")
    def validate_dimension_score(self) -> Self:
        expected_max_score = DEAL_SCORE_WEIGHTS[self.dimension]
        if self.max_score != expected_max_score:
            raise ValueError(
                f"Max score for {self.dimension.value} must be {expected_max_score}."
            )
        if self.score < 0 or self.score > self.max_score:
            raise ValueError("Deal score dimension score must be between 0 and max_score.")
        if not self.evidence:
            raise ValueError("Deal score dimension must include at least one evidence reference.")
        return self


class DealScore(StrictBaseModel):
    """Structured deal quality score; it is not a probability of closing the deal."""

    total_score: int
    score_level: DealScoreLevel
    confidence: ConfidenceLevel
    dimensions: list[DealScoreDimension]
    score_limiters: list[str] = Field(default_factory=list)
    conditions_to_increase_score: list[str] = Field(default_factory=list)
    reasoning_summary: str

    @field_validator("score_limiters")
    @classmethod
    def score_limiters_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Score limiters")

    @field_validator("conditions_to_increase_score")
    @classmethod
    def conditions_to_increase_score_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Conditions to increase score")

    @field_validator("reasoning_summary")
    @classmethod
    def reasoning_summary_must_be_clear(cls, value: str) -> str:
        if len(value) < 10:
            raise ValueError("Deal score reasoning summary must contain at least 10 characters.")
        return value

    @model_validator(mode="after")
    def validate_deal_score(self) -> Self:
        if self.total_score < 0 or self.total_score > 100:
            raise ValueError("Deal score total must be between 0 and 100.")

        dimensions = [dimension.dimension for dimension in self.dimensions]
        if len(dimensions) != len(set(dimensions)):
            raise ValueError("Deal score dimensions cannot contain duplicate dimensions.")
        if set(dimensions) != set(DEAL_SCORE_WEIGHTS):
            raise ValueError("Deal score must include exactly all 7 required dimensions.")

        calculated_total = sum(dimension.score for dimension in self.dimensions)
        if self.total_score != calculated_total:
            raise ValueError("Deal score total must equal the sum of dimension scores.")

        expected_level = score_level_for_total(self.total_score)
        if self.score_level is not expected_level:
            raise ValueError(
                f"Deal score level must be {expected_level.value} for total score {self.total_score}."
            )
        return self


class NextBestAction(StrictBaseModel):
    action_id: str
    priority: ActionPriority
    objective: str
    action: str
    owner: ActionOwner
    required_participants: list[str] = Field(default_factory=list)
    required_inputs: list[str] = Field(default_factory=list)
    expected_output: str
    suggested_timeframe: str
    success_criteria: str
    related_gap_ids: list[str] = Field(default_factory=list)
    reasoning_summary: str

    @field_validator("required_participants")
    @classmethod
    def required_participants_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Required participants")

    @field_validator("required_inputs")
    @classmethod
    def required_inputs_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Required inputs")

    @field_validator("related_gap_ids")
    @classmethod
    def related_gap_ids_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Related gap IDs")

    @field_validator("objective", "expected_output", "success_criteria", "reasoning_summary")
    @classmethod
    def action_text_must_be_clear(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Next best action text must contain at least 8 characters.")
        return value

    @field_validator("action")
    @classmethod
    def action_must_be_specific(cls, value: str) -> str:
        vague_actions = {"持续跟进", "保持沟通", "加强沟通", "follow up", "keep in touch"}
        if value.casefold() in vague_actions:
            raise ValueError("Next best action must be specific, not a generic follow-up.")
        return value

    @model_validator(mode="after")
    def validate_next_best_action(self) -> Self:
        if self.priority is ActionPriority.P0 and not self.related_gap_ids:
            raise ValueError("P0 next best actions must reference at least one information gap.")
        return self


class CustomerFollowUp(StrictBaseModel):
    internal_summary: str
    customer_email_subject: str
    customer_email_body: str
    next_meeting_agenda: list[str]
    materials_to_prepare: list[str] = Field(default_factory=list)
    claims_requiring_human_review: list[str] = Field(default_factory=list)

    @field_validator("internal_summary")
    @classmethod
    def internal_summary_must_be_clear(cls, value: str) -> str:
        if len(value) < 10:
            raise ValueError("Internal summary must contain at least 10 characters.")
        return value

    @field_validator("customer_email_body")
    @classmethod
    def customer_email_body_must_be_clear(cls, value: str) -> str:
        if len(value) < 20:
            raise ValueError("Customer email body must contain at least 20 characters.")
        return value

    @field_validator(
        "next_meeting_agenda",
        "materials_to_prepare",
        "claims_requiring_human_review",
    )
    @classmethod
    def lists_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Customer follow-up list fields")

    @model_validator(mode="after")
    def validate_customer_followup(self) -> Self:
        if not self.next_meeting_agenda:
            raise ValueError("Customer follow-up must include at least one agenda item.")
        return self
