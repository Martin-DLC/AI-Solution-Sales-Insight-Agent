from __future__ import annotations

import operator
import re
from datetime import datetime
from enum import Enum
from typing import Annotated, Self, TypedDict

from pydantic import Field, field_validator, model_validator

from llm.models import LLMUsage
from agent.workflow_c.decision_models import ActionTrace, RiskTrace
from schemas import EvaluationCaseInput
from schemas.common_models import (
    ClaimType,
    ConfidenceLevel,
    ContextQuality,
    EvidenceReference,
    EvidenceSourceType,
    StrictBaseModel,
)
from schemas.decision_models import DealScore, NextBestAction
from schemas.insight_models import (
    BusinessImpact,
    BuyingIntent,
    CustomerContext,
    ExplicitNeed,
    InformationGap,
    Stakeholder,
    UnderlyingPain,
)
from agent.workflow_c.retrieval_models import SolutionRetrievalResult
from schemas.solution_models import AIOpportunity, Risk, SolutionRecommendation
from schemas.output_models import SalesInsightReport


class WorkflowNodeName(str, Enum):
    input_validation = "input_validation"
    source_indexing = "source_indexing"
    fact_extraction = "fact_extraction"
    context_sufficiency = "context_sufficiency"
    explicit_need = "explicit_need"
    underlying_pain = "underlying_pain"
    business_impact = "business_impact"
    buying_intent = "buying_intent"
    stakeholder = "stakeholder"
    information_gap = "information_gap"
    ai_opportunity = "ai_opportunity"
    solution_retrieval = "solution_retrieval"
    solution_recommendation = "solution_recommendation"
    deal_score = "deal_score"
    risk = "risk"
    next_best_action = "next_best_action"
    report_composer = "report_composer"
    final_validation = "final_validation"
    human_review_gate = "human_review_gate"


class WorkflowStatus(str, Enum):
    initialized = "initialized"
    running = "running"
    awaiting_human_review = "awaiting_human_review"
    completed = "completed"
    failed = "failed"


