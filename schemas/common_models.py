from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        use_enum_values=False,
    )

    @field_validator("*", check_fields=False)
    @classmethod
    def string_fields_must_not_be_empty(cls, value: object) -> object:
        if type(value) is str and not value:
            raise ValueError("This field is required and cannot be empty.")
        return value


class ClaimType(str, Enum):
    fact = "fact"
    inference = "inference"
    assumption = "assumption"
    unknown = "unknown"


class ConfidenceLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class PriorityLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class SeverityLevel(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class BusinessDimension(str, Enum):
    revenue = "revenue"
    cost = "cost"
    efficiency = "efficiency"
    customer_experience = "customer_experience"
    risk = "risk"
    compliance = "compliance"
    organizational_capability = "organizational_capability"


class ContextQuality(str, Enum):
    sufficient = "sufficient"
    partially_sufficient = "partially_sufficient"
    insufficient = "insufficient"


class IntentLevel(str, Enum):
    high = "high"
    medium_high = "medium_high"
    medium = "medium"
    low = "low"
    unknown = "unknown"


class SalesStage(str, Enum):
    discovery = "discovery"
    solution_exploration = "solution_exploration"
    poc_planning = "poc_planning"
    procurement = "procurement"
    contracting = "contracting"
    unknown = "unknown"


class SalesRole(str, Enum):
    user = "user"
    champion_candidate = "champion_candidate"
    champion = "champion"
    technical_evaluator = "technical_evaluator"
    business_owner = "business_owner"
    budget_owner = "budget_owner"
    decision_maker = "decision_maker"
    procurement = "procurement"
    legal_compliance = "legal_compliance"
    blocker = "blocker"
    unknown = "unknown"


class InfluenceLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"
    unknown = "unknown"


class StakeholderAttitude(str, Enum):
    supportive = "supportive"
    neutral = "neutral"
    resistant = "resistant"
    unknown = "unknown"


class InformationGapCategory(str, Enum):
    business_goal = "business_goal"
    current_metrics = "current_metrics"
    budget = "budget"
    authority = "authority"
    timeline = "timeline"
    decision_process = "decision_process"
    procurement = "procurement"
    data = "data"
    integration = "integration"
    security = "security"
    compliance = "compliance"
    success_metrics = "success_metrics"
    competition = "competition"
    delivery_readiness = "delivery_readiness"


class EvidenceSourceType(str, Enum):
    customer_profile = "customer_profile"
    meeting_transcript = "meeting_transcript"
    salesperson_note = "salesperson_note"
    known_constraint = "known_constraint"
    solution_library = "solution_library"
    reference_case = "reference_case"


class OpportunitySuitability(str, Enum):
    suitable_now = "suitable_now"
    suitable_for_poc = "suitable_for_poc"
    suitable_after_prerequisites = "suitable_after_prerequisites"
    not_recommended_now = "not_recommended_now"
    not_suitable_for_ai = "not_suitable_for_ai"
    insufficient_information = "insufficient_information"


class SolutionFitLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"
    not_recommended = "not_recommended"


class RiskCategory(str, Enum):
    budget = "budget"
    authority = "authority"
    timeline = "timeline"
    data_quality = "data_quality"
    integration = "integration"
    security = "security"
    compliance = "compliance"
    procurement = "procurement"
    competition = "competition"
    scope = "scope"
    delivery = "delivery"
    organizational_change = "organizational_change"
    model_reliability = "model_reliability"
    expectation_management = "expectation_management"


class ProbabilityLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"
    unknown = "unknown"


class DealScoreDimensionName(str, Enum):
    business_need = "business_need"
    business_value = "business_value"
    budget = "budget"
    authority = "authority"
    timeline = "timeline"
    solution_fit = "solution_fit"
    delivery_readiness = "delivery_readiness"


class DealScoreLevel(str, Enum):
    high = "high"
    medium_high = "medium_high"
    medium = "medium"
    low = "low"
    very_low = "very_low"


class ActionPriority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class ActionOwner(str, Enum):
    sales = "sales"
    presales = "presales"
    solution_architect = "solution_architect"
    customer = "customer"
    it = "it"
    security = "security"
    management = "management"
    joint = "joint"
    unknown = "unknown"


class EvaluationFlagType(str, Enum):
    unsupported_claim = "unsupported_claim"
    missing_evidence = "missing_evidence"
    fact_inference_confusion = "fact_inference_confusion"
    unknown_decision_maker = "unknown_decision_maker"
    unknown_budget = "unknown_budget"
    unknown_timeline = "unknown_timeline"
    capability_overreach = "capability_overreach"
    solution_without_knowledge_reference = "solution_without_knowledge_reference"
    stage_action_mismatch = "stage_action_mismatch"
    excessive_scope = "excessive_scope"
    security_risk = "security_risk"
    compliance_risk = "compliance_risk"
    conflicting_conclusions = "conflicting_conclusions"
    low_context_quality = "low_context_quality"
    human_review_required = "human_review_required"


class EvidenceReference(StrictBaseModel):
    source_id: str
    source_type: EvidenceSourceType
    evidence_summary: str

    @field_validator("source_id")
    @classmethod
    def source_id_must_be_useful(cls, value: str) -> str:
        if len(value) < 3:
            raise ValueError("Evidence source ID must contain at least 3 characters.")
        return value

    @field_validator("evidence_summary")
    @classmethod
    def evidence_summary_must_be_useful(cls, value: str) -> str:
        if len(value) < 5:
            raise ValueError("Evidence summary must contain at least 5 characters.")
        return value
