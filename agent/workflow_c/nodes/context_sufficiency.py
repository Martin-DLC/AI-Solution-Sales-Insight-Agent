from __future__ import annotations

from typing import Any

from agent.workflow_c.contracts import ContextSufficiencyOutput, NodeContract, NodeFailurePolicy
from agent.workflow_c.state import (
    AnalysisMode,
    ContextSufficiencyResult,
    FactExtractionResult,
    WorkflowNodeName,
)
from schemas import EvaluationCaseInput
from schemas.common_models import ContextQuality


ALL_CATEGORIES = {
    "business_goal",
    "current_process",
    "pain_or_problem",
    "stakeholders",
    "budget",
    "timeline",
    "data",
    "systems",
    "security",
    "success_metrics",
}
CORE_CATEGORIES = {"business_goal", "pain_or_problem", "stakeholders"}


class ContextSufficiencyNode:
    contract = NodeContract(
        name=WorkflowNodeName.context_sufficiency,
        required_state_fields=("validated_case", "fact_extraction"),
        produced_state_fields=("context_sufficiency",),
        output_model=ContextSufficiencyOutput,
        failure_policy=NodeFailurePolicy.require_human_review,
        prompt_version=None,
    )

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        case: EvaluationCaseInput = state["validated_case"]
        fact_result: FactExtractionResult = state["fact_extraction"]
        available = {fact.category for fact in fact_result.facts}
        if case.customer_profile.publicly_stated_goals:
            available.add("business_goal")
        if case.customer_profile.current_systems:
            available.add("systems")
        if case.meeting.participants:
            available.add("stakeholders")
        if case.known_constraints:
            available.add("security")
        if case.meeting.transcript:
            available.add("current_process")
        missing = sorted(ALL_CATEGORIES - available)
        core_available = CORE_CATEGORIES & available
        blocking = sorted(CORE_CATEGORIES - available)
        if len(core_available) == 3 and len(available) >= 6:
            quality = ContextQuality.sufficient
            mode = AnalysisMode.full_analysis
        elif len(core_available) >= 2 or len(available) >= 4:
            quality = ContextQuality.partially_sufficient
            mode = AnalysisMode.partial_analysis
        else:
            quality = ContextQuality.insufficient
            mode = AnalysisMode.clarification_only
        return {
            "context_sufficiency": ContextSufficiencyResult(
                context_quality=quality,
                analysis_mode=mode,
                available_categories=sorted(available),
                missing_categories=missing,
                blocking_gaps=blocking,
                reasoning_summary="根据事实类别、客户画像和会议参与信息判断上下文充分性。",
            )
        }
