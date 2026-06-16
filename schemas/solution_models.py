from __future__ import annotations

from typing import Self, TypeVar

from pydantic import Field, field_validator, model_validator

from schemas.common_models import (
    BusinessDimension,
    ClaimType,
    ConfidenceLevel,
    EvidenceReference,
    EvidenceSourceType,
    OpportunitySuitability,
    ProbabilityLevel,
    RiskCategory,
    SeverityLevel,
    SolutionFitLevel,
    StrictBaseModel,
)

T = TypeVar("T")


def _deduplicate_values(values: list[T], field_label: str) -> list[T]:
    seen: set[T] = set()
    result: list[T] = []
    for value in values:
        if type(value) is str and not value:
            raise ValueError(f"{field_label} cannot include empty values.")
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


class AIOpportunity(StrictBaseModel):
    opportunity_id: str
    name: str
    related_pain_ids: list[str]
    suitability: OpportunitySuitability
    business_value: list[BusinessDimension]
    reasoning_summary: str
    required_data: list[str] = Field(default_factory=list)
    required_integrations: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    major_limitations: list[str] = Field(default_factory=list)
    claim_type: ClaimType
    confidence: ConfidenceLevel
    evidence: list[EvidenceReference]

    @field_validator(
        "related_pain_ids",
        "required_data",
        "required_integrations",
        "prerequisites",
        "major_limitations",
    )
    @classmethod
    def text_lists_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_values(values, "AI opportunity list fields")

    @field_validator("business_value")
    @classmethod
    def business_value_is_unique(cls, values: list[BusinessDimension]) -> list[BusinessDimension]:
        return _deduplicate_values(values, "Business value")

    @field_validator("reasoning_summary")
    @classmethod
    def reasoning_summary_must_be_clear(cls, value: str) -> str:
        if len(value) < 10:
            raise ValueError("AI opportunity reasoning must contain at least 10 characters.")
        return value

    @model_validator(mode="after")
    def validate_ai_opportunity(self) -> Self:
        if not self.related_pain_ids:
            raise ValueError("AI opportunity must reference at least one related pain.")
        if not self.business_value:
            raise ValueError("AI opportunity must include at least one business value dimension.")
        if self.claim_type not in {ClaimType.inference, ClaimType.assumption}:
            raise ValueError("AI opportunity claim type must be inference or assumption.")
        if not self.evidence:
            raise ValueError("AI opportunity must include at least one evidence reference.")
        if (
            self.suitability is OpportunitySuitability.suitable_after_prerequisites
            and not self.prerequisites
        ):
            raise ValueError(
                "AI opportunity marked suitable after prerequisites must list those prerequisites."
            )
        limitation_required = {
            OpportunitySuitability.not_recommended_now,
            OpportunitySuitability.not_suitable_for_ai,
            OpportunitySuitability.insufficient_information,
        }
        if self.suitability in limitation_required and not self.major_limitations:
            raise ValueError(
                "AI opportunity with limited suitability must explain the major limitations."
            )
        return self


class SolutionRecommendation(StrictBaseModel):
    recommendation_id: str
    solution_id: str
    solution_name: str
    fit_level: SolutionFitLevel
    related_opportunity_ids: list[str]
    recommended_scope: str
    fit_reasons: list[str]
    prerequisites: list[str] = Field(default_factory=list)
    delivery_risks: list[str] = Field(default_factory=list)
    excluded_capabilities: list[str] = Field(default_factory=list)
    knowledge_references: list[EvidenceReference]
    confidence: ConfidenceLevel

    @field_validator(
        "related_opportunity_ids",
        "fit_reasons",
        "prerequisites",
        "delivery_risks",
        "excluded_capabilities",
    )
    @classmethod
    def text_lists_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_values(values, "Solution recommendation list fields")

    @field_validator("solution_id")
    @classmethod
    def solution_id_must_be_useful(cls, value: str) -> str:
        if len(value) < 3:
            raise ValueError("Solution ID must contain at least 3 characters.")
        return value

    @model_validator(mode="after")
    def validate_solution_recommendation(self) -> Self:
        if not self.related_opportunity_ids:
            raise ValueError("Solution recommendation must reference at least one AI opportunity.")
        if not self.fit_reasons:
            raise ValueError("Solution recommendation must include at least one fit reason.")
        if not self.knowledge_references:
            raise ValueError("Solution recommendation must include knowledge references.")
        if not any(
            reference.source_type is EvidenceSourceType.solution_library
            for reference in self.knowledge_references
        ):
            raise ValueError(
                "Solution recommendation must include at least one solution library reference."
            )
        if self.fit_level in {SolutionFitLevel.high, SolutionFitLevel.medium} and len(
            self.recommended_scope
        ) < 10:
            raise ValueError(
                "High or medium fit recommendations must describe the recommended scope clearly."
            )
        return self


class Risk(StrictBaseModel):
    risk_id: str
    category: RiskCategory
    description: str
    severity: SeverityLevel
    probability: ProbabilityLevel
    impact: str
    mitigation: str
    claim_type: ClaimType
    confidence: ConfidenceLevel
    evidence: list[EvidenceReference]

    @field_validator("impact")
    @classmethod
    def impact_must_be_clear(cls, value: str) -> str:
        if len(value) < 10:
            raise ValueError("Risk impact must contain at least 10 characters.")
        return value

    @field_validator("mitigation")
    @classmethod
    def mitigation_must_be_clear(cls, value: str) -> str:
        if len(value) < 10:
            raise ValueError("Risk mitigation must contain at least 10 characters.")
        return value

    @model_validator(mode="after")
    def validate_risk(self) -> Self:
        if self.claim_type is ClaimType.unknown:
            raise ValueError("Risk claim type cannot be unknown.")
        if not self.evidence:
            raise ValueError("Risk must include at least one evidence reference.")
        return self
