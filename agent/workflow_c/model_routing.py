from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from agent.workflow_c.failures import redact_secrets
from agent.workflow_c.real_llm import WorkflowLLMCallRecord
from agent.workflow_c.services import WorkflowLLMResult
from agent.workflow_c.state import WorkflowNodeName
from evaluation.model_benchmark.live_clients import DEEPSEEK_BASE_URL, resolve_api_key
from evaluation.model_benchmark.pricing import estimate_request_cost, get_pricing_profile
from llm import LLMClient, LLMConfig, LLMMessage, LLMUsage
from llm.errors import LLMJSONDecodeError, LLMRequestError, LLMResponseError
from llm.openai_compatible import OpenAICompatibleClient
from schemas.common_models import StrictBaseModel


DEFAULT_ROUTING_MATRIX_PATH = "data/evaluation/model_benchmark/node_model_routing_matrix.v1.json"
DEFAULT_MODEL_CONFIGS_PATH = "data/evaluation/model_benchmark/model_configs.deepseek_v4.json"
ROUTED_NODE_NAMES = {
    WorkflowNodeName.fact_extraction,
    WorkflowNodeName.underlying_pain,
    WorkflowNodeName.information_gap,
    WorkflowNodeName.solution_recommendation,
}
DEFAULT_UNBENCHMARKED_ROUTE_ROLE = "default_unbenchmarked"
PRIMARY_ROUTE_ROLE = "primary"
FALLBACK_ROUTE_ROLE = "fallback"
TECHNICAL_FAILURE_REASONS = {
    "timeout",
    "authentication_error",
    "rate_limit",
    "provider_error",
    "network_error",
    "invalid_provider_response",
}


class RoutedNodePolicy(StrictBaseModel):
    node_name: WorkflowNodeName
    route_status: str
    primary_model_config_id: str | None = None
    fallback_model_config_id: str | None = None
    eligible_model_config_ids: list[str]
    selection_reason: str
    policy_version: str


class ModelRuntimeConfig(StrictBaseModel):
    config_id: str
    provider: str
    model: str
    tier: str
    thinking_mode: str
    reasoning_effort: str | None = None
    temperature: float | None = None
    max_tokens: int
    api_key_env: str | None = None
    pricing_profile_id: str | None = None
    enabled: bool = True


class ModelRoutingPolicy(StrictBaseModel):
    routing_version: str
    source_pilot_version: str
    routes_by_node: dict[WorkflowNodeName, RoutedNodePolicy]
    model_configs_by_id: dict[str, ModelRuntimeConfig]
    routed_node_names: list[WorkflowNodeName]
    matrix_path: str
    config_path: str


class ModelRoutingError(Exception):
    pass


class ModelRoutingUnavailableError(ModelRoutingError):
    def __init__(self, node_name: WorkflowNodeName) -> None:
        self.node_name = node_name
        super().__init__(f"Routing unavailable for node {node_name.value}.")


