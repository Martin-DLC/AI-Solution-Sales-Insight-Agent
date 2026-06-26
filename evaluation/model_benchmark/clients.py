from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from pydantic import Field, field_validator, model_validator

from agent.workflow_c.state import WorkflowNodeName
from agent.workflow_c.services import WorkflowJSONClient, WorkflowLLMResult
from llm.errors import LLMRequestError
from llm.models import LLMMessage, LLMUsage
from schemas.common_models import StrictBaseModel

from evaluation.model_benchmark.models import ModelBenchmarkConfig, ModelBenchmarkConfigCatalog


class BenchmarkClientFactory(Protocol):
    def __call__(
        self,
        model_config: ModelBenchmarkConfig,
        benchmark_case: Any,
    ) -> WorkflowJSONClient:
        ...


class ReplayBenchmarkRecord(StrictBaseModel):
    benchmark_case_id: str
    model_config_id: str
    node_name: WorkflowNodeName
    raw_response: str | None = None
    parsed_response: dict[str, Any] | None = None
    latency_ms: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    request_error: bool = False
    error_type: str | None = None
    error_message: str | None = None

    @field_validator("benchmark_case_id", "model_config_id")
    @classmethod
    def text_fields_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("Replay record fields cannot be empty.")
        return value

    @field_validator("latency_ms")
    @classmethod
    def latency_must_not_be_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Replay record latency must be zero or greater.")
        return value

    @field_validator("prompt_tokens", "completion_tokens", "total_tokens")
    @classmethod
    def token_counts_must_not_be_negative(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("Replay token counts must be zero or greater.")
        return value

    @field_validator("error_message")
    @classmethod
    def error_message_must_be_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value) > 500:
            return value[:497] + "..."
        return value

    @model_validator(mode="after")
    def validate_record(self) -> "ReplayBenchmarkRecord":
        if self.request_error and not self.error_message:
            raise ValueError("Replay request error records must include an error_message.")
        if self.request_error and self.parsed_response is not None:
            raise ValueError("Replay request error records must not include parsed_response.")
        if self.request_error and self.raw_response is not None:
            raise ValueError("Replay request error records must not include raw_response.")
        if not self.request_error and self.parsed_response is None and self.raw_response is None:
            raise ValueError("Replay records must include raw_response or parsed_response.")
        if self.parsed_response is not None and not isinstance(self.parsed_response, dict):
            raise ValueError("Replay parsed_response must be a JSON object.")
        return self


class ReplayBenchmarkCallRecord(StrictBaseModel):
    sequence: int
    benchmark_case_id: str
    model_config_id: str
    node_name: WorkflowNodeName
    status: str
    started_at: str
    completed_at: str
    latency_ms: int
    configured_model: str
    response_model: str | None = None
    usage: LLMUsage
    messages: list[dict[str, str]]
    raw_content: str | None = None
    parsed_json: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None

    @field_validator("benchmark_case_id", "model_config_id", "configured_model", "status")
    @classmethod
    def text_fields_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("Replay call record text fields cannot be empty.")
        return value

    @field_validator("error_message")
    @classmethod
    def error_message_must_be_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value) > 500:
            return value[:497] + "..."
        return value


def load_model_benchmark_configs(path: str | Path) -> list[ModelBenchmarkConfig]:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    if file_path.suffix.lower() == ".jsonl":
        configs = [
            ModelBenchmarkConfig.model_validate(json.loads(line))
            for line in text.splitlines()
            if line.strip()
        ]
    else:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "configs" in parsed:
            parsed = parsed["configs"]
        if not isinstance(parsed, list):
            raise ValueError("Model benchmark config file must contain a JSON array or JSONL records.")
        configs = [ModelBenchmarkConfig.model_validate(item) for item in parsed]

    config_ids = [config.config_id for config in configs]
    if len(config_ids) != len(set(config_ids)):
        raise ValueError("Model benchmark config IDs must be unique.")
    if not any(config.enabled for config in configs):
        raise ValueError("Model benchmark config file must include at least one enabled config.")
    return configs


def load_replay_records(path: str | Path) -> list[ReplayBenchmarkRecord]:
    file_path = Path(path)
    records: list[ReplayBenchmarkRecord] = []
    seen: set[tuple[str, str, WorkflowNodeName]] = set()
    for line_number, raw_line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        data = json.loads(raw_line)
        record = ReplayBenchmarkRecord.model_validate(data)
        key = (record.benchmark_case_id, record.model_config_id, record.node_name)
        if key in seen:
            raise ValueError(f"Duplicate replay record for {key}.")
        seen.add(key)
        records.append(record)
    return records


