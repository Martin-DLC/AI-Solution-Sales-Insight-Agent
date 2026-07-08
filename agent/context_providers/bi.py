from __future__ import annotations

from agent.context_providers.base import BaseContextProvider, ProviderInput
from agent.mcp_mock import EnterpriseContextMockClient


class BIContextProvider(BaseContextProvider):
    name = "bi_context"
    provider_type = "bi"

    def __init__(self, *, client: EnterpriseContextMockClient) -> None:
        self._client = client

    def _fetch(self, provider_input: ProviderInput):
        if not provider_input.company_id:
            return "skipped", None, ["company_id_missing"], None

        context = self._client.get_bi_context(provider_input.company_id)
        if context is None:
            return "skipped", None, ["company_id_not_found"], None

        return "success", context.model_dump(mode="json"), [], None