class RoutedWorkflowLLMClient:
    def __init__(
        self,
        *,
        default_client: LLMClient,
        default_config: LLMConfig,
        policy: ModelRoutingPolicy,
        routed_client_factory: Callable[[ModelRuntimeConfig], LLMClient] | None = None,
    ) -> None:
        self.default_client = default_client
        self.default_config = default_config
        self.config = default_config
        self.policy = policy
        self.call_records: list[WorkflowLLMCallRecord] = []
        self._routed_client_factory = routed_client_factory or _build_routed_llm_client
        self._routed_clients: dict[str, LLMClient] = {}

    @property
    def model_routing_enabled(self) -> bool:
        return True

    @property
    def routing_policy_version(self) -> str:
        return self.policy.routing_version

    @property
    def routing_matrix_file(self) -> str:
        return self.policy.matrix_path

    @property
    def model_configs_file(self) -> str:
        return self.policy.config_path

    @property
    def routed_nodes(self) -> list[str]:
        return [node.value for node in self.policy.routed_node_names]

    @property
    def unavailable_routed_nodes(self) -> list[str]:
        return [
            node.value
            for node, route in self.policy.routes_by_node.items()
            if route.route_status == "no_eligible_model"
        ]

    @property
    def fallback_call_count(self) -> int:
        return sum(1 for record in self.call_records if record.route_role == FALLBACK_ROUTE_ROLE)

    @property
    def models_used(self) -> list[str]:
        models: list[str] = []
        seen: set[str] = set()
        for record in self.call_records:
            model = record.response_model or record.selected_model
            if model is None or model in seen:
                continue
            seen.add(model)
            models.append(model)
        return models

    def complete_json_for_node(
        self,
        node_name: WorkflowNodeName,
        messages: list[LLMMessage],
    ) -> WorkflowLLMResult:
        if node_name not in ROUTED_NODE_NAMES:
            return self._complete_with_client(
                client=self.default_client,
                configured_model=self.default_config.model,
                node_name=node_name,
                messages=messages,
                route_role=DEFAULT_UNBENCHMARKED_ROUTE_ROLE,
                routing_enabled=True,
                selected_model_config_id=None,
                selected_provider=self.default_config.provider,
                selected_model=self.default_config.model,
                selected_tier=None,
                thinking_mode=None,
                reasoning_effort=None,
                routing_policy_version=self.policy.routing_version,
                estimated_cost_pricing_profile_id=None,
                fallback_used=False,
                fallback_reason=None,
            )

        route = self.policy.routes_by_node[node_name]
        if route.route_status == "no_eligible_model":
            raise ModelRoutingUnavailableError(node_name)

        primary_config = self.policy.model_configs_by_id[route.primary_model_config_id]
        try:
            return self._complete_with_runtime_config(
                runtime_config=primary_config,
                node_name=node_name,
                messages=messages,
                route_role=PRIMARY_ROUTE_ROLE,
                fallback_used=False,
                fallback_reason=None,
            )
        except Exception as exc:
            reason = _classify_technical_failure(exc)
            if (
                reason is None
                or route.fallback_model_config_id is None
                or route.fallback_model_config_id == route.primary_model_config_id
            ):
                raise
            fallback_config = self.policy.model_configs_by_id[route.fallback_model_config_id]
            return self._complete_with_runtime_config(
                runtime_config=fallback_config,
                node_name=node_name,
                messages=messages,
                route_role=FALLBACK_ROUTE_ROLE,
                fallback_used=True,
                fallback_reason=reason,
            )

    def _complete_with_runtime_config(
        self,
        *,
        runtime_config: ModelRuntimeConfig,
        node_name: WorkflowNodeName,
        messages: list[LLMMessage],
        route_role: str,
        fallback_used: bool,
        fallback_reason: str | None,
    ) -> WorkflowLLMResult:
        client = self._routed_clients.get(runtime_config.config_id)
        if client is None:
            client = self._routed_client_factory(runtime_config)
            self._routed_clients[runtime_config.config_id] = client
        return self._complete_with_client(
            client=client,
            configured_model=runtime_config.model,
            node_name=node_name,
            messages=messages,
            route_role=route_role,
            routing_enabled=True,
            selected_model_config_id=runtime_config.config_id,
            selected_provider=runtime_config.provider,
            selected_model=runtime_config.model,
            selected_tier=runtime_config.tier,
            thinking_mode=runtime_config.thinking_mode,
            reasoning_effort=runtime_config.reasoning_effort,
            routing_policy_version=self.policy.routing_version,
            estimated_cost_pricing_profile_id=runtime_config.pricing_profile_id,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )

    def _complete_with_client(
        self,
        *,
        client: LLMClient,
        configured_model: str,
        node_name: WorkflowNodeName,
        messages: list[LLMMessage],
        route_role: str,
        routing_enabled: bool,
        selected_model_config_id: str | None,
        selected_provider: str | None,
        selected_model: str | None,
        selected_tier: str | None,
        thinking_mode: str | None,
        reasoning_effort: str | None,
        routing_policy_version: str | None,
        estimated_cost_pricing_profile_id: str | None,
        fallback_used: bool,
        fallback_reason: str | None,
    ) -> WorkflowLLMResult:
        sequence = len(self.call_records) + 1
        started_at = datetime.now(UTC)
        serialized_messages = [_serialize_message(message) for message in messages]
        try:
            response = client.complete_json(messages)
        except Exception as exc:
            completed_at = datetime.now(UTC)
            self.call_records.append(
                WorkflowLLMCallRecord(
                    sequence=sequence,
                    node_name=node_name,
                    status="failed",
                    started_at=started_at,
                    completed_at=completed_at,
                    latency_ms=_elapsed_ms(started_at, completed_at),
                    configured_model=configured_model,
                    response_model=None,
                    usage=LLMUsage(),
                    messages=serialized_messages,
                    raw_content=_raw_content_from_error(exc),
                    parsed_json=None,
                    error_type=exc.__class__.__name__,
                    error_message=_safe_error_message(exc),
                    estimated_cost=None,
                    routing_enabled=routing_enabled,
                    selected_model_config_id=selected_model_config_id,
                    selected_provider=selected_provider,
                    selected_model=selected_model,
                    selected_tier=selected_tier,
                    thinking_mode=thinking_mode,
                    reasoning_effort=reasoning_effort,
                    route_role=route_role,
                    fallback_used=fallback_used,
                    fallback_reason=fallback_reason,
                    routing_policy_version=routing_policy_version,
                )
            )
            raise

        estimated_cost = None
        if estimated_cost_pricing_profile_id:
            estimated_cost = estimate_request_cost(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                pricing_profile=get_pricing_profile(estimated_cost_pricing_profile_id),
            )
        completed_at = datetime.now(UTC)
        self.call_records.append(
            WorkflowLLMCallRecord(
                sequence=sequence,
                node_name=node_name,
                status="success",
                started_at=started_at,
                completed_at=completed_at,
                latency_ms=response.latency_ms,
                configured_model=configured_model,
                response_model=response.model,
                usage=response.usage,
                messages=serialized_messages,
                raw_content=response.content,
                parsed_json=response.parsed_json,
                error_type=None,
                error_message=None,
                estimated_cost=estimated_cost,
                routing_enabled=routing_enabled,
                selected_model_config_id=selected_model_config_id,
                selected_provider=selected_provider,
                selected_model=selected_model,
                selected_tier=selected_tier,
                thinking_mode=thinking_mode,
                reasoning_effort=reasoning_effort,
                route_role=route_role,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
                routing_policy_version=routing_policy_version,
            )
        )
        return WorkflowLLMResult(
            content=response.content,
            parsed_json=response.parsed_json,
            model=response.model,
            usage=response.usage,
            latency_ms=response.latency_ms,
        )


