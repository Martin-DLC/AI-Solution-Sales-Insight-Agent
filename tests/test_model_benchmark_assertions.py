from __future__ import annotations

from evaluation.model_benchmark.assertions import (
    BenchmarkAssertionContext,
    evaluate_benchmark_assertion,
    evaluate_benchmark_assertions,
)
from evaluation.model_benchmark.models import (
    BenchmarkAssertion,
    BenchmarkAssertionType,
    NodeExecutionObservation,
)
from agent.workflow_c.state import WorkflowNodeName


def _observation(
    *,
    node_name: WorkflowNodeName = WorkflowNodeName.information_gap,
    json_parse_success: bool = True,
    schema_validation_success: bool = True,
    business_rule_success: bool = True,
    evidence_reference_valid: bool = True,
    candidate_boundary_valid: bool = True,
    parsed_output: dict | None = None,
) -> NodeExecutionObservation:
    return NodeExecutionObservation(
        benchmark_case_id="NB-TEST-01",
        model_config_id="cfg-1",
        node_name=node_name,
        request_succeeded=True,
        json_parse_success=json_parse_success,
        schema_validation_success=schema_validation_success,
        business_rule_success=business_rule_success,
        evidence_reference_valid=evidence_reference_valid,
        candidate_boundary_valid=candidate_boundary_valid,
        parsed_output=parsed_output,
        latency_ms=10,
        prompt_tokens=1,
        completion_tokens=2,
        total_tokens=3,
        estimated_cost=None,
        error_type=None,
        error_message=None,
    )


def test_valid_owner_placeholder_passes() -> None:
    assertion = BenchmarkAssertion(
        assertion_id="A-owner",
        assertion_type=BenchmarkAssertionType.required_value_equals,
        location="recommended_owner",
        expected_value="valid_owner",
        description="Owner enum must be valid.",
        blocking=True,
    )
    context = BenchmarkAssertionContext(
        fixture={"state": {}},
        state={},
        node_output={"information_gaps": [{"recommended_owner": "sales"}]},
        observation=_observation(parsed_output={"information_gaps": [{"recommended_owner": "sales"}]}),
    )

    result = evaluate_benchmark_assertion(assertion, context)

    assert result.passed is True


def test_forbidden_value_absent_rejects_secret_like_content() -> None:
    assertion = BenchmarkAssertion(
        assertion_id="A-secret",
        assertion_type=BenchmarkAssertionType.forbidden_value_absent,
        location="fixture",
        expected_value=True,
        description="Fixture must exclude secrets.",
        blocking=True,
    )
    context = BenchmarkAssertionContext(
        fixture={"state": {"api_key": "sk-test-secret"}},
        state={},
        node_output=None,
        observation=_observation(),
    )

    result = evaluate_benchmark_assertion(assertion, context)

    assert result.passed is False
    assert result.failure_reason is not None


def test_referenced_id_exists_passes_for_known_source_ids() -> None:
    assertion = BenchmarkAssertion(
        assertion_id="A-ref",
        assertion_type=BenchmarkAssertionType.referenced_id_exists,
        location="facts.evidence",
        expected_value=True,
        description="Evidence references must exist.",
        blocking=True,
    )
    context = BenchmarkAssertionContext(
        fixture={
            "state": {
                "source_index": {
                    "items": [
                        {
                            "source_id": "MTG-01",
                            "source_type": "meeting_transcript",
                        }
                    ]
                }
            }
        },
        state={
            "source_index": {
                "items": [
                    {
                        "source_id": "MTG-01",
                        "source_type": "meeting_transcript",
                    }
                ]
            }
        },
        node_output={
            "facts": [
                {
                    "fact_id": "FACT-01",
                    "evidence": [
                        {
                            "source_id": "MTG-01",
                            "source_type": "meeting_transcript",
                            "evidence_summary": "会议明确说明目标",
                        }
                    ],
                }
            ]
        },
        observation=_observation(node_name=WorkflowNodeName.fact_extraction),
    )

    result = evaluate_benchmark_assertion(assertion, context)

    assert result.passed is True


def test_schema_validation_flag_uses_observation() -> None:
    assertion = BenchmarkAssertion(
        assertion_id="A-schema",
        assertion_type=BenchmarkAssertionType.schema_validation_success,
        location="information_gaps",
        expected_value=True,
        description="Schema must pass.",
        blocking=True,
    )
    context = BenchmarkAssertionContext(
        fixture={"state": {}},
        state={},
        node_output={},
        observation=_observation(schema_validation_success=False),
    )

    result = evaluate_benchmark_assertion(assertion, context)

    assert result.passed is False


def test_observation_flag_assertions_cover_core_types() -> None:
    assertion_types = [
        BenchmarkAssertionType.json_parse_success,
        BenchmarkAssertionType.schema_validation_success,
        BenchmarkAssertionType.business_rule_success,
        BenchmarkAssertionType.evidence_reference_valid,
        BenchmarkAssertionType.candidate_boundary_valid,
    ]

    for assertion_type in assertion_types:
        assertion = BenchmarkAssertion(
            assertion_id=f"A-{assertion_type.value}",
            assertion_type=assertion_type,
            location="response",
            expected_value=True,
            description="Observation flag must pass.",
            blocking=True,
        )
        result = evaluate_benchmark_assertion(
            assertion,
            BenchmarkAssertionContext(
                fixture={"state": {}},
                state={},
                node_output={},
                observation=_observation(),
            ),
        )

        assert result.passed is True


def test_referenced_id_exists_passes_for_solution_knowledge_references() -> None:
    assertion = BenchmarkAssertion(
        assertion_id="A-solution-reference",
        assertion_type=BenchmarkAssertionType.referenced_id_exists,
        location="knowledge_references",
        expected_value=True,
        description="Solution references must exist.",
        blocking=True,
    )
    context = BenchmarkAssertionContext(
        fixture={"state": {}},
        state={
            "retrieved_solutions": {
                "candidates": [
                    {
                        "solution_id": "AI客服知识问答方案",
                        "source_id": "SOL-01",
                    }
                ]
            }
        },
        node_output={
            "solution_recommendations": [
                {
                    "knowledge_references": [
                        {
                            "source_id": "SOL-01",
                            "source_type": "solution_library",
                            "evidence_summary": "候选方案支持推荐",
                        }
                    ]
                }
            ]
        },
        observation=_observation(node_name=WorkflowNodeName.solution_recommendation),
    )

    result = evaluate_benchmark_assertion(assertion, context)

    assert result.passed is True


def test_batch_of_assertions_remains_ordered() -> None:
    assertions = [
        BenchmarkAssertion(
            assertion_id="A-1",
            assertion_type=BenchmarkAssertionType.json_parse_success,
            location="response",
            expected_value=True,
            description="JSON parse must succeed.",
            blocking=True,
        ),
        BenchmarkAssertion(
            assertion_id="A-2",
            assertion_type=BenchmarkAssertionType.required_value_equals,
            location="recommended_owner",
            expected_value="valid_owner",
            description="Owner enum must be valid.",
            blocking=True,
        ),
    ]
    context = BenchmarkAssertionContext(
        fixture={"state": {}},
        state={},
        node_output={"information_gaps": [{"recommended_owner": "sales"}]},
        observation=_observation(parsed_output={"information_gaps": [{"recommended_owner": "sales"}]}),
    )

    results = evaluate_benchmark_assertions(assertions, context)

    assert [result.assertion_id for result in results] == ["A-1", "A-2"]
