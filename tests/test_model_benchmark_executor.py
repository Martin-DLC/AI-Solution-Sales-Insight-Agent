from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.workflow_c.state import WorkflowNodeName
from evaluation.model_benchmark.clients import ReplayBenchmarkRecord, create_replay_client_factory
from evaluation.model_benchmark.executor import NodeModelBenchmarkExecutor
from evaluation.model_benchmark.models import (
    BenchmarkAssertion,
    BenchmarkAssertionType,
    BenchmarkRunStatus,
    ModelBenchmarkConfig,
    ModelTier,
    NodeBenchmarkCase,
)
from evaluation.model_benchmark.dataset import load_node_benchmark_cases


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "data/evaluation/model_benchmark/node_cases.jsonl"


def _config(config_id: str = "replay-fast") -> ModelBenchmarkConfig:
    return ModelBenchmarkConfig(
        config_id=config_id,
        provider="replay",
        model="replay-model",
        tier=ModelTier.fast,
        temperature=0,
        max_tokens=2048,
        enabled=True,
    )


def _case(node_name: WorkflowNodeName) -> NodeBenchmarkCase:
    return next(case for case in load_node_benchmark_cases(CASES_PATH) if case.node_name is node_name)


def _fixture(case: NodeBenchmarkCase) -> dict[str, Any]:
    return json.loads((PROJECT_ROOT / case.input_fixture).read_text(encoding="utf-8"))


def _payload_for_case(case: NodeBenchmarkCase) -> dict[str, Any]:
    state = _fixture(case)["state"]
    if case.node_name is WorkflowNodeName.fact_extraction:
        return _fact_payload(state)
    if case.node_name is WorkflowNodeName.underlying_pain:
        return _pain_payload(state)
    if case.node_name is WorkflowNodeName.information_gap:
        return _gap_payload()
    if case.node_name is WorkflowNodeName.solution_recommendation:
        return _solution_payload(state)
    raise AssertionError(f"Unsupported node for test: {case.node_name}")


def _fact_payload(state: dict[str, Any]) -> dict[str, Any]:
    source_index = state["source_index"]
    systems = [
        item["title"]
        for item in source_index["items"]
        if item["source_type"] == "solution_library"
    ]
    return {
        "fact_extraction": {
            "facts": [
                {
                    "fact_id": "FACT-BENCH-01",
                    "category": "business_goal",
                    "statement": "客户希望评估AI能力对当前业务流程的改善空间。",
                    "claim_type": "fact",
                    "confidence": "high",
                    "evidence": [
                        {
                            "source_id": "MTG-01",
                            "source_type": "meeting_transcript",
                            "evidence_summary": "会议纪要明确包含客户目标",
                        }
                    ],
                }
            ],
            "unknown_fields": ["budget"],
            "customer_context_draft": {
                "company_name": "节点评测样例客户",
                "industry": "综合行业",
                "company_size": "约500名员工",
                "current_systems": systems or ["现有业务系统"],
                "sales_stage_input": "需求调研阶段",
                "confirmed_constraints": ["仍需确认预算和决策流程"],
                "context_quality": "partially_sufficient",
            },
        }
    }


def _pain_payload(state: dict[str, Any]) -> dict[str, Any]:
    need_id = state["explicit_needs"][0]["need_id"]
    return {
        "underlying_pains": [
            {
                "pain_id": "PAIN-BENCH-01",
                "description": "现有流程和数据基础不足，可能影响AI方案落地。",
                "business_dimension": "efficiency",
                "severity": "medium",
                "claim_type": "inference",
                "reasoning_summary": "客户目标和约束共同表明落地前需要补齐基础条件。",
                "confidence": "medium",
                "evidence": [
                    {
                        "source_id": "MTG-01",
                        "source_type": "meeting_transcript",
                        "evidence_summary": "会议纪要支持该潜在痛点",
                    }
                ],
                "validation_question": f"请确认{need_id}对应的流程和数据准备情况？",
            }
        ]
    }


def _gap_payload() -> dict[str, Any]:
    return {
        "information_gaps": [
            {
                "gap_id": "GAP-BENCH-01",
                "category": "budget",
                "description": "预算和费用承担方式仍需确认。",
                "priority": "high",
                "business_impact": "预算缺口会影响推荐范围和实施节奏。",
                "question_to_ask": "请确认本项目预算区间和费用承担部门？",
                "recommended_owner": "sales",
            }
        ]
    }


def _solution_payload(state: dict[str, Any]) -> dict[str, Any]:
    candidate = state["retrieved_solutions"]["candidates"][0]
    opportunity_id = state["ai_opportunities"][0]["opportunity_id"]
    return {
        "solution_recommendations": [
            {
                "recommendation_id": "REC-BENCH-01",
                "solution_id": candidate["solution_id"],
                "solution_name": candidate["content"],
                "fit_level": "high",
                "related_opportunity_ids": [opportunity_id],
                "recommended_scope": "围绕首个候选方案开展可控范围试点。",
                "fit_reasons": ["与当前AI机会和候选方案范围匹配"],
                "prerequisites": ["确认接口和数据权限"],
                "delivery_risks": ["数据准备不足会影响效果"],
                "excluded_capabilities": ["暂不承诺超出候选方案的能力"],
                "knowledge_references": [
                    {
                        "source_id": candidate["source_id"],
                        "source_type": "solution_library",
                        "evidence_summary": "候选方案库中包含该方案",
                    }
                ],
                "confidence": "high",
            }
        ]
    }


def _replay_record(case: NodeBenchmarkCase, payload: dict[str, Any]) -> ReplayBenchmarkRecord:
    return ReplayBenchmarkRecord(
        benchmark_case_id=case.benchmark_case_id,
        model_config_id="replay-fast",
        node_name=case.node_name,
        parsed_response=payload,
        raw_response=json.dumps(payload, ensure_ascii=False),
        latency_ms=25,
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
    )


def test_four_target_nodes_execute_real_node_code_with_replay() -> None:
    executor = NodeModelBenchmarkExecutor()
    config = _config()

    for node_name in (
        WorkflowNodeName.fact_extraction,
        WorkflowNodeName.underlying_pain,
        WorkflowNodeName.information_gap,
        WorkflowNodeName.solution_recommendation,
    ):
        case = _case(node_name)
        factory = create_replay_client_factory(
            replay_records=[_replay_record(case, _payload_for_case(case))]
        )
        client = factory(config, case)

        execution = executor.execute_case(case, config, client=client, run_id="run-1")

        assert execution.artifact.run_result.status is BenchmarkRunStatus.passed
        assert execution.artifact.observation.json_parse_success is True
        assert execution.artifact.observation.schema_validation_success is True
        assert len(execution.call_records) == 1


def test_assertion_failure_marks_run_failed_without_request_error() -> None:
    case = _case(WorkflowNodeName.information_gap).model_copy(
        update={
            "assertions": [
                BenchmarkAssertion(
                    assertion_id="A-owner",
                    assertion_type=BenchmarkAssertionType.required_value_equals,
                    location="recommended_owner",
                    expected_value="unknown",
                    description="Owner must match expected value.",
                    blocking=True,
                )
            ]
        }
    )
    config = _config()
    payload = _gap_payload()
    factory = create_replay_client_factory(replay_records=[_replay_record(case, payload)])
    client = factory(config, case)

    execution = NodeModelBenchmarkExecutor().execute_case(case, config, client=client, run_id="run-2")

    result = execution.artifact.run_result
    assert result.status is BenchmarkRunStatus.failed
    assert result.error_type == "assertion_failure"
    assert result.error_message is not None
    assert "request" not in result.error_type
