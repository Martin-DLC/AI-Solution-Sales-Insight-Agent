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
