from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from agent.workflow_c.decision_models import ActionTrace, RiskTrace
from agent.workflow_c.retrieval_models import SolutionRetrievalResult
from agent.workflow_c.state import FactExtractionResult
from schemas.common_models import StrictBaseModel
from schemas.decision_models import DealScore, NextBestAction
from schemas.insight_models import (
    BusinessImpact,
    BuyingIntent,
    ExplicitNeed,
    InformationGap,
    Stakeholder,
    UnderlyingPain,
)
from schemas.solution_models import AIOpportunity, Risk, SolutionRecommendation


def _normalized_descriptions_are_unique(
    descriptions: list[str],
    field_label: str,
) -> None:
    normalized = [" ".join(description.split()) for description in descriptions]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_label} descriptions must not be duplicated.")


class FactExtractionNodeOutput(StrictBaseModel):
    fact_extraction: FactExtractionResult


class ExplicitNeedResult(StrictBaseModel):
    explicit_needs: list[ExplicitNeed] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_explicit_needs(self) -> Self:
        if not self.explicit_needs:
            raise ValueError("Explicit need extraction must include at least one need.")

        need_ids = [need.need_id for need in self.explicit_needs]
        if len(need_ids) != len(set(need_ids)):
            raise ValueError("Explicit need IDs must not be duplicated.")

        descriptions = [need.description for need in self.explicit_needs]
        _normalized_descriptions_are_unique(descriptions, "Explicit need")
        return self


class ExplicitNeedNodeOutput(ExplicitNeedResult):
    pass


class UnderlyingPainResult(StrictBaseModel):
    underlying_pains: list[UnderlyingPain] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_underlying_pains(self) -> Self:
        if not self.underlying_pains:
            raise ValueError("Underlying pain extraction must include at least one pain.")

        pain_ids = [pain.pain_id for pain in self.underlying_pains]
        if len(pain_ids) != len(set(pain_ids)):
            raise ValueError("Underlying pain IDs must not be duplicated.")

        _normalized_descriptions_are_unique(
            [pain.description for pain in self.underlying_pains],
            "Underlying pain",
        )
        return self


class UnderlyingPainNodeOutput(UnderlyingPainResult):
    pass


class BusinessImpactResult(StrictBaseModel):
    business_impacts: list[BusinessImpact] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_business_impacts(self) -> Self:
        if not self.business_impacts:
            raise ValueError("Business impact analysis must include at least one impact.")

        impact_ids = [impact.impact_id for impact in self.business_impacts]
        if len(impact_ids) != len(set(impact_ids)):
            raise ValueError("Business impact IDs must not be duplicated.")

        _normalized_descriptions_are_unique(
            [impact.description for impact in self.business_impacts],
            "Business impact",
        )
        return self


class BusinessImpactNodeOutput(BusinessImpactResult):
    pass


class BuyingIntentNodeOutput(StrictBaseModel):
    buying_intent: BuyingIntent


class StakeholderResult(StrictBaseModel):
    stakeholder_map: list[Stakeholder] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_stakeholders(self) -> Self:
        if not self.stakeholder_map:
            raise ValueError("Stakeholder analysis must include at least one stakeholder.")

        stakeholder_ids = [stakeholder.stakeholder_id for stakeholder in self.stakeholder_map]
        if len(stakeholder_ids) != len(set(stakeholder_ids)):
            raise ValueError("Stakeholder IDs must not be duplicated.")

        normalized_names = [
            " ".join(stakeholder.name_or_role.split()).casefold()
            for stakeholder in self.stakeholder_map
        ]
        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError("Stakeholder name_or_role values must not be duplicated.")
        return self


class StakeholderNodeOutput(StakeholderResult):
    pass


class InformationGapResult(StrictBaseModel):
    information_gaps: list[InformationGap] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_information_gaps(self) -> Self:
        if not self.information_gaps:
            raise ValueError("Information gap analysis must include at least one gap.")

        gap_ids = [gap.gap_id for gap in self.information_gaps]
        if len(gap_ids) != len(set(gap_ids)):
            raise ValueError("Information gap IDs must not be duplicated.")

        _normalized_descriptions_are_unique(
            [gap.description for gap in self.information_gaps],
            "Information gap",
        )
        normalized_questions = [
            " ".join(gap.question_to_ask.split()).casefold()
            for gap in self.information_gaps
        ]
        if len(normalized_questions) != len(set(normalized_questions)):
            raise ValueError("Information gap questions must not be duplicated.")
        return self


