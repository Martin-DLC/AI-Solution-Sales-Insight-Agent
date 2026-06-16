from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from schemas.common_models import (
    BusinessDimension,
    ClaimType,
    ConfidenceLevel,
    ContextQuality,
    EvidenceReference,
    InformationGapCategory,
    InfluenceLevel,
    IntentLevel,
    PriorityLevel,
    SalesRole,
    SalesStage,
    SeverityLevel,
    StakeholderAttitude,
    StrictBaseModel,
)


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


def _ensure_question_mark(value: str) -> str:
    if value.endswith(("?", "？")):
        return value
    return f"{value}？"


class CustomerContext(StrictBaseModel):
    company_name: str
    industry: str
    company_size: str
    current_systems: list[str] = Field(default_factory=list)
    sales_stage_input: str
    confirmed_constraints: list[str] = Field(default_factory=list)
    context_quality: ContextQuality

    @field_validator("current_systems")
    @classmethod
    def current_systems_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Current systems")

    @field_validator("confirmed_constraints")
    @classmethod
    def confirmed_constraints_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Confirmed constraints")


class ExplicitNeed(StrictBaseModel):
    need_id: str
    description: str
    priority: PriorityLevel
    claim_type: ClaimType = ClaimType.fact
    confidence: ConfidenceLevel
    evidence: list[EvidenceReference]

    @model_validator(mode="after")
    def validate_explicit_need(self) -> Self:
        if self.claim_type is not ClaimType.fact:
            raise ValueError("Explicit needs must be facts stated clearly by the customer.")
        if not self.evidence:
            raise ValueError("Explicit needs must include at least one evidence reference.")
        return self


class UnderlyingPain(StrictBaseModel):
    pain_id: str
    description: str
    business_dimension: BusinessDimension
    severity: SeverityLevel
    claim_type: ClaimType
    reasoning_summary: str
    confidence: ConfidenceLevel
    evidence: list[EvidenceReference]
    validation_question: str

    @field_validator("reasoning_summary")
    @classmethod
    def reasoning_summary_must_be_clear(cls, value: str) -> str:
        if len(value) < 10:
            raise ValueError("Reasoning summary must contain at least 10 characters.")
        return value

    @field_validator("validation_question")
    @classmethod
    def validation_question_must_end_with_question_mark(cls, value: str) -> str:
        return _ensure_question_mark(value)

    @model_validator(mode="after")
    def validate_underlying_pain(self) -> Self:
        if self.claim_type not in {ClaimType.inference, ClaimType.assumption}:
            raise ValueError("Underlying pain must be marked as inference or assumption.")
        if not self.evidence:
            raise ValueError("Underlying pain must include at least one evidence reference.")
        return self


class BusinessImpact(StrictBaseModel):
    impact_id: str
    description: str
    impact_type: BusinessDimension
    quantified: bool
    current_value: str | int | float | None = None
    target_value: str | int | float | None = None
    claim_type: ClaimType
    confidence: ConfidenceLevel
    evidence: list[EvidenceReference]
    measurement_needed: str | None = None

    @model_validator(mode="after")
    def validate_business_impact(self) -> Self:
        if not self.evidence:
            raise ValueError("Business impact must include at least one evidence reference.")
        if self.quantified and self.current_value is None and self.target_value is None:
            raise ValueError(
                "Quantified business impact must include a current value or a target value."
            )
        if (
            not self.quantified
            and self.current_value is None
            and self.target_value is None
            and not self.measurement_needed
        ):
            raise ValueError(
                "Unquantified business impact must explain what measurement is needed."
            )
        return self


class BuyingIntent(StrictBaseModel):
    intent_level: IntentLevel
    sales_stage: SalesStage
    confidence: ConfidenceLevel
    positive_signals: list[str] = Field(default_factory=list)
    negative_signals: list[str] = Field(default_factory=list)
    unknown_factors: list[str] = Field(default_factory=list)
    reasoning_summary: str

    @field_validator("positive_signals")
    @classmethod
    def positive_signals_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Positive signals")

    @field_validator("negative_signals")
    @classmethod
    def negative_signals_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Negative signals")

    @field_validator("unknown_factors")
    @classmethod
    def unknown_factors_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Unknown factors")

    @field_validator("reasoning_summary")
    @classmethod
    def reasoning_summary_must_be_clear(cls, value: str) -> str:
        if len(value) < 10:
            raise ValueError("Buying intent reasoning must contain at least 10 characters.")
        return value

    @model_validator(mode="after")
    def validate_buying_intent(self) -> Self:
        total_signals = (
            len(self.positive_signals)
            + len(self.negative_signals)
            + len(self.unknown_factors)
        )
        if total_signals == 0:
            raise ValueError(
                "Buying intent must include at least one positive signal, negative signal, or unknown factor."
            )
        return self


class Stakeholder(StrictBaseModel):
    stakeholder_id: str
    name_or_role: str
    organization_role: str
    sales_role: SalesRole
    influence_level: InfluenceLevel
    attitude: StakeholderAttitude
    confirmed: bool
    claim_type: ClaimType
    confidence: ConfidenceLevel
    evidence: list[EvidenceReference] = Field(default_factory=list)
    next_validation: str | None = None

    @model_validator(mode="after")
    def validate_stakeholder(self) -> Self:
        if self.confirmed and not self.evidence:
            raise ValueError("Confirmed stakeholders must include at least one evidence reference.")
        if not self.confirmed and not self.next_validation:
            raise ValueError("Unconfirmed stakeholders must include the next validation step.")
        if (
            self.sales_role is SalesRole.decision_maker
            and self.confirmed
            and not self.evidence
        ):
            raise ValueError(
                "A confirmed decision maker must not be marked without evidence."
            )
        if self.sales_role is SalesRole.decision_maker and not self.confirmed and not self.next_validation:
            raise ValueError("Unconfirmed decision makers must include the next validation step.")
        return self


class InformationGap(StrictBaseModel):
    gap_id: str
    category: InformationGapCategory
    description: str
    priority: SeverityLevel
    business_impact: str
    question_to_ask: str
    recommended_owner: Literal[
        "sales",
        "presales",
        "customer",
        "it",
        "security",
        "management",
        "unknown",
    ]

    @field_validator("question_to_ask")
    @classmethod
    def question_to_ask_must_end_with_question_mark(cls, value: str) -> str:
        return _ensure_question_mark(value)

    @model_validator(mode="after")
    def validate_information_gap(self) -> Self:
        if self.priority is SeverityLevel.critical and len(self.business_impact) < 10:
            raise ValueError(
                "Critical information gaps must describe business impact in at least 10 characters."
            )
        return self


class CoreInsightAnalysis(StrictBaseModel):
    customer_context: CustomerContext
    explicit_needs: list[ExplicitNeed]
    underlying_pains: list[UnderlyingPain]
    business_impacts: list[BusinessImpact]
    buying_intent: BuyingIntent
    stakeholder_map: list[Stakeholder]
    information_gaps: list[InformationGap] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_core_analysis(self) -> Self:
        if not self.explicit_needs:
            raise ValueError("Core insight analysis must include at least one explicit need.")
        if not self.stakeholder_map:
            raise ValueError("Core insight analysis must include at least one stakeholder.")
        return self
