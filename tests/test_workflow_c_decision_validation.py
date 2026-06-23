from __future__ import annotations

from agent.workflow_c import FakeWorkflowLLMClient, WorkflowServices, run_architecture_c_skeleton
from agent.workflow_c.decision_models import ActionTrace, WorkflowActionType
from agent.workflow_c.decision_validation import (
    validate_action_quality,
    validate_action_stage_compatibility,
    validate_p0_action_grounding,
    validate_related_gap_ids,
    validate_related_risk_ids,
)
from dataio.runtime_cases import load_runtime_cases
from schemas.common_models import ActionPriority, DealScoreLevel


def snapshot():
    case = load_runtime_cases("data/evaluation/development_cases.jsonl")[0]
    return run_architecture_c_skeleton(
        case,
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )


def test_gap_id_exists_passes() -> None:
    state = snapshot()
    assert not validate_related_gap_ids(
        field_prefix="x",
        referenced_ids=[state.information_gaps[0].gap_id],
        information_gaps=state.information_gaps,
    )


def test_gap_id_missing_fails() -> None:
    state = snapshot()
    issues = validate_related_gap_ids(
        field_prefix="x",
        referenced_ids=["GAP-MISSING"],
        information_gaps=state.information_gaps,
    )
    assert issues


def test_risk_id_exists_passes() -> None:
    state = snapshot()
    assert not validate_related_risk_ids(
        field_prefix="x",
        referenced_ids=[state.risks_and_objections[0].risk_id],
        risks_and_objections=state.risks_and_objections,
    )


def test_risk_id_missing_fails() -> None:
    state = snapshot()
    assert validate_related_risk_ids(
        field_prefix="x",
        referenced_ids=["RISK-MISSING"],
        risks_and_objections=state.risks_and_objections,
    )


def test_p0_action_with_high_gap_passes() -> None:
    state = snapshot()
    action = state.next_best_actions[0]
    trace = state.action_traces[0].model_copy(update={"related_risk_ids": []})
    assert not validate_p0_action_grounding(
        action=action,
        action_trace=trace,
        information_gaps=state.information_gaps,
        risks_and_objections=state.risks_and_objections,
    )


def test_p0_action_without_high_gap_or_risk_fails() -> None:
    state = snapshot()
    action = state.next_best_actions[0].model_copy(update={"related_gap_ids": []})
    trace = state.action_traces[0].model_copy(update={"related_risk_ids": []})
    assert validate_p0_action_grounding(
        action=action,
        action_trace=trace,
        information_gaps=state.information_gaps,
        risks_and_objections=state.risks_and_objections,
    )


def test_discovery_with_budget_gap_blocks_commercial_proposal() -> None:
    state = snapshot()
    action = state.next_best_actions[0]
    trace = ActionTrace(
        action_id=action.action_id,
        related_risk_ids=[state.risks_and_objections[0].risk_id],
        action_type=WorkflowActionType.commercial_proposal,
    )
    assert validate_action_stage_compatibility(
        action=action,
        action_trace=trace,
        buying_intent=state.buying_intent,
        deal_score=state.deal_score,
        information_gaps=state.information_gaps,
        stakeholder_map=state.stakeholder_map,
    )


def test_low_deal_score_qualification_action_passes() -> None:
    state = snapshot()
    action = state.next_best_actions[0]
    trace = ActionTrace(
        action_id=action.action_id,
        related_risk_ids=[state.risks_and_objections[0].risk_id],
        action_type=WorkflowActionType.qualification,
    )
    deal_score = state.deal_score.model_copy(update={"score_level": DealScoreLevel.low})
    assert not validate_action_stage_compatibility(
        action=action,
        action_trace=trace,
        buying_intent=state.buying_intent,
        deal_score=deal_score,
        information_gaps=state.information_gaps,
        stakeholder_map=state.stakeholder_map,
    )


def test_vague_action_fails() -> None:
    state = snapshot()
    action = state.next_best_actions[0].model_copy(update={"action": "后续确认"})
    assert validate_action_quality(action)


def test_specific_action_passes() -> None:
    state = snapshot()
    assert not validate_action_quality(state.next_best_actions[0])


def test_issue_does_not_include_full_customer_text() -> None:
    state = snapshot()
    issue = validate_related_gap_ids(
        field_prefix="x",
        referenced_ids=["GAP-MISSING"],
        information_gaps=state.information_gaps,
    )[0]
    assert "客户希望" not in str(issue.model_dump(mode="json"))


def test_does_not_read_reference_pack() -> None:
    source = "\n".join(issue.message for issue in validate_related_gap_ids(
        field_prefix="x",
        referenced_ids=["GAP-MISSING"],
        information_gaps=snapshot().information_gaps,
    ))
    assert "Reference Pack" not in source
