from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.workflow_c import FakeWorkflowLLMClient
from agent.workflow_c.real_llm import WorkflowLLMCallRecord
from agent.workflow_c.runtime import ArchitectureCRunner
from agent.workflow_c.model_routing import (
    ModelRoutingError,
    ModelRoutingUnavailableError,
    RoutedWorkflowLLMClient,
    format_model_routing_plan,
    load_model_routing_policy,
)
from agent.workflow_c.state import WorkflowNodeName
from llm import LLMConfig, LLMMessage, LLMRole, LLMUsage
from llm.errors import LLMJSONDecodeError, LLMRequestError, LLMResponseError
from llm.models import LLMResponse


class FakeNodeLLMClient:
    def __init__(self, *, response: LLMResponse | None = None, error: Exception | None = None) -> None:
        self.response = response or LLMResponse(
            content='{"ok": true}',
            parsed_json={"ok": True},
            model="fake-model",
            response_id="resp-1",
            finish_reason="stop",
            usage=LLMUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            latency_ms=20,
        )
        self.error = error
        self.calls = 0

    def list_model_ids(self) -> list[str]:
        return ["fake-model"]

    def complete_text(self, messages, *, temperature=None, max_tokens=None):
        raise AssertionError("Routed workflow client must use complete_json.")

    def complete_json(self, messages, *, temperature=None, max_tokens=None):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.response


def _messages() -> list[LLMMessage]:
    return [LLMMessage(role=LLMRole.user, content="Return JSON object.")]


def _default_config() -> LLMConfig:
    return LLMConfig(
        api_key="sk-test-secret",
        base_url="https://api.example.com",
        model="default-model",
    )


def test_load_model_routing_policy_reads_expected_primary_and_fallback() -> None:
    policy = _load_real_policy()

    fact = policy.routes_by_node[WorkflowNodeName.fact_extraction]
    assert fact.primary_model_config_id == "ds-v4-flash-non-thinking"
    assert fact.fallback_model_config_id == "ds-v4-pro-thinking-high"


def test_load_model_routing_policy_rejects_same_primary_and_fallback(tmp_path: Path) -> None:
    matrix_path, config_path = _write_policy_fixture(
        tmp_path,
        node_overrides={
            "fact_extraction": {
                "primary_model_config_id": "cfg-a",
                "fallback_model_config_id": "cfg-a",
                "eligible_model_config_ids": ["cfg-a"],
            }
        },
    )

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ModelRoutingError):
            load_model_routing_policy(matrix_path=matrix_path.name, config_path=config_path.name)


def test_load_model_routing_policy_rejects_unknown_config_id(tmp_path: Path) -> None:
    matrix_path, config_path = _write_policy_fixture(
        tmp_path,
        node_overrides={
            "underlying_pain": {
                "primary_model_config_id": "cfg-missing",
                "eligible_model_config_ids": ["cfg-missing"],
            }
        },
    )

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ModelRoutingError):
            load_model_routing_policy(matrix_path=matrix_path.name, config_path=config_path.name)


def test_load_model_routing_policy_rejects_non_target_nodes(tmp_path: Path) -> None:
    matrix_path, config_path = _write_policy_fixture(
        tmp_path,
        extra_nodes=[
            {
                "node_name": "stakeholder",
                "route_status": "route_ready",
                "primary_model_config_id": "cfg-a",
                "fallback_model_config_id": "cfg-b",
                "eligible_model_config_ids": ["cfg-a", "cfg-b"],
                "selection_reason": "test",
            }
        ],
    )

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ModelRoutingError):
            load_model_routing_policy(matrix_path=matrix_path.name, config_path=config_path.name)


def test_load_model_routing_policy_rejects_secret_fields(tmp_path: Path) -> None:
    matrix_path, config_path = _write_policy_fixture(
        tmp_path,
        config_overrides={
            "cfg-a": {
                "api_key": "sk-secret-should-not-appear",
            }
        },
    )

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ModelRoutingError):
            load_model_routing_policy(matrix_path=matrix_path.name, config_path=config_path.name)


