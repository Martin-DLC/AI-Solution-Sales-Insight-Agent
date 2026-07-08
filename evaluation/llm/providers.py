from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from llm.config import LLMConfig
from llm.factory import create_llm_client


@dataclass(frozen=True)
class SolutionInsightProviderSpec:
    provider_name: str
    default_model: str | None
    api_key_env: str | None = None
    model_env: str | None = None
    base_url: str | None = None
    base_url_env: str | None = None

    def configured_model(self) -> str | None:
        if self.model_env:
            value = os.getenv(self.model_env, "").strip()
            if value:
                return value
        return self.default_model

    def configured_base_url(self) -> str | None:
        if self.base_url_env:
            value = os.getenv(self.base_url_env, "").strip()
            if value:
                return value
        return self.base_url

    def has_api_key(self) -> bool:
        if not self.api_key_env:
            return True
        return bool(os.getenv(self.api_key_env, "").strip())


PROVIDER_SPECS: dict[str, SolutionInsightProviderSpec] = {
    "deterministic": SolutionInsightProviderSpec(
        provider_name="deterministic",
        default_model="local_template",
    ),
    "deepseek": SolutionInsightProviderSpec(
        provider_name="deepseek",
        default_model="deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
        model_env="DEEPSEEK_MODEL",
        base_url="https://api.deepseek.com",
        base_url_env="DEEPSEEK_BASE_URL",
    ),
    "qwen": SolutionInsightProviderSpec(
        provider_name="qwen",
        default_model="qwen-plus",
        api_key_env="QWEN_API_KEY",
        model_env="QWEN_MODEL",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        base_url_env="QWEN_BASE_URL",
    ),
    "glm": SolutionInsightProviderSpec(
        provider_name="glm",
        default_model="glm-4.5-air",
        api_key_env="GLM_API_KEY",
        model_env="GLM_MODEL",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        base_url_env="GLM_BASE_URL",
    ),
}


def get_provider_spec(provider_name: str) -> SolutionInsightProviderSpec:
    try:
        return PROVIDER_SPECS[provider_name]
    except KeyError as exc:
        raise ValueError(f"Unknown provider {provider_name!r}.") from exc


def provider_is_available(provider_name: str) -> bool:
    spec = get_provider_spec(provider_name)
    return spec.has_api_key()


def create_provider_client(provider_name: str, *, client_factory: Callable[[LLMConfig], object] | None = None) -> object:
    spec = get_provider_spec(provider_name)
    if provider_name == "deterministic":
        raise ValueError("Deterministic provider does not create a live LLM client.")
    api_key = os.getenv(spec.api_key_env or "", "").strip()
    if not api_key:
        raise ValueError(f"Missing API key for provider {provider_name!r}.")
    model = spec.configured_model()
    base_url = spec.configured_base_url()
    if not model or not base_url:
        raise ValueError(f"Provider {provider_name!r} is missing model or base_url configuration.")
    config = LLMConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    factory = client_factory or create_llm_client
    return factory(config)
