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
from schemas.output_models import SalesInsightReport


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


def test_dev_01_complete_recommendation_path_builds_report_draft() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.failures == []
    assert [record.node_name for record in snapshot.node_records] == complete_order()
    assert isinstance(snapshot.report_draft, SalesInsightReport)
    assert snapshot.report_draft.reliability_summary.human_review_required is True
    assert not hasattr(snapshot, "final_report")


def test_complete_path_llm_calls_still_eleven() -> None:
    client = FakeWorkflowLLMClient.with_default_batch4b_responses()

    run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert client.total_calls == 11
    assert client.calls_for_node(WorkflowNodeName.report_composer) == 0


def test_zero_candidate_path_still_runs_report_composer() -> None:
    payload = default_ai_opportunity_response()
    payload["ai_opportunities"][0]["suitability"] = "not_suitable_for_ai"
    payload["ai_opportunities"][0]["major_limitations"] = ["当前问题不适合AI处理。"]
    client = FakeWorkflowLLMClient.with_default_batch4b_responses(
        custom_payloads={"ai_opportunity": payload}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.solution_recommendation not in order
    assert WorkflowNodeName.report_composer in order
    assert snapshot.report_draft.solution_recommendations == []
    assert "未形成可推荐候选" in snapshot.report_draft.executive_summary.primary_opportunity
    assert client.total_calls == 10


def test_clarification_only_skips_report_composer() -> None:
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

    assert order == [
        WorkflowNodeName.input_validation,
        WorkflowNodeName.source_indexing,
        WorkflowNodeName.fact_extraction,
        WorkflowNodeName.context_sufficiency,
        WorkflowNodeName.information_gap,
        WorkflowNodeName.human_review_gate,
    ]
    assert snapshot.report_draft is None
    assert client.total_calls == 2


def test_risk_failure_skips_next_best_action_and_report_composer() -> None:
    client = FakeWorkflowLLMClient.with_default_batch4b_responses(invalid_json_nodes={"risk"})

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.next_best_action not in order
    assert WorkflowNodeName.report_composer not in order
    assert snapshot.report_draft is None


def test_next_best_action_failure_skips_report_composer() -> None:
    client = FakeWorkflowLLMClient.with_default_batch4b_responses(
        invalid_json_nodes={"next_best_action"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert WorkflowNodeName.report_composer not in [record.node_name for record in snapshot.node_records]
    assert snapshot.report_draft is None


def test_report_composer_failure_enters_human_review(monkeypatch) -> None:
    from agent.workflow_c.nodes.report_composer import ReportComposerNode

    def fail(self, state, services):
        raise ValueError("composer failed")

    monkeypatch.setattr(ReportComposerNode, "run", fail)
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )
    order = [record.node_name for record in snapshot.node_records]

    assert snapshot.workflow_status is WorkflowStatus.awaiting_human_review
    assert order[-2:] == [WorkflowNodeName.report_composer, WorkflowNodeName.human_review_gate]
    assert snapshot.report_draft is None
    assert snapshot.failures[0].node_name is WorkflowNodeName.report_composer


def test_report_draft_excludes_internal_trace_fields_and_serializes() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )
    dumped = snapshot.report_draft.model_dump_json()

    assert snapshot.model_dump(mode="json")["report_draft"]["case_id"] == "DEV-01"
    for forbidden in ("risk_traces", "action_traces", "node_records", "matched_terms"):
        assert forbidden not in dumped
