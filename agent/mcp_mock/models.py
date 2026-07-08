from __future__ import annotations

from pydantic import Field

from schemas.common_models import StrictBaseModel


class CompanyProfileContext(StrictBaseModel):
    industry: str
    company_size: str
    current_systems: list[str] = Field(default_factory=list)
    business_stage: str


class CRMContext(StrictBaseModel):
    lead_volume: int
    conversion_rate: float
    sales_cycle_days: int
    main_sales_bottlenecks: list[str] = Field(default_factory=list)


class TicketContext(StrictBaseModel):
    monthly_ticket_volume: int
    top_issue_categories: list[str] = Field(default_factory=list)
    avg_response_time_hours: float
    escalation_rate: float


class BIContext(StrictBaseModel):
    key_metrics: list[str] = Field(default_factory=list)
    efficiency_baseline: list[str] = Field(default_factory=list)
    measurable_goals: list[str] = Field(default_factory=list)


class KnowledgeAssetContext(StrictBaseModel):
    existing_docs: list[str] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)
    data_readiness_level: str


class EnterpriseContextRecord(StrictBaseModel):
    company_id: str
    company_profile: CompanyProfileContext
    crm_context: CRMContext
    ticket_context: TicketContext
    bi_context: BIContext
    knowledge_context: KnowledgeAssetContext
    context_source: str = "mcp_mock"
    mock_data: bool = True
