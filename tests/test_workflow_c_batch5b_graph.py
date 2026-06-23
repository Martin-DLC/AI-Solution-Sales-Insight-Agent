from __future__ import annotations

from agent.workflow_c import (
    FakeWorkflowLLMClient,
    FinalValidationResult,
    WorkflowNodeName,
    WorkflowServices,
    run_architecture_c_skeleton,
)
from agent.workflow_c.final_validation import FinalValidationIssue
from agent.workflow_c.fake_llm import default_ai_opportunity_response
from agent.workflow_c.state import HumanReviewStatus
from dataio.runtime_cases import load_runtime_cases


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def test_complete_path_generates_passed_final_validation_and_final_report() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.final_validation_result.passed is True
    assert snapshot.final_report is not None
    assert snapshot.final_report.model_dump(mode="json") == snapshot.report_draft.model_dump(mode="json")


def test_complete_path_llm_calls_still_eleven() -> None:
    client = FakeWorkflowLLMClient.with_default_batch4b_responses()
    run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert client.total_calls == 11
    assert client.calls_for_node(WorkflowNodeName.final_validation) == 0


def test_zero_candidate_path_generates_final_report_and_ten_calls() -> None:
    payload = default_ai_opportunity_response()
    payload["ai_opportunities"][0]["suitability"] = "not_suitable_for_ai"
    payload["ai_opportunities"][0]["major_limitations"] = ["当前问题不适合AI处理。"]
    client = FakeWorkflowLLMClient.with_default_batch4b_responses(
        custom_payloads={"ai_opportunity": payload}
    )
    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.final_validation_result.passed is True
    assert snapshot.final_report is not None
    assert snapshot.final_report.solution_recommendations == []
    assert client.total_calls == 10


def test_validation_failure_keeps_report_draft_and_clears_final_report(monkeypatch) -> None:
    from agent.workflow_c.nodes import final_validation as module

    def fake_validate_report_draft(**kwargs):
        return FinalValidationResult(
            passed=False,
            issues=[
                FinalValidationIssue(
                    issue_code="FORCED_FAILURE",
                    location="report_draft",
                    message="Forced failure for graph test.",
                    blocking=True,
                )
            ],
            blocking_issue_count=1,
        )

    monkeypatch.setattr(module, "validate_report_draft", fake_validate_report_draft)
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )

    assert snapshot.report_draft is not None
    assert snapshot.final_validation_result.passed is False
    assert snapshot.final_report is None
    assert snapshot.human_review_decision.status is HumanReviewStatus.pending


def test_clarification_only_skips_report_composer_and_final_validation() -> None:
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

    assert WorkflowNodeName.report_composer not in order
    assert WorkflowNodeName.final_validation not in order
    assert snapshot.report_draft is None
    assert snapshot.final_validation_result is None
    assert snapshot.final_report is None
