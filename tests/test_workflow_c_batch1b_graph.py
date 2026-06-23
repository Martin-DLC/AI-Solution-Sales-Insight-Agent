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
        WorkflowNodeName.final_validation,
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


def test_underlying_pains_exist() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.underlying_pains


def test_business_impacts_exist() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.business_impacts


def test_generates_buying_intent_after_batch2a() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.buying_intent is not None


def test_does_not_generate_final_report() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.final_report is not None


def test_clarification_only_skips_business_nodes() -> None:
    case = dev_01_case().model_copy(deep=True)
    case.customer_profile.publicly_stated_goals = []
    case.customer_profile.current_systems = []
    case.known_constraints = []
    case.meeting.participants = []
    client = FakeWorkflowLLMClient.with_default_batch1b_responses()
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


def test_explicit_need_failure_skips_pain_and_impact() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1b_responses(
        invalid_json_nodes={"explicit_need"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.underlying_pain not in order
    assert WorkflowNodeName.business_impact not in order
    assert WorkflowNodeName.buying_intent not in order
    assert WorkflowNodeName.stakeholder not in order
    assert WorkflowNodeName.information_gap not in order


def test_pain_failure_skips_impact() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1b_responses(
        invalid_json_nodes={"underlying_pain"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.business_impact not in order
    assert WorkflowNodeName.buying_intent not in order
    assert WorkflowNodeName.stakeholder not in order
    assert WorkflowNodeName.information_gap not in order


def test_pain_failure_still_enters_human_review() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1b_responses(
        invalid_json_nodes={"underlying_pain"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.node_records[-1].node_name is WorkflowNodeName.human_review_gate


def test_impact_failure_still_enters_human_review() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1b_responses(
        invalid_json_nodes={"business_impact"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.node_records[-1].node_name is WorkflowNodeName.human_review_gate


def test_impact_failure_skips_intent_and_stakeholder() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1b_responses(
        invalid_json_nodes={"business_impact"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.buying_intent not in order
    assert WorkflowNodeName.stakeholder not in order
    assert WorkflowNodeName.information_gap not in order


def test_impact_failure_does_not_write_business_impacts() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1b_responses(
        invalid_json_nodes={"business_impact"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.business_impacts is None


def test_snapshot_json_serializes() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.model_dump(mode="json")["workflow_version"] == "c_skeleton_v1"
