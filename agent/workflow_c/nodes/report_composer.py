from __future__ import annotations

from typing import Any

from agent.workflow_c.contracts import NodeContract, NodeFailurePolicy
from agent.workflow_c.node_outputs import ReportComposerNodeOutput
from agent.workflow_c.report_composer import (
    build_analysis_id,
    compose_sales_insight_report,
    utc_now,
)
from agent.workflow_c.state import WorkflowNodeName


class ReportComposerNode:
    contract = NodeContract(
        name=WorkflowNodeName.report_composer,
        required_state_fields=(
            "run_id",
            "validated_case",
            "fact_extraction",
            "context_sufficiency",
            "explicit_needs",
            "underlying_pains",
            "business_impacts",
            "buying_intent",
            "stakeholder_map",
            "information_gaps",
            "ai_opportunities",
            "deal_score",
            "risks_and_objections",
            "next_best_actions",
        ),
        produced_state_fields=("report_draft",),
        output_model=ReportComposerNodeOutput,
        failure_policy=NodeFailurePolicy.require_human_review,
        prompt_version=None,
    )

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        case = state["validated_case"]
        analysis_id = build_analysis_id(run_id=state["run_id"], case_id=case.case_id)
        generated_at = utc_now()
        report = compose_sales_insight_report(
            analysis_id=analysis_id,
            generated_at=generated_at,
            validated_case=case,
            fact_extraction=state["fact_extraction"],
            context_sufficiency=state["context_sufficiency"],
            explicit_needs=state["explicit_needs"],
            underlying_pains=state["underlying_pains"],
            business_impacts=state["business_impacts"],
            buying_intent=state["buying_intent"],
            stakeholder_map=state["stakeholder_map"],
            information_gaps=state["information_gaps"],
            ai_opportunities=state["ai_opportunities"],
            solution_recommendations=state.get("solution_recommendations") or [],
            deal_score=state["deal_score"],
            risks_and_objections=state["risks_and_objections"],
            next_best_actions=state["next_best_actions"],
        )
        return {"report_draft": report}
