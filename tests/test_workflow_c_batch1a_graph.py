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


def test_batch1a_success_path_node_order() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch1a_responses()),
    )

    assert [record.node_name for record in snapshot.node_records] == [
        WorkflowNodeName.input_validation,
        WorkflowNodeName.source_indexing,
        WorkflowNodeName.fact_extraction,
        WorkflowNodeName.context_sufficiency,
        WorkflowNodeName.explicit_need,
        WorkflowNodeName.human_review_gate,
    ]


def test_batch1a_success_path_llm_calls_twice() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1a_responses()

    run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert client.total_calls == 2
    assert client.calls_for_node(WorkflowNodeName.fact_extraction) == 1
    assert client.calls_for_node(WorkflowNodeName.explicit_need) == 1


def test_batch1a_final_status_still_awaits_human_review() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch1a_responses()),
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
    assert order[-1] is WorkflowNodeName.human_review_gate


def test_explicit_need_failure_still_runs_human_review_gate() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1a_responses(
        invalid_json_nodes={"explicit_need"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.failures[0].node_name is WorkflowNodeName.explicit_need
    assert snapshot.node_records[-1].node_name is WorkflowNodeName.human_review_gate


def test_batch1a_snapshot_serializes_explicit_needs() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch1a_responses()),
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
