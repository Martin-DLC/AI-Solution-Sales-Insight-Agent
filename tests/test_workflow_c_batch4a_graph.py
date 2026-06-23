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
from schemas.common_models import DealScoreDimensionName


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
        WorkflowNodeName.report_composer,
        WorkflowNodeName.human_review_gate,
    ]


def test_dev_01_complete_recommendation_path_offline_success() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.failures == []


def test_recommendation_success_path_has_seventeen_nodes() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert [record.node_name for record in snapshot.node_records] == complete_order()


def test_fake_llm_total_calls_is_eleven() -> None:
    client = FakeWorkflowLLMClient.with_default_batch4b_responses()

    run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert client.total_calls == 11
    assert client.calls_for_node(WorkflowNodeName.deal_score) == 0


def test_deal_score_exists_and_has_seven_dimensions() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.failures == []
    assert snapshot.deal_score is not None
    assert len(snapshot.deal_score.dimensions) == 7


def test_default_recommendation_matches_retrieved_candidate() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.failures == []
    assert snapshot.retrieved_solutions is not None
    assert snapshot.solution_recommendations is not None
    candidate = snapshot.retrieved_solutions.candidates[0]
    recommendation = snapshot.solution_recommendations[0]
    reference = recommendation.knowledge_references[0]
    assert recommendation.solution_id == candidate.solution_id
    assert reference.source_id == candidate.source_id


def test_total_score_is_between_zero_and_one_hundred() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.deal_score is not None
    assert 0 <= snapshot.deal_score.total_score <= 100


def test_reasoning_summary_says_not_probability() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.deal_score is not None
    assert "不等于成交概率" in snapshot.deal_score.reasoning_summary


def test_does_not_generate_risk_next_action_or_final_report() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert not hasattr(snapshot, "risk")
    assert not hasattr(snapshot, "next_best_action")
    assert not hasattr(snapshot, "final_report")


def test_zero_candidate_path_still_runs_deal_score() -> None:
    payload = default_ai_opportunity_response()
    payload["ai_opportunities"][0]["suitability"] = "not_suitable_for_ai"
    payload["ai_opportunities"][0]["major_limitations"] = ["当前问题不适合AI处理。"]
    client = FakeWorkflowLLMClient.with_default_batch4b_responses(
        custom_payloads={"ai_opportunity": payload}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.deal_score in order
    assert WorkflowNodeName.solution_recommendation not in order
    assert snapshot.deal_score is not None


def test_zero_candidate_path_fake_llm_calls_is_eight() -> None:
    payload = default_ai_opportunity_response()
    payload["ai_opportunities"][0]["suitability"] = "not_suitable_for_ai"
    payload["ai_opportunities"][0]["major_limitations"] = ["当前问题不适合AI处理。"]
    client = FakeWorkflowLLMClient.with_default_batch4b_responses(
        custom_payloads={"ai_opportunity": payload}
    )

    run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert client.total_calls == 10
    assert client.calls_for_node(WorkflowNodeName.deal_score) == 0


def test_zero_candidate_solution_fit_is_zero_without_eligible_opportunity() -> None:
    payload = default_ai_opportunity_response()
    payload["ai_opportunities"][0]["suitability"] = "not_suitable_for_ai"
    payload["ai_opportunities"][0]["major_limitations"] = ["当前问题不适合AI处理。"]
    client = FakeWorkflowLLMClient.with_default_batch4b_responses(
        custom_payloads={"ai_opportunity": payload}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    assert snapshot.deal_score is not None
    solution_fit = next(
        dimension
        for dimension in snapshot.deal_score.dimensions
        if dimension.dimension is DealScoreDimensionName.solution_fit
    )

    assert solution_fit.score == 0


def test_recommendation_failure_skips_deal_score() -> None:
    client = FakeWorkflowLLMClient.with_default_batch4b_responses(
        invalid_json_nodes={"solution_recommendation"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.deal_score not in order
    assert snapshot.deal_score is None


def test_deal_score_failure_enters_human_review(monkeypatch) -> None:
    from agent.workflow_c.nodes.deal_score import DealScoreNode

    def fail(self, state, services):
        raise ValueError("deal score failed")

    monkeypatch.setattr(DealScoreNode, "run", fail)

    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.workflow_status is WorkflowStatus.awaiting_human_review
    assert snapshot.failures[0].node_name is WorkflowNodeName.deal_score
    assert snapshot.deal_score is None
    assert snapshot.node_records[-1].node_name is WorkflowNodeName.human_review_gate


def test_clarification_only_does_not_run_deal_score() -> None:
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

    assert WorkflowNodeName.deal_score not in order
    assert snapshot.deal_score is None
    assert client.total_calls == 2


def test_snapshot_json_serializes() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    dumped = snapshot.model_dump(mode="json")
    assert dumped["deal_score"]["total_score"] == snapshot.deal_score.total_score
