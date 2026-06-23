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


def test_dev_01_offline_success() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.failures == []


def test_success_node_order_includes_batch4b_nodes() -> None:
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
        WorkflowNodeName.report_composer,
        WorkflowNodeName.human_review_gate,
    ]


def test_fake_llm_total_calls_is_eleven_after_batch4b() -> None:
    client = FakeWorkflowLLMClient.with_default_batch4b_responses()

    run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert client.total_calls == 11


def test_each_llm_node_called_once() -> None:
    client = FakeWorkflowLLMClient.with_default_batch4b_responses()

    run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

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


def test_final_status_awaits_human_review() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.workflow_status is WorkflowStatus.awaiting_human_review


def test_buying_intent_exists() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.buying_intent is not None


def test_stakeholder_map_exists() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.stakeholder_map


def test_generates_information_gaps_after_batch2b() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.information_gaps


def test_generates_deal_score_after_batch4a() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.deal_score is not None


def test_does_not_generate_final_report() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert not hasattr(snapshot, "final_report")


def test_clarification_only_skips_all_analysis_nodes_after_context() -> None:
    case = dev_01_case().model_copy(deep=True)
    case.customer_profile.publicly_stated_goals = []
    case.customer_profile.current_systems = []
    case.known_constraints = []
    case.meeting.participants = []
    client = FakeWorkflowLLMClient.with_default_batch4b_responses()
    payload = client.responses_by_node[WorkflowNodeName.fact_extraction]["fact_extraction"]
    payload["facts"] = [payload["facts"][0]]
    payload["facts"][0]["category"] = "other"

    snapshot = run_architecture_c_skeleton(case, WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.explicit_need not in order
    assert WorkflowNodeName.underlying_pain not in order
    assert WorkflowNodeName.business_impact not in order
    assert WorkflowNodeName.buying_intent not in order
    assert WorkflowNodeName.stakeholder not in order
    assert WorkflowNodeName.information_gap in order


def test_business_impact_failure_skips_intent_and_stakeholder() -> None:
    client = FakeWorkflowLLMClient.with_default_batch2a_responses(
        invalid_json_nodes={"business_impact"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.buying_intent not in order
    assert WorkflowNodeName.stakeholder not in order
    assert WorkflowNodeName.information_gap not in order


def test_buying_intent_failure_skips_stakeholder() -> None:
    client = FakeWorkflowLLMClient.with_default_batch2a_responses(
        invalid_json_nodes={"buying_intent"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.stakeholder not in order
    assert WorkflowNodeName.information_gap not in order


def test_buying_intent_failure_still_enters_human_review() -> None:
    client = FakeWorkflowLLMClient.with_default_batch2a_responses(
        invalid_json_nodes={"buying_intent"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.node_records[-1].node_name is WorkflowNodeName.human_review_gate


def test_stakeholder_failure_still_enters_human_review() -> None:
    client = FakeWorkflowLLMClient.with_default_batch2a_responses(
        invalid_json_nodes={"stakeholder"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.node_records[-1].node_name is WorkflowNodeName.human_review_gate


def test_stakeholder_failure_does_not_write_stakeholder_map() -> None:
    client = FakeWorkflowLLMClient.with_default_batch2a_responses(
        invalid_json_nodes={"stakeholder"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.stakeholder_map is None


def test_unconfirmed_stakeholder_without_next_validation_fails_schema_validation() -> None:
    payload = default_stakeholder_response()
    payload["stakeholder_map"][1]["next_validation"] = None
    client = FakeWorkflowLLMClient.with_default_batch2a_responses(
        custom_payloads={"stakeholder": payload}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.failures[0].node_name is WorkflowNodeName.stakeholder
    assert snapshot.failures[0].failure_category.value == "schema_validation"


def test_snapshot_json_serializes() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.model_dump(mode="json")["workflow_version"] == "c_skeleton_v1"
