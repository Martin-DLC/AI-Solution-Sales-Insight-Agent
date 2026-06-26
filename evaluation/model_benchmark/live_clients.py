from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable

from dotenv import load_dotenv

from agent.workflow_c.failures import redact_secrets
from agent.workflow_c.services import WorkflowJSONClient, WorkflowLLMResult
from agent.workflow_c.state import WorkflowNodeName
from evaluation.model_benchmark.models import ModelBenchmarkConfig, ThinkingMode
from llm.config import LLMConfig
from llm.errors import LLMConfigurationError, LLMJSONDecodeError, LLMRequestError, LLMResponseError
from llm.models import LLMMessage, LLMUsage
from llm.openai_compatible import OpenAICompatibleClient


DEEPSEEK_BASE_URL = "https://api.deepseek.com"


@dataclass
class LiveBenchmarkCallRecord:
    sequence: int
    benchmark_case_id: str
    model_config_id: str
    node_name: WorkflowNodeName
    status: str
    started_at: str
    completed_at: str
    latency_ms: int
    configured_model: str
    response_model: str | None
    usage: LLMUsage
    messages: list[dict[str, str]]
    raw_content: str | None = None
    parsed_json: dict[str, Any] | None = None
    reasoning_content: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    thinking_mode: str | None = None

    def model_dump(self, *, mode: str = "json", exclude: set[str] | None = None) -> dict[str, Any]:
        payload = {
            "sequence": self.sequence,
            "benchmark_case_id": self.benchmark_case_id,
            "model_config_id": self.model_config_id,
            "node_name": self.node_name.value,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "latency_ms": self.latency_ms,
            "configured_model": self.configured_model,
            "response_model": self.response_model,
            "usage": self.usage.model_dump(mode=mode),
            "messages": self.messages,
            "raw_content": self.raw_content,
            "parsed_json": self.parsed_json,
            "reasoning_content": self.reasoning_content,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "thinking_mode": self.thinking_mode,
        }
        if exclude:
            for key in exclude:
                payload.pop(key, None)
        return payload


def create_deepseek_live_client_factory(
    *,
    sdk_client_factory: Callable[[ModelBenchmarkConfig], Any] | None = None,
    load_env: bool = True,
) -> Callable[[ModelBenchmarkConfig, Any], WorkflowJSONClient]:
    def factory(model_config: ModelBenchmarkConfig, benchmark_case: Any) -> DeepSeekBenchmarkClient:
        return DeepSeekBenchmarkClient(
            model_config=model_config,
            benchmark_case_id=benchmark_case.benchmark_case_id,
            sdk_client=_build_sdk_client(
                model_config,
                sdk_client_factory=sdk_client_factory,
                load_env=load_env,
            ),
        )

    return factory


def _build_sdk_client(
    model_config: ModelBenchmarkConfig,
    *,
    sdk_client_factory: Callable[[ModelBenchmarkConfig], Any] | None,
    load_env: bool,
) -> Any:
    if sdk_client_factory is not None:
        return sdk_client_factory(model_config)
    api_key = resolve_api_key(model_config.api_key_env, load_env=load_env)
    llm_config = LLMConfig(
        provider="openai_compatible",
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL,
        model=model_config.model,
        timeout_seconds=90,
        max_retries=0,
        max_tokens=model_config.max_tokens,
        temperature=model_config.temperature or 0,
    )
    return OpenAICompatibleClient(llm_config)._client


def resolve_api_key(api_key_env: str | None, *, load_env: bool) -> str:
    if not api_key_env:
        raise LLMConfigurationError("Live benchmark config is missing api_key_env.")
    if load_env:
        load_dotenv()
    api_key = os.getenv(api_key_env, "").strip()
    if not api_key:
        raise LLMRequestError(f"Live benchmark API key is missing in environment variable {api_key_env}.")
    return api_key


