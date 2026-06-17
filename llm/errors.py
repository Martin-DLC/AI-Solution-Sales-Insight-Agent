from __future__ import annotations


class LLMConfigurationError(Exception):
    """Raised when LLM configuration is missing or invalid."""


class LLMRequestError(Exception):
    """Raised when an LLM request fails before a valid response is available."""


class LLMResponseError(Exception):
    """Raised when an LLM response is present but unusable."""


class LLMJSONDecodeError(LLMResponseError):
    """Raised when JSON mode returns content that cannot be parsed as JSON."""

    def __init__(
        self,
        *,
        raw_content: str,
        json_error_message: str,
        json_error_position: int,
    ) -> None:
        self.raw_content = raw_content
        self.content_length = len(raw_content)
        self.json_error_message = json_error_message
        self.json_error_position = json_error_position
        super().__init__(
            "LLM JSON response is not valid JSON "
            f"at position {json_error_position}: {json_error_message}."
        )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"content_length={self.content_length!r}, "
            f"json_error_message={self.json_error_message!r}, "
            f"json_error_position={self.json_error_position!r})"
        )
