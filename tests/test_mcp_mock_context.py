from __future__ import annotations

from agent.mcp_mock import EnterpriseContextMockClient
from agent.skills.enterprise_context import EnterpriseContextSkill
from agent.skills.base import SkillInput


class StubService:
    def __init__(self) -> None:
        self._enterprise_context_client = EnterpriseContextMockClient()


class RequestStub:
    def __init__(self, company_id: str | None) -> None:
        self.company_id = company_id


def test_fixture_can_be_parsed_and_lists_demo_companies() -> None:
    client = EnterpriseContextMockClient()

    assert client.list_company_ids() == [
        "demo_ecommerce_001",
        "demo_manufacturing_001",
        "demo_saas_001",
    ]


def test_demo_company_has_full_context_sections() -> None:
    client = EnterpriseContextMockClient()
    record = client.get_company_context("demo_saas_001")

    assert record is not None
    assert record.crm_context.main_sales_bottlenecks
    assert record.ticket_context.top_issue_categories
    assert record.bi_context.key_metrics
    assert record.knowledge_context.data_readiness_level


def test_enterprise_context_skill_skips_without_company_id() -> None:
    skill = EnterpriseContextSkill(service=StubService())

    result = skill.execute(
        SkillInput(
            request_id="req-1",
            user_query="hello",
            context={"request": RequestStub(None)},
        )
    )

    assert result.status == "skipped"
    assert result.output["enterprise_context"] is None
    assert result.warnings == ["company_id_missing"]


def test_enterprise_context_skill_returns_success_for_known_company() -> None:
    skill = EnterpriseContextSkill(service=StubService())

    result = skill.execute(
        SkillInput(
            request_id="req-2",
            user_query="hello",
            context={"request": RequestStub("demo_saas_001")},
        )
    )

    assert result.status == "success"
    assert result.output["enterprise_context"]["context_source"] == "mcp_mock"
    assert result.output["enterprise_context"]["mock_data"] is True


def test_enterprise_context_skill_skips_unknown_company() -> None:
    skill = EnterpriseContextSkill(service=StubService())

    result = skill.execute(
        SkillInput(
            request_id="req-3",
            user_query="hello",
            context={"request": RequestStub("unknown_company")},
        )
    )

    assert result.status == "skipped"
    assert result.output["enterprise_context"] is None
    assert result.warnings == ["company_id_not_found"]
