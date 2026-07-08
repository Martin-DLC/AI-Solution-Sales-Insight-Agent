from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import Field

from schemas.common_models import StrictBaseModel


ProviderStatus = Literal["success", "skipped", "failed"]
ProviderType = Literal["crm", "ticket", "bi", "knowledge"]


class ProviderInput(StrictBaseModel):
    company_id: str | None = None
    industry: str | None = None
    current_systems: list[str] = Field(default_factory=list)
    request_id: str | None = None


class ProviderOutput(StrictBaseModel):
    provider_name: str
    provider_type: str
    status: ProviderStatus
    data: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    error_summary: str | None = None
    elapsed_ms: int = 0
    mock_data: bool = True
    context_source: str = "mcp_mock"


class BaseContextProvider(ABC):
    name: str
    provider_type: ProviderType
    version: str = "v0.3"
    context_source: str = "mcp_mock"
    mock_data: bool = True

    def is_available(self) -> bool:
        return True

    def fetch(self, provider_input: ProviderInput) -> ProviderOutput:
        started_at = time.perf_counter()
        if not self.is_available():
            return self._build_output(
                status="skipped",
                data=None,
                warnings=["provider_unavailable"],
                error_summary=None,
                started_at=started_at,
            )

        try:
            status, data, warnings, error_summary = self._fetch(provider_input)
        except Exception as exc:  # pragma: no cover - covered through registry integration
            return self._build_output(
                status="failed",
                data=None,
                warnings=[],
                error_summary=_safe_error_summary(exc),
                started_at=started_at,
            )

        return self._build_output(
            status=status,
            data=data,
            warnings=warnings,
            error_summary=error_summary,
            started_at=started_at,
        )

    @abstractmethod
    def _fetch(
        self,
        provider_input: ProviderInput,
    ) -> tuple[ProviderStatus, dict[str, Any] | None, list[str], str | None]:
        raise NotImplementedError

    def _build_output(
        self,
        *,
        status: ProviderStatus,
        data: dict[str, Any] | None,
        warnings: list[str],
        error_summary: str | None,
        started_at: float,
    ) -> ProviderOutput:
        elapsed_ms = max(0, int((time.perf_counter() - started_at) * 1000))
        return ProviderOutput(
            provider_name=self.name,
            provider_type=self.provider_type,
            status=status,
            data=data,
            warnings=warnings,
            error_summary=error_summary,
            elapsed_ms=elapsed_ms,
            mock_data=self.mock_data,
            context_source=self.context_source,
        )


def _safe_error_summary(error: Exception) -> str:
    message = str(error).strip() or error.__class__.__name__
    return f"{error.__class__.__name__}: {message.splitlines()[0][:240]}"
