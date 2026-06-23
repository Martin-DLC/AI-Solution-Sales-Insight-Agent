from __future__ import annotations

from agent.workflow_c import (
    FakeWorkflowLLMClient,
    WorkflowServices,
    find_forbidden_report_keys,
    run_architecture_c_skeleton,
    validate_report_draft,
)
from dataio.runtime_cases import load_runtime_cases
from schemas.solution_models import AIOpportunity


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def complete_snapshot():
    return run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )


def validate_from_snapshot(snapshot):
    return validate_report_draft(
        report_draft=snapshot.report_draft,
        expected_case_id=snapshot.validated_case.case_id,
        retrieved_solutions=snapshot.retrieved_solutions,
        ai_opportunities=snapshot.ai_opportunities,
        solution_recommendations=snapshot.solution_recommendations or [],
        deal_score=snapshot.deal_score,
        information_gaps=snapshot.information_gaps,
        risks_and_objections=snapshot.risks_and_objections,
        next_best_actions=snapshot.next_best_actions,
        risk_traces=snapshot.risk_traces,
        action_traces=snapshot.action_traces,
    )


def test_valid_report_passes() -> None:
    snapshot = complete_snapshot()
    result = validate_from_snapshot(snapshot)

    assert result.passed is True
    assert result.blocking_issue_count == 0
    assert result.issues == []


def test_case_id_mismatch_fails() -> None:
    snapshot = complete_snapshot()
    result = validate_report_draft(
        report_draft=snapshot.report_draft,
        expected_case_id="DEV-99",
        retrieved_solutions=snapshot.retrieved_solutions,
        ai_opportunities=snapshot.ai_opportunities,
        solution_recommendations=snapshot.solution_recommendations or [],
        deal_score=snapshot.deal_score,
        information_gaps=snapshot.information_gaps,
        risks_and_objections=snapshot.risks_and_objections,
        next_best_actions=snapshot.next_best_actions,
        risk_traces=snapshot.risk_traces,
        action_traces=snapshot.action_traces,
    )

    assert result.passed is False
    assert result.issues[0].issue_code == "CASE_ID_MISMATCH"


def test_human_review_required_false_fails() -> None:
    snapshot = complete_snapshot()
    draft = snapshot.report_draft.model_copy(deep=True)
    draft.reliability_summary.human_review_required = False
    draft.reliability_summary.human_review_reasons = ["manually changed"]
    result = validate_report_draft(
        report_draft=draft,
        expected_case_id=snapshot.validated_case.case_id,
        retrieved_solutions=snapshot.retrieved_solutions,
        ai_opportunities=snapshot.ai_opportunities,
        solution_recommendations=snapshot.solution_recommendations or [],
        deal_score=snapshot.deal_score,
        information_gaps=snapshot.information_gaps,
        risks_and_objections=snapshot.risks_and_objections,
        next_best_actions=snapshot.next_best_actions,
        risk_traces=snapshot.risk_traces,
        action_traces=snapshot.action_traces,
    )

    assert any(issue.issue_code == "HUMAN_REVIEW_DISABLED" for issue in result.issues)


def test_deal_score_total_mismatch_fails() -> None:
    snapshot = complete_snapshot()
    draft = snapshot.report_draft.model_copy(deep=True)
    object.__setattr__(draft.deal_score, "total_score", draft.deal_score.total_score + 1)

    result = validate_from_snapshot(snapshot.model_copy(update={"report_draft": draft}))
    assert any(issue.issue_code == "DEAL_SCORE_MISMATCH" for issue in result.issues)
    assert any(issue.issue_code == "DEAL_SCORE_TOTAL_INVALID" for issue in result.issues)


def test_recommendation_outside_candidates_fails() -> None:
    snapshot = complete_snapshot()
    draft = snapshot.report_draft.model_copy(deep=True)
    draft.solution_recommendations[0].solution_id = "SOLUTION-UNKNOWN"

    result = validate_from_snapshot(snapshot.model_copy(update={"report_draft": draft}))
    assert any(issue.issue_code == "SOLUTION_OUTSIDE_RETRIEVED_CANDIDATES" for issue in result.issues)


def test_zero_candidate_with_recommendation_fails() -> None:
    snapshot = complete_snapshot()
    retrieved_payload = snapshot.retrieved_solutions.model_dump(mode="json")
    retrieved_payload["candidates"] = []
    retrieved_payload["candidate_count"] = 0
    retrieved = snapshot.retrieved_solutions.__class__.model_validate(retrieved_payload)

    result = validate_report_draft(
        report_draft=snapshot.report_draft,
        expected_case_id=snapshot.validated_case.case_id,
        retrieved_solutions=retrieved,
        ai_opportunities=snapshot.ai_opportunities,
        solution_recommendations=snapshot.solution_recommendations or [],
        deal_score=snapshot.deal_score,
        information_gaps=snapshot.information_gaps,
        risks_and_objections=snapshot.risks_and_objections,
        next_best_actions=snapshot.next_best_actions,
        risk_traces=snapshot.risk_traces,
        action_traces=snapshot.action_traces,
    )

    assert any(issue.issue_code == "RECOMMENDATION_WITHOUT_CANDIDATE" for issue in result.issues)


