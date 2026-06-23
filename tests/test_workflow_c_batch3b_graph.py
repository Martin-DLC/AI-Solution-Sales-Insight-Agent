from __future__ import annotations

from agent.workflow_c import (
    FakeWorkflowLLMClient,
    WorkflowNodeName,
    WorkflowServices,
    WorkflowStatus,
    run_architecture_c_skeleton,
)
from agent.workflow_c.fake_llm import default_ai_opportunity_response
from dataio.runtime_cases import load_runtime_cases


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def clarification_case_and_client():
    case = dev_01_case().model_copy(deep=True)
    case.customer_profile.publicly_stated_goals = []
    case.customer_profile.current_systems = []
    case.known_constraints = []
    case.meeting.participants = []
    client = FakeWorkflowLLMClient.with_default_batch4b_responses()
    payload = client.responses_by_node[WorkflowNodeName.fact_extraction]["fact_extraction"]
    payload["facts"] = [payload["facts"][0]]
    payload["facts"][0]["category"] = "other"
    return case, client


def test_batch3b_complete_path_node_order_includes_solution_retrieval() -> None:
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


def test_batch3b_complete_path_llm_calls_are_eleven_after_batch4b() -> None:
    client = FakeWorkflowLLMClient.with_default_batch4b_responses()

    run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert client.total_calls == 11
    assert client.calls_for_node(WorkflowNodeName.solution_retrieval) == 0
    assert client.calls_for_node(WorkflowNodeName.deal_score) == 0


def test_batch3b_generates_retrieved_solutions() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.retrieved_solutions is not None
    assert snapshot.retrieved_solutions.candidate_count >= 1


def test_clarification_only_skips_solution_retrieval_and_downstream_nodes() -> None:
    case, client = clarification_case_and_client()

    snapshot = run_architecture_c_skeleton(case, WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.solution_retrieval not in order
    assert WorkflowNodeName.ai_opportunity not in order
    assert WorkflowNodeName.solution_recommendation not in order
    assert client.total_calls == 2


def test_empty_retrieval_skips_solution_recommendation() -> None:
    payload = default_ai_opportunity_response()
    payload["ai_opportunities"][0]["suitability"] = "not_suitable_for_ai"
    payload["ai_opportunities"][0]["major_limitations"] = ["当前问题不适合AI处理。"]
    client = FakeWorkflowLLMClient.with_default_batch3b_responses(
        custom_payloads={"ai_opportunity": payload}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert snapshot.workflow_status is WorkflowStatus.awaiting_human_review
    assert snapshot.retrieved_solutions is not None
    assert snapshot.retrieved_solutions.candidate_count == 0
    assert WorkflowNodeName.solution_recommendation not in order
    assert order[-1] is WorkflowNodeName.human_review_gate


def test_solution_retrieval_failure_enters_human_review(monkeypatch) -> None:
    from agent.workflow_c.nodes.solution_retrieval import SolutionRetrievalNode

    def fail(self, state, services):
        raise ValueError("retrieval failed")

    monkeypatch.setattr(SolutionRetrievalNode, "run", fail)

    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )
    order = [record.node_name for record in snapshot.node_records]

    assert snapshot.workflow_status is WorkflowStatus.awaiting_human_review
    assert snapshot.failures[0].node_name is WorkflowNodeName.solution_retrieval
    assert WorkflowNodeName.solution_recommendation not in order
    assert order[-1] is WorkflowNodeName.human_review_gate
