from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, Self

from pydantic import BaseModel, Field, model_validator

from agent.workflow_c.state import (
    ContextSufficiencyResult,
    FactExtractionResult,
    HumanReviewDecision,
    NodeExecutionRecord,
    NodeStatus,
    SourceIndexResult,
    WorkflowFailure,
    WorkflowNodeName,
    WorkflowStatus,
)
from agent.workflow_c.node_outputs import (
    BusinessImpactNodeOutput,
    BusinessImpactResult,
    BuyingIntentNodeOutput,
    DealScoreNodeOutput,
    ExplicitNeedNodeOutput,
    ExplicitNeedResult,
    FactExtractionNodeOutput,
    InformationGapNodeOutput,
    InformationGapResult,
    NextBestActionNodeOutput,
    NextBestActionResult,
    RiskNodeOutput,
    RiskResult,
    SolutionRetrievalNodeOutput,
    SolutionRecommendationNodeOutput,
    SolutionRecommendationResult,
    StakeholderNodeOutput,
    StakeholderResult,
    UnderlyingPainNodeOutput,
    UnderlyingPainResult,
)
from schemas import EvaluationCaseInput
from schemas.common_models import StrictBaseModel


class NodeFailurePolicy(str, Enum):
    fail_workflow = "fail_workflow"
    require_human_review = "require_human_review"


RESERVED_STATE_FIELDS = {"node_records", "failures", "warnings"}


@dataclass(frozen=True)
class NodeContract:
    name: WorkflowNodeName
    required_state_fields: tuple[str, ...]
    produced_state_fields: tuple[str, ...]
    output_model: type[BaseModel]
    failure_policy: NodeFailurePolicy
    prompt_version: str | None = None

    def __post_init__(self) -> None:
        required = set(self.required_state_fields)
        produced = set(self.produced_state_fields)
        if len(required) != len(self.required_state_fields):
            raise ValueError("Required state fields must not be duplicated.")
        if not self.produced_state_fields:
            raise ValueError("Produced state fields must include at least one field.")
        if len(produced) != len(self.produced_state_fields):
            raise ValueError("Produced state fields must not be duplicated.")
        overlap = required & produced
        if overlap:
            raise ValueError(f"Required and produced state fields must not overlap: {overlap}.")
        reserved = (required | produced) & RESERVED_STATE_FIELDS
        if reserved:
            raise ValueError(f"Nodes must not declare internal state fields: {reserved}.")


class WorkflowNode(Protocol):
    contract: NodeContract

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        ...


class InputValidationOutput(StrictBaseModel):
    validated_case: EvaluationCaseInput


class SourceIndexingOutput(StrictBaseModel):
    source_index: SourceIndexResult


class FakeFactExtractionOutput(FactExtractionNodeOutput):
    pass


class ContextSufficiencyOutput(StrictBaseModel):
    context_sufficiency: ContextSufficiencyResult


class HumanReviewGateOutput(StrictBaseModel):
    human_review_decision: HumanReviewDecision
    human_review_required: bool
    human_review_reasons: list[str] = Field(default_factory=list)
    workflow_status: WorkflowStatus

    @model_validator(mode="after")
    def workflow_status_must_await_review(self) -> Self:
        if self.workflow_status is not WorkflowStatus.awaiting_human_review:
            raise ValueError("Human review gate must set workflow_status to awaiting_human_review.")
        return self


class NodeExecutionResult(StrictBaseModel):
    node_name: WorkflowNodeName
    status: NodeStatus
    state_patch: dict[str, Any]
    record: NodeExecutionRecord
    failure: WorkflowFailure | None = None
