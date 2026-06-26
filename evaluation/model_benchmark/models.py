from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from agent.workflow_c.state import WorkflowNodeName
from schemas.common_models import StrictBaseModel


BenchmarkNodeName = WorkflowNodeName
_ALLOWED_BENCHMARK_NODE_NAMES = {
    WorkflowNodeName.fact_extraction,
    WorkflowNodeName.underlying_pain,
    WorkflowNodeName.information_gap,
    WorkflowNodeName.solution_recommendation,
}


class ModelTier(str, Enum):
    fast = "fast"
    balanced = "balanced"
    strong_reasoning = "strong_reasoning"


class BenchmarkExecutionMode(str, Enum):
    replay = "replay"
    live = "live"


class ThinkingMode(str, Enum):
    enabled = "enabled"
    disabled = "disabled"


class ReasoningEffort(str, Enum):
    high = "high"
    max = "max"


class BenchmarkAssertionType(str, Enum):
    json_parse_success = "json_parse_success"
    schema_validation_success = "schema_validation_success"
    business_rule_success = "business_rule_success"
    evidence_reference_valid = "evidence_reference_valid"
    candidate_boundary_valid = "candidate_boundary_valid"
    required_value_equals = "required_value_equals"
    forbidden_value_absent = "forbidden_value_absent"
    referenced_id_exists = "referenced_id_exists"


