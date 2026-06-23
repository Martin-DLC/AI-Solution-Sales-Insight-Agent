from __future__ import annotations

import json
from typing import Any

from agent.workflow_c.contracts import NodeContract, NodeFailurePolicy
from agent.workflow_c.decision_validation import (
    validate_risk_evidence,
    validate_risk_traces,
)
from agent.workflow_c.failures import NodeBusinessRuleError, NodeJSONParseError
from agent.workflow_c.node_outputs import RiskNodeOutput
from agent.workflow_c.prompt_loader import render_risk_messages
from agent.workflow_c.state import NodeValidationIssue, SourceIndexResult, WorkflowNodeName
from schemas.common_models import SeverityLevel
from schemas.input_models import EvaluationCaseInput
from schemas.insight_models import BuyingIntent, InformationGap, Stakeholder
from schemas.decision_models import DealScore
from schemas.solution_models import AIOpportunity, Risk, SolutionRecommendation


class RiskNode:
    contract = NodeContract(
        name=WorkflowNodeName.risk,
        required_state_fields=(
            "validated_case",
            "source_index",
            "information_gaps",
            "buying_intent",
            "stakeholder_map",
            "ai_opportunities",
            "deal_score",
        ),
        produced_state_fields=("risks_and_objections", "risk_traces"),
        output_model=RiskNodeOutput,
        failure_policy=NodeFailurePolicy.require_human_review,
        prompt_version="risk_v1",
    )

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        case: EvaluationCaseInput = state["validated_case"]
        source_index: SourceIndexResult = state["source_index"]
        information_gaps: list[InformationGap] = state["information_gaps"]
        buying_intent: BuyingIntent = state["buying_intent"]
        stakeholder_map: list[Stakeholder] = state["stakeholder_map"]
        ai_opportunities: list[AIOpportunity] = state["ai_opportunities"]
        solution_recommendations: list[SolutionRecommendation] = (
            state.get("solution_recommendations") or []
        )
        deal_score: DealScore = state["deal_score"]
        messages = render_risk_messages(
            case.known_constraints,
            information_gaps,
            buying_intent,
            stakeholder_map,
            ai_opportunities,
            solution_recommendations,
            deal_score,
        )
        result = services.llm.complete_json_for_node(WorkflowNodeName.risk, messages)
        parsed = result.parsed_json
        if parsed is None:
            try:
                parsed = json.loads(result.content)
            except json.JSONDecodeError as exc:
                raise NodeJSONParseError(
                    message="Risk analysis returned invalid JSON.",
                    content_length=len(result.content),
                    position=exc.pos,
                ) from exc

        output = RiskNodeOutput.model_validate(parsed)
        _validate_risk_rules(
            output.risks_and_objections,
            output.risk_traces,
            information_gaps,
            ai_opportunities,
            source_index,
        )
        return {
            "risks_and_objections": output.risks_and_objections,
            "risk_traces": output.risk_traces,
        }


def _validate_risk_rules(
    risks_and_objections: list[Risk],
    risk_traces: list[Any],
    information_gaps: list[InformationGap],
    ai_opportunities: list[AIOpportunity],
    source_index: SourceIndexResult,
) -> None:
    issues: list[NodeValidationIssue] = []
    issues.extend(
        validate_risk_traces(
            risk_traces=risk_traces,
            risks_and_objections=risks_and_objections,
            information_gaps=information_gaps,
            ai_opportunities=ai_opportunities,
        )
    )
    issues.extend(
        validate_risk_evidence(
            risks_and_objections=risks_and_objections,
            source_index=source_index,
        )
    )
    for index, risk in enumerate(risks_and_objections):
        if risk.severity in {SeverityLevel.high, SeverityLevel.critical} and not risk.mitigation:
            issues.append(
                NodeValidationIssue(
                    location=f"risks_and_objections.{index}.mitigation",
                    error_type="business_rule",
                    message="High or critical risks must include mitigation.",
                    input_summary=risk.risk_id,
                )
            )
    if issues:
        raise NodeBusinessRuleError(
            node_name=WorkflowNodeName.risk,
            message="Risk analysis failed business validation.",
            issues=issues,
        )