class NodeStatus(str, Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    skipped = "skipped"
    blocked = "blocked"


class AnalysisMode(str, Enum):
    full_analysis = "full_analysis"
    partial_analysis = "partial_analysis"
    clarification_only = "clarification_only"


class FailureCategory(str, Enum):
    input_validation = "input_validation"
    missing_dependency = "missing_dependency"
    llm_request = "llm_request"
    llm_response = "llm_response"
    json_parse = "json_parse"
    schema_validation = "schema_validation"
    final_validation = "final_validation"
    internal_error = "internal_error"


class HumanReviewStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    changes_requested = "changes_requested"


def _deduplicate(values: list[str], field_label: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            raise ValueError(f"{field_label} cannot include empty values.")
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


class SourceIndexItem(StrictBaseModel):
    source_id: str
    source_type: EvidenceSourceType
    source_order: int
    title: str
    content: str
    verified: bool

    @field_validator("source_order")
    @classmethod
    def source_order_must_start_at_one(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Source order must be greater than or equal to 1.")
        return value


class SourceIndexResult(StrictBaseModel):
    items: list[SourceIndexItem]
    source_count: int

    @model_validator(mode="after")
    def validate_source_index(self) -> Self:
        if not self.items:
            raise ValueError("Source index must include at least one source.")
        source_ids = [item.source_id for item in self.items]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Source IDs must not be duplicated.")
        if self.source_count != len(self.items):
            raise ValueError("Source count must equal the number of indexed items.")
        orders = [item.source_order for item in self.items]
        if len(orders) != len(set(orders)):
            raise ValueError("Source orders must not be duplicated.")
        if sorted(orders) != list(range(1, len(self.items) + 1)):
            raise ValueError("Source orders must be continuous from 1.")
        return self


class ExtractedFact(StrictBaseModel):
    fact_id: str
    category: str
    statement: str
    claim_type: ClaimType
    confidence: ConfidenceLevel
    evidence: list[EvidenceReference]

    @model_validator(mode="after")
    def validate_fact(self) -> Self:
        if self.claim_type not in {ClaimType.fact, ClaimType.unknown}:
            raise ValueError("Extracted facts can only be marked as fact or unknown.")
        if not self.evidence:
            raise ValueError("Extracted facts must include at least one evidence reference.")
        return self


class FactExtractionResult(StrictBaseModel):
    facts: list[ExtractedFact]
    unknown_fields: list[str] = Field(default_factory=list)
    customer_context_draft: CustomerContext

    @field_validator("unknown_fields")
    @classmethod
    def unknown_fields_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate(values, "Unknown fields")

    @model_validator(mode="after")
    def validate_fact_extraction(self) -> Self:
        if not self.facts:
            raise ValueError("Fact extraction must include at least one fact.")
        fact_ids = [fact.fact_id for fact in self.facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("Fact IDs must not be duplicated.")
        return self


class ContextSufficiencyResult(StrictBaseModel):
    context_quality: ContextQuality
    analysis_mode: AnalysisMode
    available_categories: list[str] = Field(default_factory=list)
    missing_categories: list[str] = Field(default_factory=list)
    blocking_gaps: list[str] = Field(default_factory=list)
    reasoning_summary: str

    @field_validator("available_categories")
    @classmethod
    def available_categories_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate(values, "Available categories")

    @field_validator("missing_categories")
    @classmethod
    def missing_categories_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate(values, "Missing categories")

    @field_validator("blocking_gaps")
    @classmethod
    def blocking_gaps_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate(values, "Blocking gaps")

    @field_validator("reasoning_summary")
    @classmethod
    def reasoning_summary_must_be_clear(cls, value: str) -> str:
        if len(value) < 10:
            raise ValueError("Context sufficiency reasoning must contain at least 10 characters.")
        return value

    @model_validator(mode="after")
    def validate_quality_and_mode(self) -> Self:
        expected = {
            ContextQuality.sufficient: AnalysisMode.full_analysis,
            ContextQuality.partially_sufficient: AnalysisMode.partial_analysis,
            ContextQuality.insufficient: AnalysisMode.clarification_only,
        }
        if self.analysis_mode is not expected[self.context_quality]:
            raise ValueError("Context quality and analysis mode must match.")
        return self


class NodeValidationIssue(StrictBaseModel):
    location: str
    error_type: str
    message: str
    input_summary: str | None = None

    @field_validator("input_summary")
    @classmethod
    def input_summary_must_be_short(cls, value: str | None) -> str | None:
        if value is not None and len(value) > 500:
            raise ValueError("Input summary must not exceed 500 characters.")
        return value


class WorkflowFailure(StrictBaseModel):
    failure_id: str
    node_name: WorkflowNodeName
    failure_category: FailureCategory
    message: str
    retryable: bool
    attempt: int
    occurred_at: datetime
    validation_issues: list[NodeValidationIssue] = Field(default_factory=list)
    raw_artifact_path: str | None = None

    @field_validator("attempt")
    @classmethod
    def attempt_must_start_at_one(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Failure attempt must be greater than or equal to 1.")
        return value

    @model_validator(mode="after")
    def validate_no_secrets(self) -> Self:
        dumped = str(self.model_dump(mode="json"))
        if re.search(r"sk-[A-Za-z0-9_-]+", dumped, re.IGNORECASE):
            raise ValueError("Workflow failure must not contain API keys.")
        if "Authorization" in dumped:
            raise ValueError("Workflow failure must not contain authentication headers.")
        if "Reference Pack" in dumped:
            raise ValueError("Workflow failure must not contain reference pack data.")
        return self


class NodeExecutionRecord(StrictBaseModel):
    node_name: WorkflowNodeName
    status: NodeStatus
    started_at: datetime
    completed_at: datetime
    latency_ms: int
    prompt_version: str | None = None
    model_name: str | None = None
    usage: LLMUsage = Field(default_factory=LLMUsage)
    output_model: str
    artifact_paths: list[str] = Field(default_factory=list)
    failure_id: str | None = None

    @field_validator("latency_ms")
    @classmethod
    def latency_must_not_be_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Node latency must be zero or greater.")
        return value

    @model_validator(mode="after")
    def validate_node_record(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("Node completed_at cannot be earlier than started_at.")
        if self.status is NodeStatus.succeeded and self.failure_id is not None:
            raise ValueError("Succeeded node records must not include failure_id.")
        if self.status is NodeStatus.failed and not self.failure_id:
            raise ValueError("Failed node records must include failure_id.")
        return self


class HumanReviewDecision(StrictBaseModel):
    required: bool = True
    status: HumanReviewStatus = HumanReviewStatus.pending
    reasons: list[str]
    reviewable_artifacts: list[str] = Field(default_factory=list)
    blocked_actions: list[str]

    @model_validator(mode="after")
    def validate_human_review(self) -> Self:
        if self.required is not True:
            raise ValueError("Architecture C MVP requires human review.")
        if not self.reasons:
            raise ValueError("Human review must include at least one reason.")
        if not self.blocked_actions:
            raise ValueError("Human review must block external actions.")
        return self


class ArchitectureCGraphState(TypedDict, total=False):
    run_id: str
    architecture_version: str
    workflow_version: str
    schema_version: str
    workflow_status: WorkflowStatus
    current_node: WorkflowNodeName | None
    case_input: EvaluationCaseInput | dict
    validated_case: EvaluationCaseInput
    source_index: SourceIndexResult
    fact_extraction: FactExtractionResult
    context_sufficiency: ContextSufficiencyResult
    explicit_needs: list[ExplicitNeed]
    underlying_pains: list[UnderlyingPain]
    business_impacts: list[BusinessImpact]
    buying_intent: BuyingIntent
    stakeholder_map: list[Stakeholder]
    information_gaps: list[InformationGap]
    ai_opportunities: list[AIOpportunity]
    retrieved_solutions: SolutionRetrievalResult
    solution_recommendations: list[SolutionRecommendation]
    deal_score: DealScore
    risks_and_objections: list[Risk]
    risk_traces: list[RiskTrace]
    next_best_actions: list[NextBestAction]
    action_traces: list[ActionTrace]
    report_draft: SalesInsightReport
    human_review_decision: HumanReviewDecision
    node_records: Annotated[list[NodeExecutionRecord], operator.add]
    failures: Annotated[list[WorkflowFailure], operator.add]
    warnings: Annotated[list[str], operator.add]
    human_review_required: bool
    human_review_reasons: Annotated[list[str], operator.add]


class ArchitectureCStateSnapshot(StrictBaseModel):
    run_id: str
    architecture_version: str
    workflow_version: str
    schema_version: str
    workflow_status: WorkflowStatus
    current_node: WorkflowNodeName | None = None
    case_input: EvaluationCaseInput | dict
    validated_case: EvaluationCaseInput | None = None
    source_index: SourceIndexResult | None = None
    fact_extraction: FactExtractionResult | None = None
    context_sufficiency: ContextSufficiencyResult | None = None
    explicit_needs: list[ExplicitNeed] | None = None
    underlying_pains: list[UnderlyingPain] | None = None
    business_impacts: list[BusinessImpact] | None = None
    buying_intent: BuyingIntent | None = None
    stakeholder_map: list[Stakeholder] | None = None
    information_gaps: list[InformationGap] | None = None
    ai_opportunities: list[AIOpportunity] | None = None
    retrieved_solutions: SolutionRetrievalResult | None = None
    solution_recommendations: list[SolutionRecommendation] | None = None
    deal_score: DealScore | None = None
    risks_and_objections: list[Risk] | None = None
    risk_traces: list[RiskTrace] | None = None
    next_best_actions: list[NextBestAction] | None = None
    action_traces: list[ActionTrace] | None = None
    report_draft: SalesInsightReport | None = None
    human_review_decision: HumanReviewDecision | None = None
    node_records: list[NodeExecutionRecord] = Field(default_factory=list)
    failures: list[WorkflowFailure] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    human_review_required: bool = True
    human_review_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        if self.architecture_version != "C":
            raise ValueError("Architecture version must be C.")
        if self.workflow_version != "c_skeleton_v1":
            raise ValueError("Workflow version must be c_skeleton_v1.")
        if self.schema_version != "1.0":
            raise ValueError("Schema version must be 1.0.")
        if self.workflow_status is WorkflowStatus.failed and not self.failures:
            raise ValueError("Failed workflow snapshots must include at least one failure.")
        if self.workflow_status is WorkflowStatus.awaiting_human_review:
            if self.human_review_required is not True:
                raise ValueError("Human review states must set human_review_required to true.")
            if self.human_review_decision is None:
                raise ValueError("Human review states must include a review decision.")
        return self