class InformationGapNodeOutput(InformationGapResult):
    pass


class AIOpportunityResult(StrictBaseModel):
    ai_opportunities: list[AIOpportunity] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ai_opportunities(self) -> Self:
        if not self.ai_opportunities:
            raise ValueError("AI opportunity analysis must include at least one opportunity.")

        opportunity_ids = [
            opportunity.opportunity_id for opportunity in self.ai_opportunities
        ]
        if len(opportunity_ids) != len(set(opportunity_ids)):
            raise ValueError("AI opportunity IDs must not be duplicated.")

        normalized_names = [
            " ".join(opportunity.name.split()).casefold()
            for opportunity in self.ai_opportunities
        ]
        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError("AI opportunity names must not be duplicated.")
        return self


class AIOpportunityNodeOutput(AIOpportunityResult):
    pass


class SolutionRetrievalNodeOutput(StrictBaseModel):
    retrieved_solutions: SolutionRetrievalResult


class SolutionRecommendationResult(StrictBaseModel):
    solution_recommendations: list[SolutionRecommendation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_solution_recommendations(self) -> Self:
        recommendation_ids = [
            recommendation.recommendation_id
            for recommendation in self.solution_recommendations
        ]
        if len(recommendation_ids) != len(set(recommendation_ids)):
            raise ValueError("Solution recommendation IDs must not be duplicated.")

        solution_ids = [
            recommendation.solution_id
            for recommendation in self.solution_recommendations
        ]
        if len(solution_ids) != len(set(solution_ids)):
            raise ValueError("Solution IDs must not be recommended more than once.")
        return self


class SolutionRecommendationNodeOutput(SolutionRecommendationResult):
    pass


class DealScoreNodeOutput(StrictBaseModel):
    deal_score: DealScore


class RiskResult(StrictBaseModel):
    risks_and_objections: list[Risk] = Field(default_factory=list)
    risk_traces: list[RiskTrace] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_risks(self) -> Self:
        if not self.risks_and_objections:
            raise ValueError("Risk analysis must include at least one risk.")
        risk_ids = [risk.risk_id for risk in self.risks_and_objections]
        if len(risk_ids) != len(set(risk_ids)):
            raise ValueError("Risk IDs must not be duplicated.")
        _normalized_descriptions_are_unique(
            [risk.description for risk in self.risks_and_objections],
            "Risk",
        )
        trace_ids = [trace.risk_id for trace in self.risk_traces]
        if len(trace_ids) != len(set(trace_ids)):
            raise ValueError("Risk trace IDs must not be duplicated.")
        if set(trace_ids) != set(risk_ids):
            raise ValueError("Each risk must have exactly one matching risk trace.")
        return self


class RiskNodeOutput(RiskResult):
    pass


class NextBestActionResult(StrictBaseModel):
    next_best_actions: list[NextBestAction] = Field(default_factory=list)
    action_traces: list[ActionTrace] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_actions(self) -> Self:
        if not self.next_best_actions:
            raise ValueError("Next best action analysis must include at least one action.")
        action_ids = [action.action_id for action in self.next_best_actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("Action IDs must not be duplicated.")
        normalized_actions = [
            " ".join(action.action.split()).casefold()
            for action in self.next_best_actions
        ]
        if len(normalized_actions) != len(set(normalized_actions)):
            raise ValueError("Next best action descriptions must not be duplicated.")
        trace_ids = [trace.action_id for trace in self.action_traces]
        if len(trace_ids) != len(set(trace_ids)):
            raise ValueError("Action trace IDs must not be duplicated.")
        if set(trace_ids) != set(action_ids):
            raise ValueError("Each action must have exactly one matching action trace.")
        priorities = {"P0": 0, "P1": 1, "P2": 2}
        if [priorities[action.priority.value] for action in self.next_best_actions] != sorted(
            priorities[action.priority.value] for action in self.next_best_actions
        ):
            raise ValueError("Next best actions must be sorted by priority.")
        return self


class NextBestActionNodeOutput(NextBestActionResult):
    pass
