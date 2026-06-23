from __future__ import annotations

import json
from typing import Any

from agent.workflow_c.contracts import NodeContract, NodeFailurePolicy
from agent.workflow_c.decision_validation import (
    validate_action_quality,
    validate_action_stage_compatibility,
    validate_action_traces,
    validate_p0_action_grounding,
    validate_related_gap_ids,
)
from agent.workflow_c.failures import NodeBusinessRuleError, NodeJSONParseError
from agent.workflow_c.node_outputs import NextBestActionNodeOutput
from agent.workflow_c.prompt_loader import render_next_best_action_messages
from agent.workflow_c.state import NodeValidationIssue, WorkflowNodeName
from schemas.decision_models import DealScore, NextBestAction
from schemas.insight_models import BuyingIntent, InformationGap, Stakeholder
from schemas.solution_models import Risk


class NextBestActionNode:
    contract = NodeContract(
        name=WorkflowNodeName.next_best_action,
        required_state_fields=(
            "buying_intent",
            "stakeholder_map",
            "information_gaps",
            "deal_score",
            "risks_and_objections",
        ),
        produced_state_fields=("next_best_actions", "action_traces"),
        output_model=NextBestActionNodeOutput,
        failure_policy=NodeFailurePolicy.require_human_review,
        prompt_version="next_best_action_v1",
    )

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        buying_intent: BuyingIntent = state["buying_intent"]
        stakeholder_map: list[Stakeholder] = state["stakeholder_map"]
        information_gaps: list[InformationGap] = state["information_gaps"]
        deal_score: DealScore = state["deal_score"]
        risks_and_objections: list[Risk] = state["risks_and_objections"]
        messages = render_next_best_action_messages(
            buying_intent,
            stakeholder_map,
            information_gaps,
            deal_score,
            risks_and_objections,
        )
        result = services.llm.complete_json_for_node(
            WorkflowNodeName.next_best_action,
            messages,
        )
        parsed = result.parsed_json
        if parsed is None:
            try:
                parsed = json.loads(result.content)
            except json.JSONDecodeError as exc:
                raise NodeJSONParseError(
                    message="Next best action analysis returned invalid JSON.",
                    content_length=len(result.content),
                    position=exc.pos,
                ) from exc

        output = NextBestActionNodeOutput.model_validate(parsed)
        _validate_action_rules(
            output.next_best_actions,
            output.action_traces,
            buying_intent,
            stakeholder_map,
            information_gaps,
            deal_score,
            risks_and_objections,
        )
        return {
            "next_best_actions": output.next_best_actions,
            "action_traces": output.action_traces,
        }


def _validate_action_rules(
    next_best_actions: list[NextBestAction],
    action_traces: list[Any],
    buying_intent: BuyingIntent,
    stakeholder_map: list[Stakeholder],
    information_gaps: list[InformationGap],
    deal_score: DealScore,
    risks_and_objections: list[Risk],
) -> None:
    issues: list[NodeValidationIssue] = []
    traces_by_action_id = {trace.action_id: trace for trace in action_traces}
    issues.extend(
        validate_action_traces(
            action_traces=action_traces,
            next_best_actions=next_best_actions,
            risks_and_objections=risks_and_objections,
        )
    )
    for index, action in enumerate(next_best_actions):
        issues.extend(
            validate_related_gap_ids(
                field_prefix=f"next_best_actions.{index}.related_gap_ids",
                referenced_ids=action.related_gap_ids,
                information_gaps=information_gaps,
            )
        )
        trace = traces_by_action_id.get(action.action_id)
        if trace is None:
            continue
        issues.extend(
            validate_p0_action_grounding(
                action=action,
                action_trace=trace,
                information_gaps=information_gaps,
                risks_and_objections=risks_and_objections,
            )
        )
        issues.extend(
            validate_action_stage_compatibility(
                action=action,
                action_trace=trace,
                buying_intent=buying_intent,
                deal_score=deal_score,
                information_gaps=information_gaps,
                stakeholder_map=stakeholder_map,
            )
        )
        issues.extend(validate_action_quality(action))
    if issues:
        raise NodeBusinessRuleError(
            node_name=WorkflowNodeName.next_best_action,
            message="Next best action failed business validation.",
            issues=issues,
        )