def test_unknown_opportunity_reference_fails() -> None:
    snapshot = complete_snapshot()
    draft = snapshot.report_draft.model_copy(deep=True)
    draft.solution_recommendations[0].related_opportunity_ids = ["OPP-404"]

    result = validate_from_snapshot(snapshot.model_copy(update={"report_draft": draft}))
    assert any(issue.issue_code == "UNKNOWN_OPPORTUNITY_REFERENCE" for issue in result.issues)


def test_ineligible_opportunity_reference_fails() -> None:
    snapshot = complete_snapshot()
    opportunities_payload = [item.model_dump(mode="json") for item in snapshot.ai_opportunities]
    opportunities_payload[0]["suitability"] = "not_suitable_for_ai"
    opportunities_payload[0]["major_limitations"] = ["Needs human validation."]
    opportunities = [AIOpportunity.model_validate(item) for item in opportunities_payload]

    result = validate_report_draft(
        report_draft=snapshot.report_draft,
        expected_case_id=snapshot.validated_case.case_id,
        retrieved_solutions=snapshot.retrieved_solutions,
        ai_opportunities=opportunities,
        solution_recommendations=snapshot.solution_recommendations or [],
        deal_score=snapshot.deal_score,
        information_gaps=snapshot.information_gaps,
        risks_and_objections=snapshot.risks_and_objections,
        next_best_actions=snapshot.next_best_actions,
        risk_traces=snapshot.risk_traces,
        action_traces=snapshot.action_traces,
    )

    assert any(issue.issue_code == "INELIGIBLE_OPPORTUNITY_RECOMMENDATION" for issue in result.issues)


def test_orphan_risk_trace_fails() -> None:
    snapshot = complete_snapshot()
    traces = [trace.model_copy(deep=True) for trace in snapshot.risk_traces]
    traces[0].risk_id = "RISK-404"

    result = validate_report_draft(
        report_draft=snapshot.report_draft,
        expected_case_id=snapshot.validated_case.case_id,
        retrieved_solutions=snapshot.retrieved_solutions,
        ai_opportunities=snapshot.ai_opportunities,
        solution_recommendations=snapshot.solution_recommendations or [],
        deal_score=snapshot.deal_score,
        information_gaps=snapshot.information_gaps,
        risks_and_objections=snapshot.risks_and_objections,
        next_best_actions=snapshot.next_best_actions,
        risk_traces=traces,
        action_traces=snapshot.action_traces,
    )

    assert any(issue.issue_code == "ORPHAN_RISK_TRACE" for issue in result.issues)


def test_p0_action_without_critical_driver_fails() -> None:
    snapshot = complete_snapshot()
    action_traces = [trace.model_copy(deep=True) for trace in snapshot.action_traces]
    action_traces[0].related_risk_ids = []
    information_gaps = [gap.model_copy(deep=True) for gap in snapshot.information_gaps]
    for gap in information_gaps:
        gap.priority = "medium"
    risks = [risk.model_copy(deep=True) for risk in snapshot.risks_and_objections]
    for risk in risks:
        risk.severity = "medium"

    result = validate_report_draft(
        report_draft=snapshot.report_draft,
        expected_case_id=snapshot.validated_case.case_id,
        retrieved_solutions=snapshot.retrieved_solutions,
        ai_opportunities=snapshot.ai_opportunities,
        solution_recommendations=snapshot.solution_recommendations or [],
        deal_score=snapshot.deal_score,
        information_gaps=information_gaps,
        risks_and_objections=risks,
        next_best_actions=snapshot.next_best_actions,
        risk_traces=snapshot.risk_traces,
        action_traces=action_traces,
    )

    assert any(issue.issue_code == "P0_ACTION_WITHOUT_CRITICAL_DRIVER" for issue in result.issues)


def test_find_forbidden_report_keys_recurses() -> None:
    payload = {
        "safe": [{"risk_traces": [{"action_trace": "x"}]}],
        "nested": {"node_records": []},
    }
    paths = find_forbidden_report_keys(payload)

    assert paths == ["$.safe[0].risk_traces", "$.safe[0].risk_traces[0].action_trace", "$.nested.node_records"]


def test_validation_does_not_modify_inputs() -> None:
    snapshot = complete_snapshot()
    before_report = snapshot.report_draft.model_dump(mode="json")
    before_retrieved = snapshot.retrieved_solutions.model_dump(mode="json")
    before_traces = [trace.model_dump(mode="json") for trace in snapshot.risk_traces]

    _ = validate_from_snapshot(snapshot)

    assert snapshot.report_draft.model_dump(mode="json") == before_report
    assert snapshot.retrieved_solutions.model_dump(mode="json") == before_retrieved
    assert [trace.model_dump(mode="json") for trace in snapshot.risk_traces] == before_traces
