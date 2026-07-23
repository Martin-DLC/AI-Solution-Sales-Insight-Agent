from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import Field

from agent.model_providers.base import ModelProviderResponse
from agent.recovery.decision import RecoveryDecisionEngine
from agent.recovery.models import ErrorType, RecoveryAction
from schemas.common_models import StrictBaseModel


DEFAULT_MAAS_PROVIDERS_PATH = Path("config/maas_providers.yaml")
DEFAULT_BOUNDARY_NOTE = (
    "skipped and dry-run results are not model quality results; estimated cost is not real billing; "
    "not_verified providers are not completed integrations."
)


class OpenAICompatibleProviderConfig(StrictBaseModel):
    provider_name: str
    adapter_type: str = "openai_compatible"
    model_name: str = "to_be_configured"
    model_id: str | None = None
    base_url: str | None = None
    base_url_candidate: str | None = None
    api_key_env: str
    timeout_seconds: int = 30
    max_retries: int = 0
    default_headers: dict[str, str] = Field(default_factory=dict)
    supports_tool_calling: bool = False
    supports_structured_output: bool = True
    supports_streaming: bool = False
    supports_long_context: bool = False
    cost_profile: str = "not_configured"
    latency_profile: str = "not_verified"
    data_policy: str = "not_verified"
    verification_status: str = "not_verified"
    notes: str | None = None

    @property
    def resolved_model_name(self) -> str:
        return self.model_id or self.model_name

    @property
    def resolved_base_url(self) -> str | None:
        return self.base_url or self.base_url_candidate