def test_no_eligible_model_must_not_define_primary_or_fallback(tmp_path: Path) -> None:
    matrix_path, config_path = _write_policy_fixture(
        tmp_path,
        node_overrides={
            "information_gap": {
                "route_status": "no_eligible_model",
                "primary_model_config_id": "cfg-a",
                "fallback_model_config_id": None,
                "eligible_model_config_ids": [],
            }
        },
    )

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ModelRoutingError):
            load_model_routing_policy(matrix_path=matrix_path.name, config_path=config_path.name)


def test_format_model_routing_plan_shows_unbenchmarked_nodes() -> None:
    plan = format_model_routing_plan(_load_real_policy())

    assert "Model routing: enabled" in plan
    assert "unbenchmarked nodes:" in plan
    assert "existing default model" in plan


def test_routed_client_uses_primary_for_benchmarked_node() -> None:
    created: list[str] = []

    def factory(config):
        created.append(config.config_id)
        return FakeNodeLLMClient(
            response=LLMResponse(
                content='{"result": "primary"}',
                parsed_json={"result": "primary"},
                model=config.model,
                response_id="resp-1",
                finish_reason="stop",
                usage=LLMUsage(prompt_tokens=11, completion_tokens=4, total_tokens=15),
                latency_ms=30,
            )
        )

    client = RoutedWorkflowLLMClient(
        default_client=FakeNodeLLMClient(),
        default_config=_default_config(),
        policy=_load_real_policy(),
        routed_client_factory=factory,
    )

    result = client.complete_json_for_node(WorkflowNodeName.fact_extraction, _messages())

    assert result.parsed_json == {"result": "primary"}
    assert created == ["ds-v4-flash-non-thinking"]
    assert client.call_records[0].route_role == "primary"


def test_routed_client_caches_per_config() -> None:
    created: list[str] = []

    def factory(config):
        created.append(config.config_id)
        return FakeNodeLLMClient()

    client = RoutedWorkflowLLMClient(
        default_client=FakeNodeLLMClient(),
        default_config=_default_config(),
        policy=_load_real_policy(),
        routed_client_factory=factory,
    )

    client.complete_json_for_node(WorkflowNodeName.fact_extraction, _messages())
    client.complete_json_for_node(WorkflowNodeName.fact_extraction, _messages())

    assert created == ["ds-v4-flash-non-thinking"]


def test_unbenchmarked_node_uses_default_client() -> None:
    default_client = FakeNodeLLMClient(
        response=LLMResponse(
            content='{"result": "default"}',
            parsed_json={"result": "default"},
            model="default-model",
            response_id="resp-1",
            finish_reason="stop",
            usage=LLMUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
            latency_ms=9,
        )
    )
    client = RoutedWorkflowLLMClient(
        default_client=default_client,
        default_config=_default_config(),
        policy=_load_real_policy(),
        routed_client_factory=lambda config: FakeNodeLLMClient(),
    )

    result = client.complete_json_for_node(WorkflowNodeName.explicit_need, _messages())

    assert result.parsed_json == {"result": "default"}
    assert default_client.calls == 1
    assert client.call_records[0].route_role == "default_unbenchmarked"


def test_primary_request_error_uses_fallback_once() -> None:
    created: dict[str, FakeNodeLLMClient] = {}

    def factory(config):
        if config.config_id == "ds-v4-flash-non-thinking":
            created[config.config_id] = FakeNodeLLMClient(error=LLMRequestError("timeout"))
        else:
            created[config.config_id] = FakeNodeLLMClient()
        return created[config.config_id]

    client = RoutedWorkflowLLMClient(
        default_client=FakeNodeLLMClient(),
        default_config=_default_config(),
        policy=_load_real_policy(),
        routed_client_factory=factory,
    )

    result = client.complete_json_for_node(WorkflowNodeName.fact_extraction, _messages())

    assert result.parsed_json == {"ok": True}
    assert len(client.call_records) == 2
    assert client.call_records[0].route_role == "primary"
    assert client.call_records[1].route_role == "fallback"
    assert client.call_records[1].fallback_reason == "timeout"


