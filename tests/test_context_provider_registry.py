from __future__ import annotations

from agent.context_providers import (
    BIContextProvider,
    BaseContextProvider,
    CRMContextProvider,
    ContextProviderRegistry,
    KnowledgeContextProvider,
    ProviderInput,
    TicketContextProvider,
)
from agent.mcp_mock import EnterpriseContextMockClient


class ExplodingProvider(BaseContextProvider):
    name = "exploding"
    provider_type = "crm"

    def _fetch(self, provider_input: ProviderInput):
        raise RuntimeError("provider boom")


def _registry() -> ContextProviderRegistry:
    client = EnterpriseContextMockClient()
    registry = ContextProviderRegistry()
    registry.register(CRMContextProvider(client=client))
    registry.register(TicketContextProvider(client=client))
    registry.register(BIContextProvider(client=client))
    registry.register(KnowledgeContextProvider(client=client))
    return registry


def test_registry_registers_and_lists_providers() -> None:
    registry = _registry()

    assert registry.list_providers() == [
        "crm_context",
        "ticket_context",
        "bi_context",
        "knowledge_context",
    ]


def test_duplicate_provider_name_raises() -> None:
    client = EnterpriseContextMockClient()
    registry = ContextProviderRegistry()
    registry.register(CRMContextProvider(client=client))

    try:
        registry.register(CRMContextProvider(client=client))
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected duplicate provider registration to fail.")


def test_fetch_all_order_is_stable() -> None:
    registry = _registry()

    results = registry.fetch_all(ProviderInput(company_id="demo_saas_001", request_id="req-1"))

    assert [result.provider_name for result in results] == registry.list_providers()


def test_single_provider_failure_does_not_break_others() -> None:
    registry = _registry()
    registry.register(ExplodingProvider())

    results = registry.fetch_all(ProviderInput(company_id="demo_saas_001", request_id="req-2"))
    statuses = {result.provider_name: result.status for result in results}

    assert statuses["crm_context"] == "success"
    assert statuses["ticket_context"] == "success"
    assert statuses["bi_context"] == "success"
    assert statuses["knowledge_context"] == "success"
    assert statuses["exploding"] == "failed"


def test_missing_company_id_skips_all_providers() -> None:
    registry = _registry()

    results = registry.fetch_all(ProviderInput(company_id=None, request_id="req-3"))

    assert all(result.status == "skipped" for result in results)


def test_known_company_id_succeeds_for_all_providers() -> None:
    registry = _registry()

    results = registry.fetch_all(ProviderInput(company_id="demo_saas_001", request_id="req-4"))

    assert all(result.status == "success" for result in results)


def test_unknown_company_id_does_not_raise() -> None:
    registry = _registry()

    results = registry.fetch_all(ProviderInput(company_id="unknown_company", request_id="req-5"))

    assert all(result.status == "skipped" for result in results)
