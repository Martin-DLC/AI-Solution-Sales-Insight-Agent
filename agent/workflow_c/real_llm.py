from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from agent.workflow_c.failures import redact_secrets
from agent.workflow_c.services import WorkflowLLMResult
from agent.workflow_c.state import WorkflowNodeName
from llm import LLMClient, LLMConfig, LLMMessage, LLMUsage
from llm.errors import LLMJSONDecodeError
from schemas.common_models import StrictBaseModel


class WorkflowLLMCallRecord(StrictBaseModel):
    sequence: int
    node_name: WorkflowNodeName
    status: str
    started_at: datetime
    completed_at: datetime
    latency_ms: int
    configured_model: str
    response_model: str | None = None
    usage: LLMUsage
    messages: list[dict[str, str]]
    raw_content: str | None = None
    parsed_json: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None
    estimated_cost: Decimal | None = None
    routing_enabled: bool = False
    selected_model_config_id: str | None = None
    selected_provider: str | None = None
    selected_model: str | None = None
    selected_tier: str | None = None
    thinking_mode: str | None = None
    reasoning_effort: str | None = None
    route_role: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    routing_policy_version: str | None = None


class RealWorkflowLLMClient:
    def __init__(self, llm_client: LLMClient, config: LLMConfig) -> None:
        self.llm_client = llm_client
        self.config = config
        self.call_records: list[WorkflowLLMCallRecord] = []

    def complete_json_for_node(
        self,
        node_name: WorkflowNodeName,
        messages: list[LLMMessage],
    ) -> WorkflowLLMResult:
        sequence = len(self.call_records) + 1
        started_at = datetime.now(UTC)
        serialized_messages = [_serialize_message(message) for message in messages]
        try:
            response = self.llm_client.complete_json(messages)
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
                    configured_model=self.config.model,
                    response_model=None,
                    usage=LLMUsage(),
                    messages=serialized_messages,
                    raw_content=_raw_content_from_error(exc),
                    parsed_json=None,
                    error_type=exc.__class__.__name__,
                    error_message=_safe_error_message(exc),
                )
            )
            raise

        completed_at = datetime.now(UTC)
        self.call_records.append(
            WorkflowLLMCallRecord(
                sequence=sequence,
                node_name=node_name,
                status="success",
                started_at=started_at,
                completed_at=completed_at,
                latency_ms=response.latency_ms,
                configured_model=self.config.model,
                response_model=response.model,
                usage=response.usage,
                messages=serialized_messages,
                raw_content=response.content,
                parsed_json=response.parsed_json,
                error_type=None,
                error_message=None,
            )
        )
        return WorkflowLLMResult(
            content=response.content,
            parsed_json=response.parsed_json,
            model=response.model,
            usage=response.usage,
            latency_ms=response.latency_ms,
        )


def _serialize_message(message: LLMMessage) -> dict[str, str]:
    return {
        "role": message.role.value,
        "content": message.content,
    }


def _elapsed_ms(started_at: datetime, completed_at: datetime) -> int:
    return max(0, int((completed_at - started_at).total_seconds() * 1000))


def _safe_error_message(error: Exception) -> str:
    message = redact_secrets(str(error) or error.__class__.__name__)
    if len(message) > 1000:
        return f"{message[:997]}..."
    return message


def _raw_content_from_error(error: Exception) -> str | None:
    if isinstance(error, LLMJSONDecodeError):
        return error.raw_content
    return None
