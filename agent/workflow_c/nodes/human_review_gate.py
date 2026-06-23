from __future__ import annotations

from typing import Any

from agent.workflow_c.contracts import HumanReviewGateOutput, NodeContract, NodeFailurePolicy
from agent.workflow_c.state import (
    HumanReviewDecision,
    HumanReviewStatus,
    WorkflowFailure,
    WorkflowNodeName,
    WorkflowStatus,
)


class HumanReviewGateNode:
    contract = NodeContract(
        name=WorkflowNodeName.human_review_gate,
        required_state_fields=("case_input",),
        produced_state_fields=(
            "human_review_decision",
            "human_review_required",
            "human_review_reasons",
            "workflow_status",
        ),
        output_model=HumanReviewGateOutput,
        failure_policy=NodeFailurePolicy.require_human_review,
        prompt_version=None,
    )

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        reasons = ["Architecture C MVP requires human review."]
        final_validation_result = state.get("final_validation_result")
        if final_validation_result is not None:
            if final_validation_result.passed:
                reasons.append("Final validation passed; business approval is still required.")
            else:
                reasons.append(
                    "Final validation found "
                    f"{final_validation_result.blocking_issue_count} blocking issue(s); "
                    "review the draft and validation result."
                )
        for failure in state.get("failures", []):
            if isinstance(failure, WorkflowFailure):
                reasons.append(failure.message)
        decision = HumanReviewDecision(
            required=True,
            status=HumanReviewStatus.pending,
            reasons=reasons,
            reviewable_artifacts=["workflow_state_snapshot"],
            blocked_actions=[
                "发送客户邮件",
                "更新CRM",
                "发送报价",
                "对外作出实施承诺",
            ],
        )
        return {
            "human_review_decision": decision,
            "human_review_required": True,
            "human_review_reasons": reasons,
            "workflow_status": WorkflowStatus.awaiting_human_review,
        }
