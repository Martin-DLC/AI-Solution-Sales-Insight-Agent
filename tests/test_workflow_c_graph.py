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


def test_dev_01_minimal_graph_runs_offline() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )

    assert snapshot.run_id.startswith("C-")


def test_final_status_is_awaiting_human_review() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )

    assert snapshot.workflow_status is WorkflowStatus.awaiting_human_review


def test_node_execution_order_is_expected() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )

    assert [record.node_name for record in snapshot.node_records] == [
        WorkflowNodeName.input_validation,
        WorkflowNodeName.source_indexing,
        WorkflowNodeName.fact_extraction,
        WorkflowNodeName.context_sufficiency,
        WorkflowNodeName.human_review_gate,
    ]


def test_each_node_runs_once() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )

    counts = {record.node_name: 0 for record in snapshot.node_records}
    for record in snapshot.node_records:
        counts[record.node_name] += 1
    assert set(counts.values()) == {1}


def test_fake_llm_called_once() -> None:
    client = FakeWorkflowLLMClient.with_default_fact_response()
    run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert client.call_count == 1
    assert client.total_calls == 1


def test_graph_generates_source_index() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )

    assert snapshot.source_index is not None


def test_graph_generates_fact_extraction() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )

    assert snapshot.fact_extraction is not None


def test_graph_generates_context_sufficiency() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )

    assert snapshot.context_sufficiency is not None


def test_graph_generates_human_review_decision() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )

    assert snapshot.human_review_decision is not None


def test_graph_does_not_generate_final_report() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )

    assert not hasattr(snapshot, "final_report")


def test_graph_does_not_generate_sales_insight_report() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )

    assert not hasattr(snapshot, "sales_insight_report")


def test_two_runs_have_different_run_ids() -> None:
    first = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )
    second = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )

    assert first.run_id != second.run_id


def test_final_snapshot_json_serializes() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )

    assert snapshot.model_dump(mode="json")["architecture_version"] == "C"
