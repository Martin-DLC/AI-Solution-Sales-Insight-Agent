from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from agent.workflow_c.state import FactExtractionResult
from schemas.common_models import StrictBaseModel
from schemas.insight_models import (
    BusinessImpact,
    BuyingIntent,
    ExplicitNeed,
    InformationGap,
    Stakeholder,
    UnderlyingPain,
)


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
