from __future__ import annotations

import json
from pathlib import Path

from agent.mcp_mock.models import BIContext, CRMContext, CompanyProfileContext, EnterpriseContextRecord, KnowledgeAssetContext, TicketContext


FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "enterprise_context.json"


class EnterpriseContextMockClient:
    def __init__(self, fixture_path: Path | None = None) -> None:
        self._fixture_path = fixture_path or FIXTURE_PATH
        payload = json.loads(self._fixture_path.read_text(encoding="utf-8"))
        self._records = {
            record["company_id"]: EnterpriseContextRecord.model_validate(record)
            for record in payload.get("companies", [])
        }

    def list_company_ids(self) -> list[str]:
        return sorted(self._records.keys())

    def get_company_context(self, company_id: str) -> EnterpriseContextRecord | None:
        return self._records.get(company_id)

    def get_company_profile(self, company_id: str) -> CompanyProfileContext | None:
        record = self.get_company_context(company_id)
        return None if record is None else record.company_profile

    def get_crm_context(self, company_id: str) -> CRMContext | None:
        record = self.get_company_context(company_id)
        return None if record is None else record.crm_context

    def get_ticket_context(self, company_id: str) -> TicketContext | None:
        record = self.get_company_context(company_id)
        return None if record is None else record.ticket_context

    def get_bi_context(self, company_id: str) -> BIContext | None:
        record = self.get_company_context(company_id)
        return None if record is None else record.bi_context

    def get_knowledge_context(self, company_id: str) -> KnowledgeAssetContext | None:
        record = self.get_company_context(company_id)
        return None if record is None else record.knowledge_context
