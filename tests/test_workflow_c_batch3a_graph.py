from __future__ import annotations

from agent.workflow_c import (
    FakeWorkflowLLMClient,
    WorkflowNodeName,
    WorkflowServices,
    WorkflowStatus,
    run_architecture_c_skeleton,
)
from agent.workflow_c.fake_llm import default_solution_recommendation_response
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


def test_dev_01_complete_path_offline_success() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3a_responses()),
    )

    assert snapshot.failures == []


def test_complete_path_node_order_has_thirteen_nodes() -> None:
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
        WorkflowNodeName.solution_retrieval,
        WorkflowNodeName.solution_recommendation,
        WorkflowNodeName.deal_score,
        WorkflowNodeName.human_review_gate,
    ]


def test_complete_path_fake_llm_total_calls_is_nine() -> None:
    client = FakeWorkflowLLMClient.with_default_batch3a_responses()

    run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert client.total_calls == 9


def test_nine_llm_nodes_called_once() -> None:
    client = FakeWorkflowLLMClient.with_default_batch3a_responses()

    run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    for node_name in (
        WorkflowNodeName.fact_extraction,
        WorkflowNodeName.explicit_need,
        WorkflowNodeName.underlying_pain,
        WorkflowNodeName.business_impact,
        WorkflowNodeName.buying_intent,
        WorkflowNodeName.stakeholder,
        WorkflowNodeName.information_gap,
        WorkflowNodeName.ai_opportunity,
        WorkflowNodeName.solution_recommendation,
    ):
        assert client.calls_for_node(node_name) == 1
    assert client.calls_for_node(WorkflowNodeName.solution_retrieval) == 0
    assert client.calls_for_node(WorkflowNodeName.deal_score) == 0


def test_final_status_awaits_human_review() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3a_responses()),
    )

    assert snapshot.workflow_status is WorkflowStatus.awaiting_human_review


def test_ai_opportunities_exist() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3a_responses()),
    )

    assert snapshot.ai_opportunities


def test_solution_recommendations_field_exists() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3a_responses()),
    )

    assert snapshot.solution_recommendations is not None


def test_generates_retrieved_solutions() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3a_responses()),
    )

    assert snapshot.retrieved_solutions is not None


def test_generates_deal_score_after_batch4a() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3a_responses()),
    )

    assert snapshot.deal_score is not None


def test_does_not_generate_final_report() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3a_responses()),
    )

    assert not hasattr(snapshot, "final_report")


def test_clarification_only_skips_ai_opportunity() -> None:
    case, client = clarification_case_and_client()

    snapshot = run_architecture_c_skeleton(case, WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.ai_opportunity not in order
    assert WorkflowNodeName.solution_retrieval not in order


def test_clarification_only_skips_solution_recommendation() -> None:
    case, client = clarification_case_and_client()

    snapshot = run_architecture_c_skeleton(case, WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.solution_recommendation not in order
    assert WorkflowNodeName.solution_retrieval not in order


def test_information_gap_failure_skips_two_new_nodes() -> None:
    client = FakeWorkflowLLMClient.with_default_batch3a_responses(
        invalid_json_nodes={"information_gap"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.ai_opportunity not in order
    assert WorkflowNodeName.solution_retrieval not in order
    assert WorkflowNodeName.solution_recommendation not in order


def test_ai_opportunity_failure_skips_solution_recommendation() -> None:
    client = FakeWorkflowLLMClient.with_default_batch3a_responses(
        invalid_json_nodes={"ai_opportunity"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.solution_recommendation not in order
    assert WorkflowNodeName.solution_retrieval not in order


def test_ai_opportunity_failure_still_enters_human_review() -> None:
    client = FakeWorkflowLLMClient.with_default_batch3a_responses(
        invalid_json_nodes={"ai_opportunity"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.node_records[-1].node_name is WorkflowNodeName.human_review_gate


def test_solution_recommendation_failure_still_enters_human_review() -> None:
    client = FakeWorkflowLLMClient.with_default_batch3a_responses(
        invalid_json_nodes={"solution_recommendation"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.node_records[-1].node_name is WorkflowNodeName.human_review_gate


def test_solution_recommendation_failure_does_not_write_output() -> None:
    client = FakeWorkflowLLMClient.with_default_batch3a_responses(
        invalid_json_nodes={"solution_recommendation"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.solution_recommendations is None


def test_outside_library_solution_id_creates_schema_validation_failure() -> None:
    payload = default_solution_recommendation_response()
    payload["solution_recommendations"][0]["solution_id"] = "outside-library-solution"
    client = FakeWorkflowLLMClient.with_default_batch3a_responses(
        custom_payloads={"solution_recommendation": payload}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.failures[0].node_name is WorkflowNodeName.solution_recommendation
    assert snapshot.solution_recommendations is None


def test_snapshot_json_serializes() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3a_responses()),
    )

    dumped = snapshot.model_dump(mode="json")
    assert dumped["ai_opportunities"][0]["opportunity_id"] == "OPP-01"
