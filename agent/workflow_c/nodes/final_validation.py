from __future__ import annotations

from typing import Any

from agent.workflow_c.contracts import NodeContract, NodeFailurePolicy
from agent.workflow_c.final_validation import validate_report_draft
from agent.workflow_c.node_outputs import FinalValidationNodeOutput
from agent.workflow_c.state import WorkflowNodeName


class FinalValidationNode:
    contract = NodeContract(
        name=WorkflowNodeName.final_validation,
        required_state_fields=(
            "validated_case",
            "report_draft",
            "retrieved_solutions",
            "ai_opportunities",
            "deal_score",
            "information_gaps",
            "risks_and_objections",
            "risk_traces",
            "next_best_actions",
            "action_traces",
        ),
        produced_state_fields=("final_validation_result", "final_report"),
        output_model=FinalValidationNodeOutput,
        failure_policy=NodeFailurePolicy.require_human_review,
        prompt_version=None,
    )

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        report_draft = state["report_draft"]
        result = validate_report_draft(
            report_draft=report_draft,
            expected_case_id=state["validated_case"].case_id,
            retrieved_solutions=state["retrieved_solutions"],
            ai_opportunities=state["ai_opportunities"],
            solution_recommendations=state.get("solution_recommendations") or [],
            deal_score=state["deal_score"],
            information_gaps=state["information_gaps"],
            risks_and_objections=state["risks_and_objections"],
            next_best_actions=state["next_best_actions"],
            risk_traces=state["risk_traces"],
            action_traces=state["action_traces"],
        )
        final_report = report_draft.model_copy(deep=True) if result.passed else None
        return {
            "final_validation_result": result,
            "final_report": final_report,
        }