def index_replay_records(
    records: list[ReplayBenchmarkRecord],
) -> dict[tuple[str, str, WorkflowNodeName], ReplayBenchmarkRecord]:
    indexed: dict[tuple[str, str, WorkflowNodeName], ReplayBenchmarkRecord] = {}
    for record in records:
        key = (record.benchmark_case_id, record.model_config_id, record.node_name)
        if key in indexed:
            raise ValueError(f"Duplicate replay record for {key}.")
        indexed[key] = record
    return indexed


def create_replay_client_factory(
    *,
    replay_records: list[ReplayBenchmarkRecord],
) -> Callable[[ModelBenchmarkConfig, Any], ReplayBenchmarkClient]:
    indexed = index_replay_records(replay_records)

    def factory(
        model_config: ModelBenchmarkConfig,
        benchmark_case: Any,
    ) -> ReplayBenchmarkClient:
        return ReplayBenchmarkClient(
            model_config=model_config,
            benchmark_case_id=benchmark_case.benchmark_case_id,
            records=indexed,
        )

    return factory


@dataclass
class ReplayBenchmarkClient:
    model_config: ModelBenchmarkConfig
    benchmark_case_id: str
    records: dict[tuple[str, str, WorkflowNodeName], ReplayBenchmarkRecord]
    call_records: list[ReplayBenchmarkCallRecord] = field(default_factory=list)

    def complete_json_for_node(
        self,
        node_name: WorkflowNodeName,
        messages: list[LLMMessage],
    ) -> WorkflowLLMResult:
        key = (self.benchmark_case_id, self.model_config.config_id, node_name)
        record = self.records.get(key)
        sequence = len(self.call_records) + 1
        started_at = "replay-start"
        completed_at = "replay-end"
        if record is None:
            error_message = (
                f"Replay response missing for benchmark_case_id={self.benchmark_case_id}, "
                f"model_config_id={self.model_config.config_id}, node_name={node_name.value}."
            )
            self.call_records.append(
                ReplayBenchmarkCallRecord(
                    sequence=sequence,
                    benchmark_case_id=self.benchmark_case_id,
                    model_config_id=self.model_config.config_id,
                    node_name=node_name,
                    status="request_error",
                    started_at=started_at,
                    completed_at=completed_at,
                    latency_ms=0,
                    configured_model=self.model_config.model,
                    response_model=None,
                    usage=LLMUsage(),
                    messages=[_serialize_message(message) for message in messages],
                    raw_content=None,
                    parsed_json=None,
                    error_type="request_error",
                    error_message=error_message,
                )
            )
            raise LLMRequestError(error_message)

        serialized_messages = [_serialize_message(message) for message in messages]
        if record.request_error:
            error_message = record.error_message or (
                f"Replay request error for benchmark_case_id={record.benchmark_case_id}, "
                f"model_config_id={record.model_config_id}, node_name={record.node_name.value}."
            )
            self.call_records.append(
                ReplayBenchmarkCallRecord(
                    sequence=sequence,
                    benchmark_case_id=record.benchmark_case_id,
                    model_config_id=record.model_config_id,
                    node_name=record.node_name,
                    status="request_error",
                    started_at=started_at,
                    completed_at=completed_at,
                    latency_ms=record.latency_ms,
                    configured_model=self.model_config.model,
                    response_model=None,
                    usage=LLMUsage(
                        prompt_tokens=record.prompt_tokens,
                        completion_tokens=record.completion_tokens,
                        total_tokens=record.total_tokens,
                    ),
                    messages=serialized_messages,
                    raw_content=None,
                    parsed_json=None,
                    error_type=record.error_type or "request_error",
                    error_message=error_message,
                )
            )
            raise LLMRequestError(error_message)

        raw_content = record.raw_response
        if raw_content is None:
            raw_content = json.dumps(record.parsed_response or {}, ensure_ascii=False)

        call_record = ReplayBenchmarkCallRecord(
            sequence=sequence,
            benchmark_case_id=record.benchmark_case_id,
            model_config_id=record.model_config_id,
            node_name=record.node_name,
            status="success",
            started_at=started_at,
            completed_at=completed_at,
            latency_ms=record.latency_ms,
            configured_model=self.model_config.model,
            response_model=self.model_config.model,
            usage=LLMUsage(
                prompt_tokens=record.prompt_tokens,
                completion_tokens=record.completion_tokens,
                total_tokens=record.total_tokens,
            ),
            messages=serialized_messages,
            raw_content=raw_content,
            parsed_json=record.parsed_response,
            error_type=None,
            error_message=None,
        )
        self.call_records.append(call_record)
        return WorkflowLLMResult(
            content=raw_content,
            parsed_json=record.parsed_response,
            model=self.model_config.model,
            usage=call_record.usage,
            latency_ms=record.latency_ms,
        )


def _serialize_message(message: LLMMessage) -> dict[str, str]:
    return {
        "role": message.role.value,
        "content": message.content,
    }