def test_invalid_provider_response_uses_fallback_once() -> None:
    def factory(config):
        if config.config_id == "ds-v4-flash-non-thinking":
            return FakeNodeLLMClient(error=LLMResponseError("provider returned blank body"))
        return FakeNodeLLMClient()

    client = RoutedWorkflowLLMClient(
        default_client=FakeNodeLLMClient(),
        default_config=_default_config(),
        policy=_load_real_policy(),
        routed_client_factory=factory,
    )

    result = client.complete_json_for_node(WorkflowNodeName.underlying_pain, _messages())

    assert result.parsed_json == {"ok": True}
    assert [record.route_role for record in client.call_records] == ["primary", "fallback"]


def test_json_decode_failure_does_not_use_fallback() -> None:
    def factory(config):
        if config.config_id == "ds-v4-flash-non-thinking":
            return FakeNodeLLMClient(
                error=LLMJSONDecodeError(
                    raw_content="{bad json",
                    json_error_message="bad json",
                    json_error_position=1,
                )
            )
        return FakeNodeLLMClient()

    client = RoutedWorkflowLLMClient(
        default_client=FakeNodeLLMClient(),
        default_config=_default_config(),
        policy=_load_real_policy(),
        routed_client_factory=factory,
    )

    with pytest.raises(LLMJSONDecodeError):
        client.complete_json_for_node(WorkflowNodeName.fact_extraction, _messages())

    assert len(client.call_records) == 1
    assert client.call_records[0].route_role == "primary"


def test_primary_and_fallback_both_fail_stop_after_two_attempts() -> None:
    def factory(config):
        if config.config_id == "ds-v4-flash-non-thinking":
            return FakeNodeLLMClient(error=LLMRequestError("timeout"))
        return FakeNodeLLMClient(error=LLMRequestError("network unavailable sk-secret"))

    client = RoutedWorkflowLLMClient(
        default_client=FakeNodeLLMClient(),
        default_config=_default_config(),
        policy=_load_real_policy(),
        routed_client_factory=factory,
    )

    with pytest.raises(LLMRequestError):
        client.complete_json_for_node(WorkflowNodeName.fact_extraction, _messages())

    assert len(client.call_records) == 2
    assert [record.route_role for record in client.call_records] == ["primary", "fallback"]
    assert "sk-secret" not in (client.call_records[-1].error_message or "")


