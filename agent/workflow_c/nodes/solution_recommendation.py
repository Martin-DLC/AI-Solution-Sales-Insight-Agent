from __future__ import annotations

import json
from typing import Any

from agent.workflow_c.contracts import NodeContract, NodeFailurePolicy
from agent.workflow_c.failures import NodeBusinessRuleError, NodeJSONParseError
from agent.workflow_c.node_outputs import SolutionRecommendationNodeOutput
from agent.workflow_c.prompt_loader import render_solution_recommendation_messages
from agent.workflow_c.solution_validation import (
    build_solution_catalog,
    opportunity_allows_recommendation,
    validate_recommendation_in_retrieved_candidates,
    validate_solution_catalog,
    validate_solution_recommendation,
)
from agent.workflow_c.retrieval_models import SolutionRetrievalResult
from agent.workflow_c.state import NodeValidationIssue, SourceIndexResult, WorkflowNodeName
from schemas.input_models import EvaluationCaseInput
from schemas.insight_models import InformationGap
from schemas.solution_models import AIOpportunity, SolutionRecommendation


class SolutionRecommendationNode:
    contract = NodeContract(
        name=WorkflowNodeName.solution_recommendation,
        required_state_fields=(
            "validated_case",
            "source_index",
            "information_gaps",
            "ai_opportunities",
            "retrieved_solutions",
        ),
        produced_state_fields=("solution_recommendations",),
        output_model=SolutionRecommendationNodeOutput,
        failure_policy=NodeFailurePolicy.require_human_review,
        prompt_version="solution_recommendation_v1",
    )

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        case: EvaluationCaseInput = state["validated_case"]
        source_index: SourceIndexResult = state["source_index"]
        information_gaps: list[InformationGap] = state["information_gaps"]
        ai_opportunities: list[AIOpportunity] = state["ai_opportunities"]
        retrieved_solutions: SolutionRetrievalResult = state["retrieved_solutions"]
        solution_catalog = build_solution_catalog(case, source_index)
        messages = render_solution_recommendation_messages(
            ai_opportunities,
            information_gaps,
            case.known_constraints,
            retrieved_solutions,
        )
        result = services.llm.complete_json_for_node(
            WorkflowNodeName.solution_recommendation,
            messages,
        )
        parsed = result.parsed_json
        if parsed is None:
            try:
                parsed = json.loads(result.content)
            except json.JSONDecodeError as exc:
                raise NodeJSONParseError(
                    message="Solution recommendation analysis returned invalid JSON.",
                    content_length=len(result.content),
                    position=exc.pos,
                ) from exc

        output = SolutionRecommendationNodeOutput.model_validate(parsed)
        _validate_solution_recommendation_rules(
            output.solution_recommendations,
            case,
            solution_catalog,
            ai_opportunities,
            retrieved_solutions,
        )
        return {"solution_recommendations": output.solution_recommendations}


def _validate_solution_recommendation_rules(
    recommendations: list[SolutionRecommendation],
    case: EvaluationCaseInput,
    solution_catalog: dict[str, Any],
    ai_opportunities: list[AIOpportunity],
    retrieved_solutions: SolutionRetrievalResult,
) -> None:
    issues: list[NodeValidationIssue] = []
    issues.extend(validate_solution_catalog(case, solution_catalog))

    if recommendations and not any(
        opportunity_allows_recommendation(opportunity)
        for opportunity in ai_opportunities
    ):
        issues.append(
            NodeValidationIssue(
                location="solution_recommendations",
                error_type="business_rule",
                message=(
                    "Solution recommendations must be empty when no AI opportunity "
                    "is eligible for recommendation."
                ),
            )
        )

    for index, recommendation in enumerate(recommendations):
        issues.extend(
            validate_solution_recommendation(
                recommendation=recommendation,
                recommendation_index=index,
                solution_catalog=solution_catalog,
                ai_opportunities=ai_opportunities,
            )
        )
        issues.extend(
            validate_recommendation_in_retrieved_candidates(
                recommendation=recommendation,
                recommendation_index=index,
                retrieved_solutions=retrieved_solutions,
            )
        )

    if issues:
        raise NodeBusinessRuleError(
            node_name=WorkflowNodeName.solution_recommendation,
            message="Solution recommendation failed business validation.",
            issues=issues,
        )
