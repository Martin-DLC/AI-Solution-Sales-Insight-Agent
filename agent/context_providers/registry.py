from __future__ import annotations

from agent.context_providers.base import BaseContextProvider, ProviderInput, ProviderOutput


class ContextProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, BaseContextProvider] = {}

    def register(self, provider: BaseContextProvider) -> None:
        if provider.name in self._providers:
            raise ValueError(f"Context provider '{provider.name}' is already registered.")
        self._providers[provider.name] = provider

    def get(self, name: str) -> BaseContextProvider:
        try:
            return self._providers[name]
        except KeyError as exc:  # pragma: no cover
            raise KeyError(f"Unknown context provider: {name}") from exc

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())

    def fetch(self, name: str, provider_input: ProviderInput) -> ProviderOutput:
        return self.get(name).fetch(provider_input)

    def fetch_all(self, provider_input: ProviderInput) -> list[ProviderOutput]:
        return [provider.fetch(provider_input) for provider in self._providers.values()]