def test_primary_failure_without_fallback_does_not_retry(tmp_path: Path) -> None:
    matrix_path, config_path = _write_policy_fixture(
        tmp_path,
        node_overrides={
            "fact_extraction": {
                "fallback_model_config_id": None,
                "eligible_model_config_ids": ["cfg-a"],
            }
        },
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.chdir(tmp_path)
        policy = load_model_routing_policy(matrix_path=matrix_path.name, config_path=config_path.name)
    client = RoutedWorkflowLLMClient(
        default_client=FakeNodeLLMClient(),
        default_config=_default_config(),
        policy=policy,
        routed_client_factory=lambda config: FakeNodeLLMClient(error=LLMRequestError("timeout")),
    )

    with pytest.raises(LLMRequestError):
        client.complete_json_for_node(WorkflowNodeName.fact_extraction, _messages())

    assert len(client.call_records) == 1


def test_no_eligible_model_fails_closed_without_request(tmp_path: Path) -> None:
    matrix_path, config_path = _write_policy_fixture(
        tmp_path,
        node_overrides={
            "information_gap": {
                "route_status": "no_eligible_model",
                "primary_model_config_id": None,
                "fallback_model_config_id": None,
                "eligible_model_config_ids": [],
            }
        },
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.chdir(tmp_path)
        policy = load_model_routing_policy(matrix_path=matrix_path.name, config_path=config_path.name)
    default_client = FakeNodeLLMClient()
    client = RoutedWorkflowLLMClient(
        default_client=default_client,
        default_config=_default_config(),
        policy=policy,
        routed_client_factory=lambda config: FakeNodeLLMClient(),
    )

    with pytest.raises(ModelRoutingUnavailableError):
        client.complete_json_for_node(WorkflowNodeName.information_gap, _messages())

    assert default_client.calls == 0
    assert client.call_records == []


def test_call_records_include_routing_metadata() -> None:
    client = RoutedWorkflowLLMClient(
        default_client=FakeNodeLLMClient(),
        default_config=_default_config(),
        policy=_load_real_policy(),
        routed_client_factory=lambda config: FakeNodeLLMClient(),
    )

    client.complete_json_for_node(WorkflowNodeName.solution_recommendation, _messages())

    record = client.call_records[0]
    assert record.routing_enabled is True
    assert record.selected_model_config_id == "ds-v4-flash-non-thinking"
    assert record.selected_provider == "deepseek"
    assert record.selected_tier == "fast"
    assert record.routing_policy_version == "v1"
    assert record.fallback_used is False


def test_fallback_call_count_and_models_used_are_reported() -> None:
    def factory(config):
        if config.config_id == "ds-v4-flash-non-thinking":
            return FakeNodeLLMClient(error=LLMRequestError("timeout"))
        return FakeNodeLLMClient(
            response=LLMResponse(
                content='{"result": "fallback"}',
                parsed_json={"result": "fallback"},
                model="fallback-model",
                response_id="resp-2",
                finish_reason="stop",
                usage=LLMUsage(prompt_tokens=9, completion_tokens=3, total_tokens=12),
                latency_ms=14,
            )
        )

    client = RoutedWorkflowLLMClient(
        default_client=FakeNodeLLMClient(),
        default_config=_default_config(),
        policy=_load_real_policy(),
        routed_client_factory=factory,
    )

    client.complete_json_for_node(WorkflowNodeName.solution_recommendation, _messages())

    assert client.fallback_call_count == 1
    assert client.models_used == ["deepseek-v4-flash", "fallback-model"]


def test_runner_metadata_collects_routing_fields(tmp_path: Path) -> None:
    class RecordingRoutedWorkflowLLM:
        def __init__(self) -> None:
            self.delegate = FakeWorkflowLLMClient.with_default_batch4b_responses()
            self.config = _default_config()
            self.call_records: list[WorkflowLLMCallRecord] = []
            self.model_routing_enabled = True
            self.routing_policy_version = "v1"
            self.routing_matrix_file = "data/evaluation/model_benchmark/node_model_routing_matrix.v1.json"
            self.model_configs_file = "data/evaluation/model_benchmark/model_configs.deepseek_v4.json"
            self.routed_nodes = ["fact_extraction"]
            self.unavailable_routed_nodes = []
            self.fallback_call_count = 1
            self.models_used = ["model-b", "default-model"]

        def complete_json_for_node(self, node_name, messages):
            sequence = len(self.call_records) + 1
            result = self.delegate.complete_json_for_node(node_name, messages)
            self.call_records.append(
                WorkflowLLMCallRecord.model_validate(
                    {
                        "sequence": sequence,
                        "node_name": node_name.value,
                        "status": "success",
                        "started_at": "2026-06-28T00:00:00Z",
                        "completed_at": "2026-06-28T00:00:00Z",
                        "latency_ms": result.latency_ms,
                        "configured_model": self.config.model,
                        "response_model": result.model,
                        "usage": result.usage.model_dump(mode="json"),
                        "messages": [],
                        "estimated_cost": "0.42" if sequence == 1 else None,
                        "routing_enabled": True,
                        "selected_model_config_id": "cfg-b" if sequence == 1 else None,
                        "selected_provider": "deepseek" if sequence == 1 else None,
                        "selected_model": "model-b" if sequence == 1 else self.config.model,
                        "selected_tier": "balanced" if sequence == 1 else None,
                        "route_role": "fallback" if sequence == 1 else "default_unbenchmarked",
                        "fallback_used": sequence == 1,
                        "fallback_reason": "timeout" if sequence == 1 else None,
                        "routing_policy_version": "v1",
                    }
                )
            )
            return result

    runner = ArchitectureCRunner(RecordingRoutedWorkflowLLM(), output_root=tmp_path / "runs")
    result = runner.run_case(_dev_case())

    assert result.metadata.model_routing_enabled is True
    assert result.metadata.routing_policy_version == "v1"
    assert result.metadata.fallback_call_count == 1
    assert result.metadata.models_used == ["model-b", "default-model"]
    assert str(result.metadata.estimated_cost_cny) == "0.42"
    assert not Path(result.metadata.output_directory).is_absolute()


def test_runner_metadata_defaults_remain_compatible_without_routing(tmp_path: Path) -> None:
    class NonRoutingWorkflowLLM:
        def __init__(self) -> None:
            self.delegate = FakeWorkflowLLMClient.with_default_batch4b_responses()
            self.config = _default_config()
            self.call_records: list[WorkflowLLMCallRecord] = []

        def complete_json_for_node(self, node_name, messages):
            sequence = len(self.call_records) + 1
            result = self.delegate.complete_json_for_node(node_name, messages)
            self.call_records.append(
                WorkflowLLMCallRecord.model_validate(
                    {
                        "sequence": sequence,
                        "node_name": node_name.value,
                        "status": "success",
                        "started_at": "2026-06-28T00:00:00Z",
                        "completed_at": "2026-06-28T00:00:00Z",
                        "latency_ms": result.latency_ms,
                        "configured_model": self.config.model,
                        "response_model": result.model,
                        "usage": result.usage.model_dump(mode="json"),
                        "messages": [],
                    }
                )
            )
            return result

    runner = ArchitectureCRunner(NonRoutingWorkflowLLM(), output_root=tmp_path / "runs")
    result = runner.run_case(_dev_case())

    assert result.metadata.model_routing_enabled is False
    assert result.metadata.routing_policy_version is None
    assert result.metadata.routing_matrix_file is None
    assert result.metadata.model_configs_file is None
    assert result.metadata.routed_nodes == []
    assert result.metadata.unavailable_routed_nodes == []
    assert result.metadata.fallback_call_count == 0
    assert result.metadata.models_used == ["fake-workflow-model"]
    assert not Path(result.metadata.output_directory).is_absolute()


def _load_real_policy():
    root = Path(__file__).resolve().parents[1]
    return load_model_routing_policy(
        matrix_path=root / "data/evaluation/model_benchmark/node_model_routing_matrix.v1.json",
        config_path=root / "data/evaluation/model_benchmark/model_configs.deepseek_v4.json",
    )


def _dev_case():
    from dataio.runtime_cases import load_runtime_cases

    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def _write_policy_fixture(
    tmp_path: Path,
    *,
    node_overrides: dict[str, dict] | None = None,
    config_overrides: dict[str, dict] | None = None,
    extra_nodes: list[dict] | None = None,
) -> tuple[Path, Path]:
    node_overrides = node_overrides or {}
    config_items = [
        {
            "config_id": "cfg-a",
            "provider": "deepseek",
            "model": "model-a",
            "tier": "fast",
            "thinking_mode": "disabled",
            "reasoning_effort": None,
            "temperature": 0,
            "max_tokens": 1024,
            "pricing_profile_id": "flash-v4-2026-06",
            "api_key_env": "LLM_API_KEY",
            "enabled": True,
        },
        {
            "config_id": "cfg-b",
            "provider": "deepseek",
            "model": "model-b",
            "tier": "balanced",
            "thinking_mode": "disabled",
            "reasoning_effort": None,
            "temperature": 0,
            "max_tokens": 1024,
            "pricing_profile_id": "pro-v4-2026-06",
            "api_key_env": "LLM_API_KEY",
            "enabled": True,
        },
    ]
    overrides = config_overrides or {}
    for item in config_items:
        item.update(overrides.get(item["config_id"], {}))
    nodes = []
    for node_name in [
        "fact_extraction",
        "underlying_pain",
        "information_gap",
        "solution_recommendation",
    ]:
        item = {
            "node_name": node_name,
            "route_status": "route_ready",
            "primary_model_config_id": "cfg-a",
            "fallback_model_config_id": "cfg-b",
            "eligible_model_config_ids": ["cfg-a", "cfg-b"],
            "selection_reason": "test",
        }
        item.update(node_overrides.get(node_name, {}))
        nodes.append(item)
    if extra_nodes:
        nodes.extend(extra_nodes)
    matrix = {
        "matrix_version": "v1",
        "formal_run_ids": [],
        "nodes": nodes,
    }
    matrix_path = tmp_path / "matrix.json"
    config_path = tmp_path / "configs.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    config_path.write_text(json.dumps(config_items), encoding="utf-8")
    return matrix_path, config_path