def load_model_routing_policy(
    *,
    matrix_path: str | Path = DEFAULT_ROUTING_MATRIX_PATH,
    config_path: str | Path = DEFAULT_MODEL_CONFIGS_PATH,
) -> ModelRoutingPolicy:
    resolved_matrix = _resolve_project_path(matrix_path)
    resolved_config = _resolve_project_path(config_path)

    matrix = _load_json(resolved_matrix)
    config_items = _load_json(resolved_config)
    try:
        model_configs = [ModelRuntimeConfig.model_validate(item) for item in config_items]
    except ValidationError as exc:
        raise ModelRoutingError(f"Invalid model config entry: {exc}") from exc
    model_configs_by_id = {item.config_id: item for item in model_configs}

    routes_by_node: dict[WorkflowNodeName, RoutedNodePolicy] = {}
    for item in matrix["nodes"]:
        node_name = WorkflowNodeName(item["node_name"])
        if node_name not in ROUTED_NODE_NAMES:
            raise ModelRoutingError(f"Unsupported routed node: {node_name.value}")
        route = RoutedNodePolicy(
            node_name=node_name,
            route_status=item["route_status"],
            primary_model_config_id=item.get("primary_model_config_id"),
            fallback_model_config_id=item.get("fallback_model_config_id"),
            eligible_model_config_ids=list(item.get("eligible_model_config_ids", [])),
            selection_reason=item.get("selection_reason", ""),
            policy_version=matrix["matrix_version"],
        )
        _validate_route(route, model_configs_by_id)
        routes_by_node[node_name] = route

    if set(routes_by_node) != ROUTED_NODE_NAMES:
        raise ModelRoutingError(
            "Routing matrix must define exactly the four benchmarked routed nodes."
        )
    for config in model_configs:
        if hasattr(config, "api_key"):
            raise ModelRoutingError(f"Model config {config.config_id} must not contain secret values.")

    return ModelRoutingPolicy(
        routing_version=matrix["matrix_version"],
        source_pilot_version=matrix["matrix_version"],
        routes_by_node=routes_by_node,
        model_configs_by_id=model_configs_by_id,
        routed_node_names=sorted(routes_by_node, key=lambda item: item.value),
        matrix_path=_relative_project_path(resolved_matrix),
        config_path=_relative_project_path(resolved_config),
    )


