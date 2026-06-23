from __future__ import annotations

from agent.workflow_c import (
    FakeWorkflowLLMClient,
    WorkflowNodeName,
    WorkflowServices,
    WorkflowStatus,
    run_architecture_c_skeleton,
)
from dataio.runtime_cases import load_runtime_cases


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def test_batch1b_success_path_node_order() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert [record.node_name for record in snapshot.node_records] == [
        WorkflowNodeName.input_validation,
        WorkflowNodeName.source_indexing,
        WorkflowNodeName.fact_extraction,
        WorkflowNodeName.context_sufficiency,
        WorkflowNodeName.explicit_need,
        WorkflowNodeName.underlying_pain,
        WorkflowNodeName.business_impact,
        WorkflowNodeName.buying_intent,
        WorkflowNodeName.stakeholder,
        WorkflowNodeName.information_gap,
        WorkflowNodeName.ai_opportunity,
        WorkflowNodeName.solution_retrieval,
        WorkflowNodeName.solution_recommendation,
        WorkflowNodeName.deal_score,
        WorkflowNodeName.risk,
        WorkflowNodeName.next_best_action,
        WorkflowNodeName.human_review_gate,
    ]


def test_batch1b_coverage_success_path_llm_calls_eleven_times_after_batch4b() -> None:
    client = FakeWorkflowLLMClient.with_default_batch4b_responses()

    run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert client.total_calls == 11
    assert client.calls_for_node(WorkflowNodeName.fact_extraction) == 1
    assert client.calls_for_node(WorkflowNodeName.explicit_need) == 1
    assert client.calls_for_node(WorkflowNodeName.underlying_pain) == 1
    assert client.calls_for_node(WorkflowNodeName.business_impact) == 1
    assert client.calls_for_node(WorkflowNodeName.buying_intent) == 1
    assert client.calls_for_node(WorkflowNodeName.stakeholder) == 1
    assert client.calls_for_node(WorkflowNodeName.information_gap) == 1
    assert client.calls_for_node(WorkflowNodeName.ai_opportunity) == 1
    assert client.calls_for_node(WorkflowNodeName.solution_retrieval) == 0
    assert client.calls_for_node(WorkflowNodeName.solution_recommendation) == 1
    assert client.calls_for_node(WorkflowNodeName.deal_score) == 0


def test_batch1b_final_status_still_awaits_human_review() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.workflow_status is WorkflowStatus.awaiting_human_review
    assert snapshot.human_review_required is True


def test_fact_failure_skips_context_and_explicit_need() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1a_responses(
        invalid_json_nodes={"fact_extraction"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.context_sufficiency not in order
    assert WorkflowNodeName.explicit_need not in order
    assert WorkflowNodeName.underlying_pain not in order
    assert WorkflowNodeName.business_impact not in order
    assert WorkflowNodeName.buying_intent not in order
    assert WorkflowNodeName.stakeholder not in order
    assert order[-1] is WorkflowNodeName.human_review_gate


def test_explicit_need_failure_still_runs_human_review_gate() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1a_responses(
        invalid_json_nodes={"explicit_need"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.failures[0].node_name is WorkflowNodeName.explicit_need
    assert snapshot.node_records[-1].node_name is WorkflowNodeName.human_review_gate


def test_batch1b_snapshot_serializes_explicit_needs() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    dumped = snapshot.model_dump(mode="json")

    assert dumped["explicit_needs"][0]["need_id"] == "NEED-01"


def test_custom_explicit_need_evidence_failure_runs_human_review_gate() -> None:
    bad_payload = {
        "explicit_needs": [
            {
                "need_id": "NEED-BAD",
                "description": "客户明确希望提升销售线索跟进效率。",
                "priority": "high",
                "claim_type": "fact",
                "confidence": "high",
                "evidence": [
                    {
                        "source_id": "NOTE-01",
                        "source_type": "salesperson_note",
                        "evidence_summary": "销售备注不能单独证明显性需求。",
                    }
                ],
            }
        ]
    }
    client = FakeWorkflowLLMClient.with_default_batch1a_responses(
        custom_payloads={"explicit_need": bad_payload}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.failures[0].failure_category.value == "schema_validation"
    assert snapshot.failures[0].node_name is WorkflowNodeName.explicit_need
    assert snapshot.explicit_needs is None
    assert snapshot.node_records[-1].node_name is WorkflowNodeName.human_review_gate
