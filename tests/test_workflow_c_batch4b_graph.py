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


def complete_order() -> list[WorkflowNodeName]:
    return [
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


def test_dev_01_complete_path_success() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )
    assert snapshot.failures == []


def test_complete_path_node_order_has_seventeen_nodes() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )
    assert [record.node_name for record in snapshot.node_records] == complete_order()


def test_complete_path_llm_calls_is_eleven() -> None:
    client = FakeWorkflowLLMClient.with_default_batch4b_responses()
    run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    assert client.total_calls == 11
    assert client.calls_for_node(WorkflowNodeName.deal_score) == 0
    assert client.calls_for_node(WorkflowNodeName.solution_retrieval) == 0


def test_risk_and_next_best_action_exist() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )
    assert snapshot.risks_and_objections
    assert snapshot.risk_traces
    assert snapshot.next_best_actions
    assert snapshot.action_traces
    assert not hasattr(snapshot, "final_report")


def test_zero_candidate_path_still_generates_risk_and_action() -> None:
    payload = default_ai_opportunity_response()
    payload["ai_opportunities"][0]["suitability"] = "not_suitable_for_ai"
    payload["ai_opportunities"][0]["major_limitations"] = ["当前问题不适合AI处理。"]
    client = FakeWorkflowLLMClient.with_default_batch4b_responses(
        custom_payloads={"ai_opportunity": payload}
    )
    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]
    assert WorkflowNodeName.solution_recommendation not in order
    assert WorkflowNodeName.risk in order
    assert WorkflowNodeName.next_best_action in order
    assert client.total_calls == 10


def test_deal_score_failure_skips_risk_and_action(monkeypatch) -> None:
    from agent.workflow_c.nodes.deal_score import DealScoreNode

    monkeypatch.setattr(DealScoreNode, "run", lambda self, state, services: (_ for _ in ()).throw(ValueError("boom")))
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )
    order = [record.node_name for record in snapshot.node_records]
    assert WorkflowNodeName.risk not in order
    assert WorkflowNodeName.next_best_action not in order


def test_risk_failure_skips_next_best_action() -> None:
    client = FakeWorkflowLLMClient.with_default_batch4b_responses(invalid_json_nodes={"risk"})
    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]
    assert snapshot.workflow_status is WorkflowStatus.awaiting_human_review
    assert WorkflowNodeName.next_best_action not in order
    assert snapshot.risks_and_objections is None


def test_next_best_action_failure_enters_human_review() -> None:
    client = FakeWorkflowLLMClient.with_default_batch4b_responses(
        invalid_json_nodes={"next_best_action"}
    )
    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    assert snapshot.workflow_status is WorkflowStatus.awaiting_human_review
    assert snapshot.next_best_actions is None


def test_clarification_only_skips_risk_and_action() -> None:
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
    assert WorkflowNodeName.risk not in order
    assert WorkflowNodeName.next_best_action not in order
    assert client.total_calls == 2


def test_snapshot_json_serializes() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )
    assert snapshot.model_dump(mode="json")["risk_traces"][0]["risk_id"]


def test_dynamic_fake_uses_real_gap_and_risk_ids() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )
    gap_ids = {gap.gap_id for gap in snapshot.information_gaps}
    risk_ids = {risk.risk_id for risk in snapshot.risks_and_objections}
    assert set(snapshot.risk_traces[0].related_gap_ids) <= gap_ids
    assert set(snapshot.action_traces[0].related_risk_ids) <= risk_ids
