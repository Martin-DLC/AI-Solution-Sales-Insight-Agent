from __future__ import annotations

from llm.base import LLMClient
from llm.config import LLMConfig
from llm.errors import LLMConfigurationError
from llm.openai_compatible import OpenAICompatibleClient


def create_llm_client(config: LLMConfig | None = None) -> LLMClient:
    resolved_config = config or LLMConfig.from_env()
    if resolved_config.provider == "openai_compatible":
        return OpenAICompatibleClient(resolved_config)
    raise LLMConfigurationError(f"Unsupported LLM provider: {resolved_config.provider}")
