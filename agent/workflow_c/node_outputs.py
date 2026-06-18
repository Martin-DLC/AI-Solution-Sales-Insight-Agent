from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from agent.workflow_c.state import FactExtractionResult
from schemas.common_models import StrictBaseModel
from schemas.insight_models import ExplicitNeed


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
        if len(descriptions) != len(set(descriptions)):
            raise ValueError("Explicit need descriptions must not be duplicated.")
        return self


class ExplicitNeedNodeOutput(ExplicitNeedResult):
    pass