class MaaSProviderUsage(StrictBaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class MaaSProviderResult(StrictBaseModel):
    provider_name: str
    model_name: str
    adapter_type: str = "openai_compatible"
    verification_status: str = "not_verified"
    status: str
    output_text: str | None = None
    response_preview: str | None = None
    latency_ms: int = 0
    usage: MaaSProviderUsage = Field(default_factory=MaaSProviderUsage)
    usage_available: bool = False
    estimated_cost: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    schema_parse_status: str = "not_attempted"
    recommended_recovery_action: str | None = None
    should_retry: bool = False
    should_fallback: bool = False
    api_key_env: str | None = None
    api_key_present: bool = False
    dry_run: bool = True
    boundary_note: str = DEFAULT_BOUNDARY_NOTE


HTTPClient = Callable[[dict[str, Any]], dict[str, Any]]


class OpenAICompatibleModelProvider:
    def __init__(
        self,
        *,
        provider_name: str,
        model_name: str | None = None,
        model_id: str | None = None,
        base_url: str | None = None,
        base_url_candidate: str | None = None,
        api_key_env: str,
        timeout_seconds: int = 30,
        max_retries: int = 0,
        default_headers: dict[str, str] | None = None,
        supports_tool_calling: bool = False,
        supports_structured_output: bool = True,
        supports_streaming: bool = False,
        supports_long_context: bool = False,
        cost_profile: str = "not_configured",
        latency_profile: str = "not_verified",
        data_policy: str = "not_verified",
        verification_status: str = "not_verified",
        http_client: HTTPClient | None = None,
        recovery_engine: RecoveryDecisionEngine | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.model_name = model_id or model_name or "to_be_configured"
        self.model_id = model_id
        self.base_url = base_url
        self.base_url_candidate = base_url_candidate
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.default_headers = default_headers or {}
        self.supports_tool_calling = supports_tool_calling
        self.supports_structured_output = supports_structured_output
        self.supports_streaming = supports_streaming
        self.supports_long_context = supports_long_context
        self.cost_profile = cost_profile
        self.latency_profile = latency_profile
        self.data_policy = data_policy
        self.verification_status = verification_status
        self._http_client = http_client
        self._recovery_engine = recovery_engine or RecoveryDecisionEngine()

    @classmethod
    def from_config(
        cls,
        config: OpenAICompatibleProviderConfig | dict[str, Any],
        *,
        http_client: HTTPClient | None = None,
    ) -> OpenAICompatibleModelProvider:
        resolved = (
            config
            if isinstance(config, OpenAICompatibleProviderConfig)
            else OpenAICompatibleProviderConfig.model_validate(config)
        )
        return cls(
            provider_name=resolved.provider_name,
            model_name=resolved.model_name,
            model_id=resolved.model_id,
            base_url=resolved.base_url,
            base_url_candidate=resolved.base_url_candidate,
            api_key_env=resolved.api_key_env,
            timeout_seconds=resolved.timeout_seconds,
            max_retries=resolved.max_retries,
            default_headers=resolved.default_headers,
            supports_tool_calling=resolved.supports_tool_calling,
            supports_structured_output=resolved.supports_structured_output,
            supports_streaming=resolved.supports_streaming,
            supports_long_context=resolved.supports_long_context,
            cost_profile=resolved.cost_profile,
            latency_profile=resolved.latency_profile,
            data_policy=resolved.data_policy,
            verification_status=resolved.verification_status,
            http_client=http_client,
        )

    @property
    def api_key_present(self) -> bool:
        return bool(os.getenv(self.api_key_env, "").strip())

    def health_check(self) -> bool:
        return self.api_key_present and self.verification_status != "deprecated"

    def smoke_test(self, *, dry_run: bool = True, prompt: str = "ping") -> MaaSProviderResult:
        return self._run(prompt=prompt, dry_run=dry_run)

    def generate(self, prompt: str, **kwargs: Any) -> ModelProviderResponse:
        result = self._run(prompt=prompt, dry_run=bool(kwargs.get("dry_run", True)))
        parsed = result.model_dump(mode="json")
        content = result.output_text or json.dumps(parsed, ensure_ascii=False, sort_keys=True)
        return ModelProviderResponse(
            provider_name=self.provider_name,
            model_name=self.model_name,
            content=content,
            parsed_json=parsed,
            input_tokens=result.usage.prompt_tokens or 0,
            output_tokens=result.usage.completion_tokens or 0,
            estimated_cost=result.estimated_cost,
        )

    def estimate_cost(self, input_text: str, output_text: str) -> str | None:
        return None

    def _run(self, *, prompt: str, dry_run: bool) -> MaaSProviderResult:
        if dry_run:
            return self._result(
                status="skipped_dry_run",
                dry_run=True,
                schema_parse_status="not_attempted",
                recommended_recovery_action=RecoveryAction.fallback.value,
                should_fallback=True,
            )
        if not self.api_key_present:
            return self._error_result(
                status="skipped_missing_api_key",
                error_type=ErrorType.model_unavailable,
                error_message=f"Missing API key env var: {self.api_key_env}",
                dry_run=False,
                force_fallback=True,
            )
        if self._http_client is None:
            return self._error_result(
                status="skipped_live_call_disabled",
                error_type=ErrorType.model_unavailable,
                error_message="Live API calls require an injected HTTP client.",
                dry_run=False,
                force_fallback=True,
            )

        started = time.monotonic()
        try:
            payload = self._http_client(
                {
                    "provider_name": self.provider_name,
                    "model_name": self.model_name,
                    "base_url": self.base_url,
                    "base_url_candidate": self.base_url_candidate,
                    "prompt": prompt,
                    "timeout_seconds": self.timeout_seconds,
                    "max_retries": self.max_retries,
                    "default_headers": dict(self.default_headers),
                }
            )
            latency_ms = _elapsed_ms(started)
            output_text = str(payload.get("output_text") or payload.get("content") or "")
            parsed_json = payload.get("parsed_json")
            schema_parse_status = "valid" if isinstance(parsed_json, dict) and parsed_json else "invalid"
            if schema_parse_status == "invalid":
                return self._error_result(
                    status="failed",
                    error_type=ErrorType.model_schema_invalid,
                    error_message="Provider response did not include a valid parsed_json object.",
                    latency_ms=latency_ms,
                    output_text=output_text,
                    response_preview=_preview(output_text),
                    dry_run=False,
                )
            usage = _coerce_usage(payload.get("usage"))
            return self._result(
                status="success",
                output_text=output_text,
                response_preview=_preview(output_text),
                latency_ms=int(payload.get("latency_ms") or latency_ms),
                usage=usage,
                usage_available=usage.total_tokens is not None,
                estimated_cost=None,
                schema_parse_status="valid",
                recommended_recovery_action=None,
                dry_run=False,
            )
        except TimeoutError as exc:
            return self._error_result(
                status="failed",
                error_type=ErrorType.model_timeout,
                error_message=_safe_error_message(exc),
                latency_ms=_elapsed_ms(started),
                dry_run=False,
            )
        except ConnectionError as exc:
            return self._error_result(
                status="failed",
                error_type=ErrorType.model_unavailable,
                error_message=_safe_error_message(exc),
                latency_ms=_elapsed_ms(started),
                dry_run=False,
            )
        except Exception as exc:
            if _looks_like_provider_unavailable(exc):
                error_type = ErrorType.model_unavailable
            else:
                error_type = ErrorType.unknown_error
            return self._error_result(
                status="failed",
                error_type=error_type,
                error_message=_safe_error_message(exc),
                latency_ms=_elapsed_ms(started),
                dry_run=False,
            )

    def _error_result(
        self,
        *,
        status: str,
        error_type: ErrorType,
        error_message: str,
        latency_ms: int = 0,
        output_text: str | None = None,
        response_preview: str | None = None,
        dry_run: bool,
        force_fallback: bool = False,
    ) -> MaaSProviderResult:
        if force_fallback:
            action = RecoveryAction.fallback
            should_retry = False
        else:
            decision = self._recovery_engine.decide(error_type=error_type, current_retry_count=0)
            action = decision.decision
            should_retry = decision.retry_recommended
        return self._result(
            status=status,
            output_text=output_text,
            response_preview=response_preview,
            latency_ms=latency_ms,
            error_type=error_type.value,
            error_message=error_message,
            schema_parse_status="invalid" if error_type is ErrorType.model_schema_invalid else "not_attempted",
            recommended_recovery_action=action.value,
            should_retry=should_retry,
            should_fallback=force_fallback or action is RecoveryAction.fallback,
            dry_run=dry_run,
        )

    def _result(
        self,
        *,
        status: str,
        output_text: str | None = None,
        response_preview: str | None = None,
        latency_ms: int = 0,
        usage: MaaSProviderUsage | None = None,
        usage_available: bool = False,
        estimated_cost: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        schema_parse_status: str,
        recommended_recovery_action: str | None,
        should_retry: bool = False,
        should_fallback: bool = False,
        dry_run: bool,
    ) -> MaaSProviderResult:
        return MaaSProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            verification_status=self.verification_status,
            status=status,
            output_text=output_text,
            response_preview=response_preview,
            latency_ms=latency_ms,
            usage=usage or MaaSProviderUsage(),
            usage_available=usage_available,
            estimated_cost=estimated_cost,
            error_type=error_type,
            error_message=error_message,
            schema_parse_status=schema_parse_status,
            recommended_recovery_action=recommended_recovery_action,
            should_retry=should_retry,
            should_fallback=should_fallback,
            api_key_env=self.api_key_env,
            api_key_present=self.api_key_present,
            dry_run=dry_run,
        )


def load_maas_provider_configs(path: str | Path = DEFAULT_MAAS_PROVIDERS_PATH) -> list[OpenAICompatibleProviderConfig]:
    return [
        OpenAICompatibleProviderConfig.model_validate(item)
        for item in _parse_provider_yaml(Path(path).read_text(encoding="utf-8"))
    ]


def get_maas_provider_config(
    provider_name: str,
    path: str | Path = DEFAULT_MAAS_PROVIDERS_PATH,
) -> OpenAICompatibleProviderConfig:
    for config in load_maas_provider_configs(path):
        if config.provider_name == provider_name:
            return config
    raise KeyError(f"Unknown MaaS provider: {provider_name}")


def build_openai_compatible_provider(
    provider_name: str,
    *,
    path: str | Path = DEFAULT_MAAS_PROVIDERS_PATH,
    model_name: str | None = None,
    http_client: HTTPClient | None = None,
) -> OpenAICompatibleModelProvider:
    config = get_maas_provider_config(provider_name, path)
    if model_name:
        config = config.model_copy(update={"model_name": model_name})
    return OpenAICompatibleModelProvider.from_config(config, http_client=http_client)


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
    if value.isdigit():
        return int(value)
    if value.startswith("{") and value.endswith("}"):
        return {}
    return value.strip('"').strip("'")


def _coerce_usage(value: Any) -> MaaSProviderUsage:
    if not isinstance(value, dict):
        return MaaSProviderUsage()
    return MaaSProviderUsage(
        prompt_tokens=_optional_int(value.get("prompt_tokens")),
        completion_tokens=_optional_int(value.get("completion_tokens")),
        total_tokens=_optional_int(value.get("total_tokens")),
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


def _preview(value: str) -> str:
    return value[:240]


def _safe_error_message(error: Exception) -> str:
    message = str(error).strip() or error.__class__.__name__
    return message.splitlines()[0][:240]


def _looks_like_provider_unavailable(error: Exception) -> bool:
    text = f"{error.__class__.__name__} {error}".casefold()
    return any(marker in text for marker in ("5xx", "503", "502", "500", "unavailable", "provider_error"))
