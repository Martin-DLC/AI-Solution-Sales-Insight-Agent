from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from schemas.common_models import (
    ConfidenceLevel,
    EvaluationFlagType,
    IntentLevel,
    SalesStage,
    SeverityLevel,
    StrictBaseModel,
)
from schemas.decision_models import CustomerFollowUp, DealScore, NextBestAction
from schemas.insight_models import (
    BusinessImpact,
    BuyingIntent,
    CustomerContext,
    ExplicitNeed,
    InformationGap,
    Stakeholder,
    UnderlyingPain,
)
from schemas.solution_models import AIOpportunity, Risk, SolutionRecommendation


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


class ExecutiveSummary(StrictBaseModel):
    opportunity_summary: str
    overall_intent: IntentLevel
    current_stage: SalesStage
    recommended_strategy: str
    primary_opportunity: str
    primary_risk: str
    confidence: ConfidenceLevel

    @field_validator(
        "opportunity_summary",
        "recommended_strategy",
        "primary_opportunity",
        "primary_risk",
    )
    @classmethod
    def summary_text_must_be_clear(cls, value: str) -> str:
        if len(value) < 5:
            raise ValueError("Executive summary text must contain at least 5 characters.")
        return value


class ReliabilitySummary(StrictBaseModel):
    overall_confidence: ConfidenceLevel
    fact_count: int
    inference_count: int
    assumption_count: int
    unknown_count: int
    unsupported_claim_count: int
    knowledge_grounded_recommendation_rate: float
    critical_information_gap_count: int
    human_review_required: bool = True
    human_review_reasons: list[str]

    @field_validator(
        "fact_count",
        "inference_count",
        "assumption_count",
        "unknown_count",
        "unsupported_claim_count",
        "critical_information_gap_count",
    )
    @classmethod
    def counts_must_not_be_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Reliability summary counts must be zero or greater.")
        return value

    @field_validator("knowledge_grounded_recommendation_rate")
    @classmethod
    def recommendation_rate_must_be_valid(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("Knowledge grounded recommendation rate must be between 0 and 1.")
        return value

    @field_validator("human_review_reasons")
    @classmethod
    def human_review_reasons_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Human review reasons")

    @model_validator(mode="after")
    def validate_reliability_summary(self) -> Self:
        if self.human_review_required and not self.human_review_reasons:
            raise ValueError("Human review reasons are required when human review is required.")
        return self


class EvaluationFlag(StrictBaseModel):
    flag: EvaluationFlagType
    severity: SeverityLevel
    description: str
    affected_fields: list[str]

    @field_validator("description")
    @classmethod
    def description_must_be_clear(cls, value: str) -> str:
        if len(value) < 5:
            raise ValueError("Evaluation flag description must contain at least 5 characters.")
        return value

    @field_validator("affected_fields")
    @classmethod
    def affected_fields_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Affected fields")

    @model_validator(mode="after")
    def validate_evaluation_flag(self) -> Self:
        if not self.affected_fields:
            raise ValueError("Evaluation flag must include at least one affected field.")
        return self


class SalesInsightReport(StrictBaseModel):
    schema_version: Literal["1.0"]
    case_id: str
    analysis_id: str
    generated_at: datetime
    executive_summary: ExecutiveSummary
    customer_context: CustomerContext
    explicit_needs: list[ExplicitNeed]
    underlying_pains: list[UnderlyingPain]
    business_impacts: list[BusinessImpact]
    buying_intent: BuyingIntent
    stakeholder_map: list[Stakeholder]
    information_gaps: list[InformationGap] = Field(default_factory=list)
    ai_opportunities: list[AIOpportunity]
    solution_recommendations: list[SolutionRecommendation] = Field(default_factory=list)
    risks_and_objections: list[Risk]
    deal_score: DealScore
    next_best_actions: list[NextBestAction]
    customer_followup: CustomerFollowUp
    reliability_summary: ReliabilitySummary
    evaluation_flags: list[EvaluationFlag] = Field(default_factory=list)

    @field_validator("case_id")
    @classmethod
    def case_id_must_match_expected_format(cls, value: str) -> str:
        if not re.fullmatch(r"(DEV|TEST)-\d{2}", value):
            raise ValueError("Case ID must use the format DEV-01 or TEST-01.")
        return value

    @field_validator("analysis_id")
    @classmethod
    def analysis_id_must_be_useful(cls, value: str) -> str:
        if len(value) < 5:
            raise ValueError("Analysis ID must contain at least 5 characters.")
        return value

    @model_validator(mode="after")
    def validate_sales_insight_report(self) -> Self:
        if not self.explicit_needs:
            raise ValueError("Sales insight report must include at least one explicit need.")
        if not self.stakeholder_map:
            raise ValueError("Sales insight report must include at least one stakeholder.")
        if not self.ai_opportunities:
            raise ValueError("Sales insight report must include at least one AI opportunity.")
        if not self.risks_and_objections:
            raise ValueError("Sales insight report must include at least one risk or objection.")
        if not self.next_best_actions:
            raise ValueError("Sales insight report must include at least one next best action.")
        if self.executive_summary.overall_intent is not self.buying_intent.intent_level:
            raise ValueError("Executive summary intent must match the buying intent assessment.")
        if self.executive_summary.current_stage is not self.buying_intent.sales_stage:
            raise ValueError("Executive summary stage must match the buying intent sales stage.")
        if not self.reliability_summary.human_review_required:
            raise ValueError("MVP sales insight reports must require human review.")
        return self
