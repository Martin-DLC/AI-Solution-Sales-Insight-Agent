from __future__ import annotations

from agent.model_providers import MockModelProvider, MockProviderFailureMode, ModelProviderRegistry, load_model_provider_configs
from agent.recovery import (
    CompensationPlan,
    ErrorCategory,
    ErrorType,
    FallbackType,
    IdempotencyKeyGenerator,
    RecoveryDecisionEngine,
    RetryPolicy,
    load_recovery_policy,
)
from agent.recovery.models import RecoveryAction, categorize_error
from agent.models import SolutionInsightRequest
from agent.observability import build_observation_snapshot
from agent.solution_insight_service import SolutionInsightService


def test_error_taxonomy_serializes_and_categorizes() -> None:
    assert ErrorType.model_timeout.value == "model_timeout"
    assert categorize_error(ErrorType.permission_denied) is ErrorCategory.permission_error


def test_fallback_taxonomy_contains_six_types() -> None:
    assert {item.value for item in FallbackType} == {
        "retrieval_fallback",
        "model_fallback",
        "tool_fallback",
        "workflow_fallback",
        "human_fallback",
        "safe_response_fallback",
    }


def test_recovery_policy_yaml_loads() -> None:
    config = load_recovery_policy()

    assert config.max_retry_count == 2
    assert ErrorType.model_timeout in config.retryable_error_types
    assert ErrorType.permission_denied in config.non_retryable_error_types


def test_retry_policy_allows_retryable_error() -> None:
    policy = RetryPolicy()

    assert policy.can_retry(error_type=ErrorType.model_timeout, current_retry_count=0) is True
    assert policy.next_retry_count(0) == 1


def test_retry_policy_rejects_non_retryable_error() -> None:
    assert RetryPolicy().can_retry(error_type=ErrorType.permission_denied, current_retry_count=0) is False


def test_model_timeout_first_decision_is_retry() -> None:
    decision = RecoveryDecisionEngine().decide(error_type=ErrorType.model_timeout, current_retry_count=0)

    assert decision.decision is RecoveryAction.retry
    assert decision.retry_recommended is True


def test_model_timeout_after_retries_falls_back() -> None:
    decision = RecoveryDecisionEngine().decide(error_type=ErrorType.model_timeout, current_retry_count=2)

    assert decision.decision is RecoveryAction.fallback
    assert decision.fallback_type is FallbackType.model_fallback


def test_permission_denied_requires_stop_or_human_review() -> None:
    decision = RecoveryDecisionEngine().decide(error_type=ErrorType.permission_denied)

    assert decision.decision in {RecoveryAction.stop, RecoveryAction.human_review}
    assert decision.human_review_required is True


def test_retrieval_boundary_failed_uses_safe_response_or_human_review() -> None:
    decision = RecoveryDecisionEngine().decide(error_type=ErrorType.retrieval_boundary_failed)

    assert decision.fallback_type is FallbackType.safe_response_fallback
    assert decision.human_review_required is True


def test_idempotency_key_generation_and_validation() -> None:
    generator = IdempotencyKeyGenerator()

    key = generator.generate(
        run_id="run-1",
        tool_name="crm_write",
        action="write",
        input_summary="account update",
    )

    assert generator.validate(key) is True
    assert key == generator.generate(
        run_id="run-1",
        tool_name="crm_write",
        action="write",
        input_summary="account update",
    )


def test_compensation_plan_serializes_without_execution() -> None:
    plan = CompensationPlan(
        run_id="run-1",
        tool_name="crm_write",
        original_action="write",
        compensation_action="manual_reverse",
        reason="Simulated rollback plan.",
    )

    dumped = plan.model_dump(mode="json")
    assert dumped["status"] == "planned"
    assert dumped["executed_at"] is None


def test_mock_model_provider_generate_is_deterministic() -> None:
    provider = MockModelProvider()

    first = provider.generate("hello")
    second = provider.generate("hello")

    assert first.content == second.content
    assert first.parsed_json["summary"] == "deterministic mock response"


def test_mock_model_provider_failure_modes() -> None:
    timeout_provider = MockModelProvider(failure_mode=MockProviderFailureMode.model_timeout)
    unavailable_provider = MockModelProvider(failure_mode=MockProviderFailureMode.model_unavailable)
    invalid_provider = MockModelProvider(failure_mode=MockProviderFailureMode.model_schema_invalid)

    try:
        timeout_provider.generate("hello")
    except TimeoutError as exc:
        assert "model_timeout" in str(exc)
    try:
        unavailable_provider.generate("hello")
    except RuntimeError as exc:
        assert "model_unavailable" in str(exc)
    assert invalid_provider.generate("hello").parsed_json == {}


def test_model_provider_registry_registers_and_selects_fallback() -> None:
    registry = ModelProviderRegistry()
    registry.register(MockModelProvider(provider_name="primary"))
    registry.register(MockModelProvider(provider_name="fallback"))

    primary = registry.select_primary()
    fallback = registry.select_fallback(primary.provider_name)

    assert primary.provider_name == "primary"
    assert fallback is not None
    assert fallback.provider_name == "fallback"
    assert registry.health_check_all() == {"primary": True, "fallback": True}


def test_model_provider_config_loads_placeholders() -> None:
    configs = load_model_provider_configs()

    assert {item["provider_name"] for item in configs} >= {"deterministic", "mock_primary", "mock_fallback", "deepseek"}
    assert any(item["provider_type"] == "placeholder" for item in configs)


def test_service_response_contains_recovery_and_model_provider_summary() -> None:
    response = _response()

    assert response.recovery_summary["decision"] in {"human_review", "fallback"}
    assert response.model_provider_summary["network_access"] == "none"
    assert response.requirement_summary


def test_observability_snapshot_contains_recovery_summary() -> None:
    snapshot = build_observation_snapshot(_response())

    assert snapshot.recovery.decision in {"human_review", "fallback"}
    assert snapshot.recovery.primary_provider is not None
    assert snapshot.recovery.model_fallback_configured is True


def _response():
    service = SolutionInsightService.from_defaults(
        enable_shadow_retrieval=True,
        llm_mode="deterministic",
    )
    return service.generate_insight(
        SolutionInsightRequest(
            user_query="一家中型 SaaS 公司想提升销售线索转化和客户成功效率",
            company_id="demo_saas_001",
            industry="SaaS",
            enable_shadow_retrieval=True,
            llm_mode="deterministic",
        )
    )