def format_model_routing_plan(policy: ModelRoutingPolicy) -> str:
    lines = ["Model routing: enabled"]
    for node_name in sorted(ROUTED_NODE_NAMES, key=lambda item: item.value):
        route = policy.routes_by_node[node_name]
        lines.append(f"{node_name.value}:")
        lines.append(f"  primary: {route.primary_model_config_id or 'none'}")
        lines.append(f"  fallback: {route.fallback_model_config_id or 'none'}")
    lines.append("unbenchmarked nodes:")
    lines.append("  existing default model")
    unavailable = [node for node in policy.routed_node_names if policy.routes_by_node[node].route_status == "no_eligible_model"]
    if unavailable:
        lines.append(f"Routing unavailable for: {', '.join(node.value for node in unavailable)}")
    return "\n".join(lines)


def _validate_route(
    route: RoutedNodePolicy,
    model_configs_by_id: dict[str, ModelRuntimeConfig],
) -> None:
    if route.route_status not in {"route_ready", "no_eligible_model"}:
        raise ModelRoutingError(
            f"Node {route.node_name.value} has unsupported route_status={route.route_status}."
        )
    if route.route_status == "no_eligible_model":
        if route.primary_model_config_id is not None or route.fallback_model_config_id is not None:
            raise ModelRoutingError(
                f"Node {route.node_name.value} must not define primary/fallback when route_status=no_eligible_model."
            )
        return
    if route.primary_model_config_id is None:
        raise ModelRoutingError(f"Node {route.node_name.value} must define a primary model config.")
    if route.primary_model_config_id not in model_configs_by_id:
        raise ModelRoutingError(
            f"Node {route.node_name.value} references unknown primary config_id={route.primary_model_config_id}."
        )
    if route.primary_model_config_id not in route.eligible_model_config_ids:
        raise ModelRoutingError(
            f"Node {route.node_name.value} primary config_id={route.primary_model_config_id} is not eligible."
        )
    if route.fallback_model_config_id is not None:
        if route.fallback_model_config_id not in model_configs_by_id:
            raise ModelRoutingError(
                f"Node {route.node_name.value} references unknown fallback config_id={route.fallback_model_config_id}."
            )
        if route.fallback_model_config_id not in route.eligible_model_config_ids:
            raise ModelRoutingError(
                f"Node {route.node_name.value} fallback config_id={route.fallback_model_config_id} is not eligible."
            )
        if route.fallback_model_config_id == route.primary_model_config_id:
            raise ModelRoutingError(
                f"Node {route.node_name.value} cannot use the same config for primary and fallback."
            )


def _build_routed_llm_client(runtime_config: ModelRuntimeConfig) -> LLMClient:
    api_key = resolve_api_key(runtime_config.api_key_env, load_env=True)
    llm_config = LLMConfig(
        provider="openai_compatible",
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL,
        model=runtime_config.model,
        timeout_seconds=90,
        max_retries=0,
        max_tokens=runtime_config.max_tokens,
        temperature=runtime_config.temperature or 0,
    )
    return _DeepSeekRoutedLLMClient(runtime_config=runtime_config, sdk_client=OpenAICompatibleClient(llm_config)._client)