def _deduplicate_text(values: list[str], field_label: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            raise ValueError(f"{field_label} cannot include empty values.")
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _json_safe(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, bool)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json_safe(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_safe(item) for key, item in value.items())
    return False


def _to_decimal(value: Any, *, field_label: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        result = value
    else:
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError(f"{field_label} must be a valid decimal value.") from exc
    if result < 0:
        raise ValueError(f"{field_label} must be zero or greater.")
    return result.quantize(Decimal("0.000001"))


class ModelBenchmarkConfig(StrictBaseModel):
    config_id: str
    provider: str
    model: str
    tier: ModelTier
    thinking_mode: ThinkingMode = ThinkingMode.disabled
    reasoning_effort: ReasoningEffort | None = None
    temperature: float | None = 0
    max_tokens: int
    pricing_profile_id: str | None = None
    api_key_env: str | None = None
    enabled: bool = True

    @field_validator("config_id", "provider", "model")
    @classmethod
    def text_fields_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("Benchmark config fields are required and cannot be empty.")
        return value

    @field_validator("pricing_profile_id", "api_key_env")
    @classmethod
    def optional_text_fields_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("Optional benchmark config text fields cannot be blank.")
        return value

    @field_validator("temperature")
    @classmethod
    def temperature_must_be_valid(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if value < 0 or value > 2:
            raise ValueError("Benchmark temperature must be between 0 and 2.")
        return value

    @field_validator("max_tokens")
    @classmethod
    def max_tokens_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Benchmark max_tokens must be greater than 0.")
        return value

    @model_validator(mode="after")
    def validate_provider_specific_rules(self) -> Self:
        if self.provider == "deepseek":
            if self.model not in {"deepseek-v4-flash", "deepseek-v4-pro"}:
                raise ValueError("DeepSeek benchmark configs only support deepseek-v4-flash or deepseek-v4-pro.")
            if not self.pricing_profile_id:
                raise ValueError("DeepSeek benchmark configs must define pricing_profile_id.")
            if not self.api_key_env:
                raise ValueError("DeepSeek benchmark configs must define api_key_env.")
            if self.api_key_env != "LLM_API_KEY":
                raise ValueError("This pilot requires DeepSeek configs to use api_key_env=LLM_API_KEY.")
            if self.thinking_mode is ThinkingMode.enabled:
                if self.temperature is not None:
                    raise ValueError("Thinking-enabled benchmark configs must set temperature to null.")
                if self.reasoning_effort not in {ReasoningEffort.high, ReasoningEffort.max}:
                    raise ValueError("Thinking-enabled benchmark configs must use reasoning_effort high or max.")
            else:
                if self.reasoning_effort is not None:
                    raise ValueError("Non-thinking benchmark configs must not define reasoning_effort.")
                if self.temperature is None:
                    raise ValueError("Non-thinking benchmark configs must define temperature.")
        return self


class ModelBenchmarkConfigCatalog(StrictBaseModel):
    configs: list[ModelBenchmarkConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_catalog(self) -> Self:
        config_ids = [config.config_id for config in self.configs]
        if len(config_ids) != len(set(config_ids)):
            raise ValueError("Benchmark config IDs must be unique.")
        if not any(config.enabled for config in self.configs):
            raise ValueError("Benchmark config catalog must include at least one enabled config.")
        return self


class BenchmarkAssertion(StrictBaseModel):
    assertion_id: str
    assertion_type: BenchmarkAssertionType
    location: str
    expected_value: bool | int | float | str | None | list[Any] | dict[str, Any]
    description: str
    blocking: bool

    @field_validator("assertion_id", "location")
    @classmethod
    def text_fields_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("Benchmark assertion fields are required and cannot be empty.")
        return value

    @field_validator("description")
    @classmethod
    def description_must_be_concise(cls, value: str) -> str:
        if len(value) < 5:
            raise ValueError("Benchmark assertion descriptions must contain at least 5 characters.")
        if len(value) > 240:
            raise ValueError("Benchmark assertion descriptions must remain concise.")
        if "\n" in value:
            raise ValueError("Benchmark assertion descriptions must be single-line text.")
        lowered = value.casefold()
        forbidden_fragments = ("eval(", "__import__", "exec(", "lambda ", "os.system")
        if any(fragment in lowered for fragment in forbidden_fragments):
            raise ValueError("Benchmark assertion descriptions must not contain executable code.")
        return value

    @field_validator("expected_value")
    @classmethod
    def expected_value_must_be_json_safe(cls, value: Any) -> Any:
        if not _json_safe(value):
            raise ValueError("Benchmark assertion expected_value must be JSON-safe.")
        return value


class NodeBenchmarkCase(StrictBaseModel):
    benchmark_case_id: str
    source_case_id: str
    node_name: BenchmarkNodeName
    input_fixture: str
    assertions: list[BenchmarkAssertion]
    tags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("benchmark_case_id", "source_case_id", "input_fixture")
    @classmethod
    def text_fields_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("Benchmark case fields are required and cannot be empty.")
        return value

    @field_validator("source_case_id")
    @classmethod
    def source_case_id_must_match_expected_format(cls, value: str) -> str:
        if not re.fullmatch(r"(DEV|TEST)-\d{2}", value):
            raise ValueError("Source case ID must use the format DEV-01 or TEST-01.")
        return value

    @field_validator("input_fixture")
    @classmethod
    def input_fixture_must_be_stable(cls, value: str) -> str:
        if Path(value).is_absolute():
            raise ValueError("Input fixture must use a relative path or stable fixture identifier.")
        if "\n" in value:
            raise ValueError("Input fixture must be a single-line relative path or identifier.")
        return value

    @field_validator("tags", "notes")
    @classmethod
    def text_lists_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Benchmark case list fields")

    @field_validator("notes")
    @classmethod
    def notes_must_not_reference_hidden_pack(cls, values: list[str]) -> list[str]:
        lowered = " ".join(values).casefold()
        if "hidden reference pack" in lowered:
            raise ValueError("Benchmark notes must not reference the Hidden Reference Pack.")
        return values

    @model_validator(mode="after")
    def validate_node_benchmark_case(self) -> Self:
        if self.node_name not in _ALLOWED_BENCHMARK_NODE_NAMES:
            raise ValueError(
                "Benchmark cases can only target fact_extraction, underlying_pain, "
                "information_gap, or solution_recommendation."
            )
        if not self.assertions:
            raise ValueError("Benchmark cases must include at least one assertion.")
        if not any(assertion.blocking for assertion in self.assertions):
            raise ValueError("Benchmark cases must include at least one blocking assertion.")
        assertion_ids = [assertion.assertion_id for assertion in self.assertions]
        if len(assertion_ids) != len(set(assertion_ids)):
            raise ValueError("Benchmark assertion IDs must be unique.")
        return self


class BenchmarkRunStatus(str, Enum):
    passed = "passed"
    failed = "failed"
    request_error = "request_error"


class NodeBenchmarkRunResult(StrictBaseModel):
    run_id: str
    benchmark_case_id: str
    model_config_id: str
    node_name: BenchmarkNodeName
    status: BenchmarkRunStatus
    json_parse_success: bool
    schema_validation_success: bool
    business_rule_success: bool
    evidence_reference_valid: bool
    candidate_boundary_valid: bool
    assertion_pass_count: int
    assertion_fail_count: int
    blocking_failure_count: int
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost: Decimal | None = None
    error_type: str | None = None
    error_message: str | None = None

    @field_validator("run_id", "benchmark_case_id", "model_config_id")
    @classmethod
    def text_fields_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("Benchmark run fields are required and cannot be empty.")
        return value

    @field_validator("latency_ms")
    @classmethod
    def latency_must_not_be_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Benchmark run latency must be zero or greater.")
        return value

    @field_validator("prompt_tokens", "completion_tokens", "total_tokens")
    @classmethod
    def token_counts_must_not_be_negative(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("Benchmark token counts must be zero or greater.")
        return value

    @field_validator("estimated_cost")
    @classmethod
    def estimated_cost_must_be_non_negative(cls, value: Any) -> Decimal | None:
        return _to_decimal(value, field_label="Estimated benchmark cost")

    @field_validator("error_message")
    @classmethod
    def error_message_must_be_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value) > 500:
            return value[:497] + "..."
        return value

    @model_validator(mode="after")
    def validate_run_result(self) -> Self:
        if self.status is BenchmarkRunStatus.passed and self.blocking_failure_count != 0:
            raise ValueError("Passed benchmark runs must not record blocking failures.")
        if self.status in {BenchmarkRunStatus.failed, BenchmarkRunStatus.request_error}:
            if not self.error_type or not self.error_message:
                raise ValueError("Failed benchmark runs must include error_type and error_message.")
        if self.status is BenchmarkRunStatus.passed and (
            self.error_type is not None or self.error_message is not None
        ):
            raise ValueError("Passed benchmark runs must not include error details.")
        return self


class NodeModelBenchmarkSummary(StrictBaseModel):
    node_name: BenchmarkNodeName
    model_config_id: str
    case_count: int
    passed_count: int
    json_parse_pass_rate: float
    schema_pass_rate: float
    business_rule_pass_rate: float
    evidence_reference_pass_rate: float
    candidate_boundary_pass_rate: float
    average_latency_ms: float
    total_tokens: int
    estimated_total_cost: Decimal | None = None
    eligible_for_routing: bool
    disqualification_reasons: list[str] = Field(default_factory=list)

    @field_validator(
        "json_parse_pass_rate",
        "schema_pass_rate",
        "business_rule_pass_rate",
        "evidence_reference_pass_rate",
        "candidate_boundary_pass_rate",
    )
    @classmethod
    def rates_must_be_between_zero_and_one(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("Benchmark pass rates must be between 0 and 1.")
        return value

    @field_validator("disqualification_reasons")
    @classmethod
    def disqualification_reasons_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Disqualification reasons")

    @field_validator("case_count", "passed_count", "total_tokens")
    @classmethod
    def counts_must_not_be_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Benchmark summary counts must be zero or greater.")
        return value

    @field_validator("average_latency_ms")
    @classmethod
    def average_latency_must_not_be_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Average latency must be zero or greater.")
        return value

    @field_validator("estimated_total_cost")
    @classmethod
    def estimated_total_cost_must_be_non_negative(cls, value: Any) -> Decimal | None:
        return _to_decimal(value, field_label="Estimated total cost")


class NodeExecutionObservation(StrictBaseModel):
    benchmark_case_id: str
    model_config_id: str
    node_name: BenchmarkNodeName
    request_succeeded: bool
    json_parse_success: bool | None = None
    schema_validation_success: bool | None = None
    business_rule_success: bool | None = None
    evidence_reference_valid: bool | None = None
    candidate_boundary_valid: bool | None = None
    parsed_output: dict[str, Any] | list[Any] | str | int | float | bool | None = None
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost: Decimal | None = None
    model: str | None = None
    thinking_mode: ThinkingMode | None = None
    error_type: str | None = None
    error_message: str | None = None

    @field_validator("benchmark_case_id", "model_config_id")
    @classmethod
    def text_fields_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("Benchmark execution observation fields cannot be empty.")
        return value

    @field_validator("latency_ms")
    @classmethod
    def latency_must_not_be_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Observation latency must be zero or greater.")
        return value

    @field_validator("prompt_tokens", "completion_tokens", "total_tokens")
    @classmethod
    def token_counts_must_not_be_negative(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("Observation token counts must be zero or greater.")
        return value

    @field_validator("estimated_cost")
    @classmethod
    def estimated_cost_must_be_non_negative(cls, value: Any) -> Decimal | None:
        return _to_decimal(value, field_label="Observation estimated cost")

    @field_validator("error_message")
    @classmethod
    def error_message_must_be_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value) > 500:
            return value[:497] + "..."
        return value

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        if not self.request_succeeded:
            if not self.error_type or not self.error_message:
                raise ValueError("Failed observations must include error_type and error_message.")
            if self.parsed_output is not None:
                raise ValueError("Failed observations must not include parsed_output.")
        elif self.error_type is not None or self.error_message is not None:
            if (
                self.json_parse_success is not False
                and self.schema_validation_success is not False
                and self.business_rule_success is not False
            ):
                raise ValueError("Fully successful observations must not include error details.")
        return self


class BenchmarkAssertionResult(StrictBaseModel):
    assertion_id: str
    assertion_type: BenchmarkAssertionType
    blocking: bool
    passed: bool
    location: str
    failure_reason: str | None = None
    actual_summary: str | None = None

    @field_validator("assertion_id", "location")
    @classmethod
    def text_fields_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("Benchmark assertion result fields cannot be empty.")
        return value

    @field_validator("failure_reason", "actual_summary")
    @classmethod
    def short_text_fields_are_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value) > 500:
            return value[:497] + "..."
        return value

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.passed and self.failure_reason is not None:
            raise ValueError("Passed benchmark assertions must not include a failure reason.")
        if not self.passed and not self.failure_reason:
            raise ValueError("Failed benchmark assertions must include a failure reason.")
        return self


class BenchmarkCaseRunArtifact(StrictBaseModel):
    benchmark_case_id: str
    model_config_id: str
    node_name: BenchmarkNodeName
    observation: NodeExecutionObservation
    assertion_results: list[BenchmarkAssertionResult] = Field(default_factory=list)
    run_result: NodeBenchmarkRunResult
    artifact_dir: str | None = None

    @field_validator("benchmark_case_id", "model_config_id", "artifact_dir")
    @classmethod
    def string_fields_are_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value:
            raise ValueError("Benchmark case run artifact fields cannot be empty.")
        return value

    @model_validator(mode="after")
    def validate_case_run_artifact(self) -> Self:
        if self.observation.benchmark_case_id != self.benchmark_case_id:
            raise ValueError("Observation case ID must match the artifact case ID.")
        if self.observation.model_config_id != self.model_config_id:
            raise ValueError("Observation model config ID must match the artifact model config ID.")
        if self.observation.node_name is not self.node_name:
            raise ValueError("Observation node name must match the artifact node name.")
        if self.run_result.benchmark_case_id != self.benchmark_case_id:
            raise ValueError("Run result case ID must match the artifact case ID.")
        if self.run_result.model_config_id != self.model_config_id:
            raise ValueError("Run result model config ID must match the artifact model config ID.")
        if self.run_result.node_name is not self.node_name:
            raise ValueError("Run result node name must match the artifact node name.")
        return self


class BenchmarkRunManifest(StrictBaseModel):
    benchmark_version: Literal["v1.1C"] = "v1.1C"
    run_id: str
    started_at: datetime
    completed_at: datetime
    execution_mode: BenchmarkExecutionMode = BenchmarkExecutionMode.replay
    selected_case_count: int
    selected_model_count: int
    planned_run_count: int
    completed_run_count: int
    passed_count: int
    failed_count: int
    request_error_count: int
    provider_names: list[str] = Field(default_factory=list)
    pricing_snapshot_ids: list[str] = Field(default_factory=list)
    max_budget_cny: Decimal | None = None
    estimated_cost_cny: Decimal | None = None
    unknown_cost_run_count: int = 0
    stopped_by_budget: bool = False
    live_confirmed: bool = False
    selected_model_details: list[dict[str, Any]] = Field(default_factory=list)
    capture_debug_artifacts: bool = False
    output_directory: str

    @field_validator("run_id", "output_directory")
    @classmethod
    def string_fields_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("Benchmark run manifest fields cannot be empty.")
        return value

    @field_validator(
        "selected_case_count",
        "selected_model_count",
        "planned_run_count",
        "completed_run_count",
        "passed_count",
        "failed_count",
        "request_error_count",
        "unknown_cost_run_count",
    )
    @classmethod
    def counts_must_not_be_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Benchmark run manifest counts must be zero or greater.")
        return value

    @field_validator("provider_names", "pricing_snapshot_ids")
    @classmethod
    def text_lists_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Benchmark run manifest text lists")

    @field_validator("max_budget_cny", "estimated_cost_cny")
    @classmethod
    def manifest_costs_must_be_non_negative(cls, value: Any) -> Decimal | None:
        return _to_decimal(value, field_label="Benchmark run manifest cost")

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("Benchmark run manifest completed_at cannot precede started_at.")
        if self.completed_run_count != self.passed_count + self.failed_count + self.request_error_count:
            raise ValueError("Completed run count must equal the sum of status counts.")
        if self.execution_mode is BenchmarkExecutionMode.live and not self.provider_names:
            raise ValueError("Live benchmark manifests must include provider_names.")
        return self


class BenchmarkRunReport(StrictBaseModel):
    manifest: BenchmarkRunManifest
    model_configs: list[ModelBenchmarkConfig]
    selected_cases: list[NodeBenchmarkCase]
    run_results: list[NodeBenchmarkRunResult]
    summaries: list[NodeModelBenchmarkSummary]
    case_artifacts: list[BenchmarkCaseRunArtifact] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if self.manifest.completed_run_count != len(self.run_results):
            raise ValueError("Completed run count must equal the number of run results.")
        if len(self.model_configs) != self.manifest.selected_model_count:
            raise ValueError("Selected model count must match the loaded model configs.")
        if len(self.selected_cases) != self.manifest.selected_case_count:
            raise ValueError("Selected case count must match the loaded benchmark cases.")
        if self.case_artifacts and len(self.case_artifacts) != len(self.run_results):
            raise ValueError("Case artifacts must align with the run results.")
        return self


ModelBenchmarkSummary = NodeModelBenchmarkSummary
