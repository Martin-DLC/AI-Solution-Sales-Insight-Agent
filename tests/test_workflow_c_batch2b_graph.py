from __future__ import annotations

from agent.workflow_c import (
    FakeWorkflowLLMClient,
    WorkflowNodeName,
    WorkflowServices,
    WorkflowStatus,
    run_architecture_c_skeleton,
)
from agent.workflow_c.fake_llm import default_stakeholder_response
from dataio.runtime_cases import load_runtime_cases


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def clarification_case_and_client():
    case = dev_01_case().model_copy(deep=True)
    case.customer_profile.publicly_stated_goals = []
    case.customer_profile.current_systems = []
    case.known_constraints = []
    case.meeting.participants = []
    client = FakeWorkflowLLMClient.with_default_batch3a_responses()
    payload = client.responses_by_node[WorkflowNodeName.fact_extraction]["fact_extraction"]
    payload["facts"] = [payload["facts"][0]]
    payload["facts"][0]["category"] = "other"
    return case, client


def test_dev_01_full_path_offline_success() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3a_responses()),
    )

    assert snapshot.failures == []


def test_full_path_node_order_has_thirteen_nodes_after_batch3a() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3a_responses()),
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
        WorkflowNodeName.solution_recommendation,
        WorkflowNodeName.human_review_gate,
    ]


def test_full_path_fake_llm_total_calls_is_nine_after_batch3a() -> None:
    client = FakeWorkflowLLMClient.with_default_batch3a_responses()

    run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert client.total_calls == 9


def test_nine_llm_nodes_called_once() -> None:
    client = FakeWorkflowLLMClient.with_default_batch3a_responses()

    run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert client.calls_for_node(WorkflowNodeName.fact_extraction) == 1
    assert client.calls_for_node(WorkflowNodeName.explicit_need) == 1
    assert client.calls_for_node(WorkflowNodeName.underlying_pain) == 1
    assert client.calls_for_node(WorkflowNodeName.business_impact) == 1
    assert client.calls_for_node(WorkflowNodeName.buying_intent) == 1
    assert client.calls_for_node(WorkflowNodeName.stakeholder) == 1
    assert client.calls_for_node(WorkflowNodeName.information_gap) == 1
    assert client.calls_for_node(WorkflowNodeName.ai_opportunity) == 1
    assert client.calls_for_node(WorkflowNodeName.solution_recommendation) == 1


def test_final_status_awaits_human_review() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3a_responses()),
    )

    assert snapshot.workflow_status is WorkflowStatus.awaiting_human_review


def test_information_gaps_exist() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3a_responses()),
    )

    assert snapshot.information_gaps


def test_generates_ai_opportunities_after_batch3a() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3a_responses()),
    )

    assert snapshot.ai_opportunities is not None


def test_does_not_generate_deal_score() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3a_responses()),
    )

    assert not hasattr(snapshot, "deal_score")


def test_does_not_generate_final_report() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3a_responses()),
    )

    assert not hasattr(snapshot, "final_report")


def test_clarification_only_path_runs_information_gap() -> None:
    case, client = clarification_case_and_client()

    snapshot = run_architecture_c_skeleton(case, WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.information_gap in order


def test_clarification_only_path_skips_explicit_need() -> None:
    case, client = clarification_case_and_client()

    snapshot = run_architecture_c_skeleton(case, WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.explicit_need not in order


def test_clarification_only_path_skips_downstream_analysis_nodes() -> None:
    case, client = clarification_case_and_client()

    snapshot = run_architecture_c_skeleton(case, WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.underlying_pain not in order
    assert WorkflowNodeName.business_impact not in order
    assert WorkflowNodeName.buying_intent not in order
    assert WorkflowNodeName.stakeholder not in order


def test_clarification_only_path_fake_llm_total_calls_is_two() -> None:
    case, client = clarification_case_and_client()

    run_architecture_c_skeleton(case, WorkflowServices(llm=client))

    assert client.total_calls == 2


def test_clarification_only_path_outputs_information_gaps() -> None:
    case, client = clarification_case_and_client()

    snapshot = run_architecture_c_skeleton(case, WorkflowServices(llm=client))

    assert snapshot.information_gaps


def test_stakeholder_failure_skips_information_gap() -> None:
    client = FakeWorkflowLLMClient.with_default_batch2b_responses(
        invalid_json_nodes={"stakeholder"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.information_gap not in order


def test_information_gap_failure_still_enters_human_review() -> None:
    client = FakeWorkflowLLMClient.with_default_batch2b_responses(
        invalid_json_nodes={"information_gap"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.node_records[-1].node_name is WorkflowNodeName.human_review_gate


def test_information_gap_failure_does_not_write_information_gaps() -> None:
    client = FakeWorkflowLLMClient.with_default_batch2b_responses(
        invalid_json_nodes={"information_gap"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.information_gaps is None


def test_unconfirmed_stakeholder_missing_next_validation_stops_before_information_gap() -> None:
    payload = default_stakeholder_response()
    payload["stakeholder_map"][1]["next_validation"] = None
    client = FakeWorkflowLLMClient.with_default_batch2b_responses(
        custom_payloads={"stakeholder": payload}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert snapshot.failures[0].node_name is WorkflowNodeName.stakeholder
    assert WorkflowNodeName.information_gap not in order


def test_snapshot_json_serializes() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3a_responses()),
    )

    assert snapshot.model_dump(mode="json")["information_gaps"][0]["gap_id"] == "GAP-01"