class _DeepSeekRoutedLLMClient:
    def __init__(self, *, runtime_config: ModelRuntimeConfig, sdk_client: Any) -> None:
        self.runtime_config = runtime_config
        self._client = sdk_client

    def list_model_ids(self) -> list[str]:
        models = self._client.models.list()
        return [item.id for item in models.data]

    def complete_text(self, messages, *, temperature=None, max_tokens=None):
        raise AssertionError("Routed workflow client only supports complete_json.")

    def complete_json(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Any:
        from evaluation.model_benchmark.live_clients import _extract_usage  # local import to avoid extra module load
        import json as _json
        import time as _time

        payload: dict[str, Any] = {
            "model": self.runtime_config.model,
            "messages": [{"role": message.role.value, "content": message.content} for message in messages],
            "max_tokens": self.runtime_config.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        if self.runtime_config.thinking_mode == "enabled":
            if self.runtime_config.reasoning_effort is not None:
                payload["reasoning_effort"] = self.runtime_config.reasoning_effort
        else:
            payload["temperature"] = (
                self.runtime_config.temperature if temperature is None else temperature
            )
        payload = {key: value for key, value in payload.items() if value is not None}

        started = _time.perf_counter()
        try:
            response = self._client.chat.completions.create(**payload)
        except Exception as exc:
            raise LLMRequestError(_safe_error_message(exc)) from exc
        latency_ms = max(0, int((_time.perf_counter() - started) * 1000))
        choices = getattr(response, "choices", None)
        if not choices:
            raise LLMResponseError("LLM response did not include choices.")
        first_choice = choices[0]
        message = getattr(first_choice, "message", None)
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise LLMResponseError("LLM response content is empty.")
        content = content.strip()
        try:
            decoded = _json.loads(content)
        except _json.JSONDecodeError as exc:
            raise LLMJSONDecodeError(
                raw_content=content,
                json_error_message=exc.msg,
                json_error_position=exc.pos,
            ) from exc
        if not isinstance(decoded, dict):
            raise LLMResponseError("LLM JSON response must be a JSON object.")
        usage = _extract_usage(getattr(response, "usage", None))
        return WorkflowLLMResult(
            content=content,
            parsed_json=decoded,
            model=getattr(response, "model", self.runtime_config.model),
            usage=usage,
            latency_ms=latency_ms,
        )


def _classify_technical_failure(error: Exception) -> str | None:
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, LLMJSONDecodeError):
        return None
    if isinstance(error, LLMResponseError):
        return "invalid_provider_response"
    if isinstance(error, LLMRequestError):
        message = str(error).casefold()
        if "rate limit" in message or "429" in message:
            return "rate_limit"
        if "auth" in message or "unauthorized" in message or "api key" in message:
            return "authentication_error"
        if "timeout" in message or "timed out" in message:
            return "timeout"
        if "network" in message or "connection" in message or "dns" in message:
            return "network_error"
        return "provider_error"
    return None


def _serialize_message(message: LLMMessage) -> dict[str, str]:
    return {"role": message.role.value, "content": message.content}


def _safe_error_message(error: Exception) -> str:
    message = redact_secrets(str(error) or error.__class__.__name__)
    if len(message) > 1000:
        return f"{message[:997]}..."
    return message


def _raw_content_from_error(error: Exception) -> str | None:
    if isinstance(error, LLMJSONDecodeError):
        return error.raw_content
    return None


def _elapsed_ms(started_at: datetime, completed_at: datetime) -> int:
    return max(0, int((completed_at - started_at).total_seconds() * 1000))


def _resolve_project_path(path: str | Path) -> Path:
    raw = str(path)
    if raw.startswith("http://") or raw.startswith("https://"):
        raise ModelRoutingError("Routing files must not use HTTP URLs.")
    resolved = Path(raw)
    if not resolved.is_absolute():
        resolved = Path.cwd() / resolved
    resolved = resolved.resolve()
    project_root = Path.cwd().resolve()
    try:
        resolved.relative_to(project_root)
    except ValueError as exc:
        raise ModelRoutingError(f"Routing file is outside the project root: {raw}") from exc
    if not resolved.exists():
        raise ModelRoutingError(f"Routing file not found: {raw}")
    return resolved


def _relative_project_path(path: Path) -> str:
    project_root = Path.cwd().resolve()
    try:
        return str(path.resolve().relative_to(project_root))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