@dataclass
class DeepSeekBenchmarkClient:
    model_config: ModelBenchmarkConfig
    benchmark_case_id: str
    sdk_client: Any
    call_records: list[LiveBenchmarkCallRecord] = field(default_factory=list)

    def complete_json_for_node(
        self,
        node_name: WorkflowNodeName,
        messages: list[LLMMessage],
    ) -> WorkflowLLMResult:
        sequence = len(self.call_records) + 1
        started_at = datetime.now(UTC)
        serialized_messages = [_serialize_message(message) for message in messages]
        request_payload = _build_request_payload(
            model_config=self.model_config,
            serialized_messages=serialized_messages,
        )

        started_perf = time.perf_counter()
        try:
            response = self.sdk_client.chat.completions.create(**request_payload)
        except Exception as exc:
            completed_at = datetime.now(UTC)
            self.call_records.append(
                LiveBenchmarkCallRecord(
                    sequence=sequence,
                    benchmark_case_id=self.benchmark_case_id,
                    model_config_id=self.model_config.config_id,
                    node_name=node_name,
                    status="request_error",
                    started_at=started_at.isoformat(),
                    completed_at=completed_at.isoformat(),
                    latency_ms=max(0, int((completed_at - started_at).total_seconds() * 1000)),
                    configured_model=self.model_config.model,
                    response_model=None,
                    usage=LLMUsage(),
                    messages=serialized_messages,
                    error_type=exc.__class__.__name__,
                    error_message=_safe_error_message(exc),
                    thinking_mode=self.model_config.thinking_mode.value,
                )
            )
            raise LLMRequestError(_safe_error_message(exc)) from exc

        latency_ms = max(0, int((time.perf_counter() - started_perf) * 1000))
        choices = getattr(response, "choices", None)
        if not choices:
            raise LLMRequestError("DeepSeek live response did not include choices.")
        first_choice = choices[0]
        message = getattr(first_choice, "message", None)
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise LLMResponseError("DeepSeek live response content is empty.")
        content = content.strip()
        reasoning_content = getattr(message, "reasoning_content", None)
        usage = _extract_usage(getattr(response, "usage", None))
        try:
            parsed_json = json.loads(content)
        except json.JSONDecodeError as exc:
            completed_at = datetime.now(UTC)
            self.call_records.append(
                LiveBenchmarkCallRecord(
                    sequence=sequence,
                    benchmark_case_id=self.benchmark_case_id,
                    model_config_id=self.model_config.config_id,
                    node_name=node_name,
                    status="invalid_json",
                    started_at=started_at.isoformat(),
                    completed_at=completed_at.isoformat(),
                    latency_ms=latency_ms,
                    configured_model=self.model_config.model,
                    response_model=getattr(response, "model", self.model_config.model),
                    usage=usage,
                    messages=serialized_messages,
                    raw_content=content,
                    parsed_json=None,
                    reasoning_content=reasoning_content if isinstance(reasoning_content, str) else None,
                    error_type="LLMJSONDecodeError",
                    error_message=f"LLM JSON response is not valid JSON at position {exc.pos}: {exc.msg}.",
                    thinking_mode=self.model_config.thinking_mode.value,
                )
            )
            raise LLMJSONDecodeError(
                raw_content=content,
                json_error_message=exc.msg,
                json_error_position=exc.pos,
            ) from exc
        if not isinstance(parsed_json, dict):
            raise LLMResponseError("DeepSeek live JSON response must be a JSON object.")

        completed_at = datetime.now(UTC)
        self.call_records.append(
            LiveBenchmarkCallRecord(
                sequence=sequence,
                benchmark_case_id=self.benchmark_case_id,
                model_config_id=self.model_config.config_id,
                node_name=node_name,
                status="success",
                started_at=started_at.isoformat(),
                completed_at=completed_at.isoformat(),
                latency_ms=latency_ms,
                configured_model=self.model_config.model,
                response_model=getattr(response, "model", self.model_config.model),
                usage=usage,
                messages=serialized_messages,
                raw_content=content,
                parsed_json=parsed_json,
                reasoning_content=reasoning_content if isinstance(reasoning_content, str) else None,
                thinking_mode=self.model_config.thinking_mode.value,
            )
        )
        return WorkflowLLMResult(
            content=content,
            parsed_json=parsed_json,
            model=getattr(response, "model", self.model_config.model),
            usage=usage,
            latency_ms=latency_ms,
        )


def _build_request_payload(
    *,
    model_config: ModelBenchmarkConfig,
    serialized_messages: list[dict[str, str]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model_config.model,
        "messages": serialized_messages,
        "max_tokens": model_config.max_tokens,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    if model_config.thinking_mode is ThinkingMode.enabled:
        if model_config.reasoning_effort is not None:
            payload["reasoning_effort"] = model_config.reasoning_effort.value
    else:
        payload["temperature"] = model_config.temperature
    return {key: value for key, value in payload.items() if value is not None}


def _extract_usage(raw_usage: Any) -> LLMUsage:
    if raw_usage is None:
        return LLMUsage()
    return LLMUsage(
        prompt_tokens=getattr(raw_usage, "prompt_tokens", None),
        completion_tokens=getattr(raw_usage, "completion_tokens", None),
        total_tokens=getattr(raw_usage, "total_tokens", None),
    )


def _serialize_message(message: LLMMessage) -> dict[str, str]:
    return {"role": message.role.value, "content": message.content}


def _safe_error_message(error: Exception) -> str:
    message = redact_secrets(str(error) or error.__class__.__name__)
    if len(message) > 1000:
        return f"{message[:997]}..."
    return message
