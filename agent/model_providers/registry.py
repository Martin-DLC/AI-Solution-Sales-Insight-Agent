from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.model_providers.base import BaseModelProvider
from agent.model_providers.mock import MockModelProvider


DEFAULT_MODEL_PROVIDERS_PATH = Path("config/model_providers.yaml")


class ModelProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, BaseModelProvider] = {}

    def register(self, provider: BaseModelProvider) -> None:
        if provider.provider_name in self._providers:
            raise ValueError(f"Provider already registered: {provider.provider_name}")
        self._providers[provider.provider_name] = provider

    def get(self, provider_name: str) -> BaseModelProvider:
        try:
            return self._providers[provider_name]
        except KeyError as exc:
            raise KeyError(f"Unknown provider: {provider_name}") from exc

    def list_providers(self) -> list[str]:
        return list(self._providers)

    def select_primary(self) -> BaseModelProvider:
        for provider in self._providers.values():
            if provider.health_check():
                return provider
        raise RuntimeError("No healthy model provider is available.")

    def select_fallback(self, primary_provider: str) -> BaseModelProvider | None:
        for provider_name, provider in self._providers.items():
            if provider_name != primary_provider and provider.health_check():
                return provider
        return None

    def health_check_all(self) -> dict[str, bool]:
        return {name: provider.health_check() for name, provider in self._providers.items()}


def load_model_provider_configs(path: str | Path = DEFAULT_MODEL_PROVIDERS_PATH) -> list[dict[str, Any]]:
    return _parse_provider_yaml(Path(path).read_text(encoding="utf-8"))


def build_default_registry(path: str | Path = DEFAULT_MODEL_PROVIDERS_PATH) -> ModelProviderRegistry:
    registry = ModelProviderRegistry()
    for config in load_model_provider_configs(path):
        if config.get("provider_type") == "mock":
            registry.register(
                MockModelProvider(
                    provider_name=str(config["provider_name"]),
                    model_name=str(config["model_name"]),
                )
            )
    return registry


def _parse_provider_yaml(content: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line == "providers:":
            continue
        if line.startswith("- "):
            if current is not None:
                items.append(current)
            current = {}
            line = line[2:].strip()
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        current[key.strip()] = _parse_scalar(value.strip())
    if current is not None:
        items.append(current)
    return items


def _parse_scalar(value: str) -> Any:
    if value.casefold() == "true":
        return True
    if value.casefold() == "false":
        return False
    return value.strip('"').strip("'")
