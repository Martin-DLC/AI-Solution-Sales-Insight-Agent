from __future__ import annotations


class LLMConfigurationError(Exception):
    """Raised when LLM configuration is missing or invalid."""


class LLMRequestError(Exception):
    """Raised when an LLM request fails before a valid response is available."""


class LLMResponseError(Exception):
    """Raised when an LLM response is present but unusable."""
