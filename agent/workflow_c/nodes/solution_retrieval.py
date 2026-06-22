from __future__ import annotations

from typing import Any

from agent.workflow_c.contracts import NodeContract, NodeFailurePolicy
from agent.workflow_c.node_outputs import SolutionRetrievalNodeOutput
from agent.workflow_c.solution_retrieval import retrieve_solution_candidates
from agent.workflow_c.state import SourceIndexResult, WorkflowNodeName
from schemas.input_models import EvaluationCaseInput
from schemas.insight_models import BusinessImpact, UnderlyingPain
from schemas.solution_models import AIOpportunity


class SolutionRetrievalNode:
    contract = NodeContract(
        name=WorkflowNodeName.solution_retrieval,
        required_state_fields=(
            "validated_case",
            "source_index",
            "underlying_pains",
            "business_impacts",
            "ai_opportunities",
        ),
        produced_state_fields=("retrieved_solutions",),
        output_model=SolutionRetrievalNodeOutput,
        failure_policy=NodeFailurePolicy.require_human_review,
        prompt_version=None,
    )

    def __init__(self, *, top_k: int = 5, min_score: float = 0.05) -> None:
        self.top_k = top_k
        self.min_score = min_score

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        case: EvaluationCaseInput = state["validated_case"]
        source_index: SourceIndexResult = state["source_index"]
        underlying_pains: list[UnderlyingPain] = state["underlying_pains"]
        business_impacts: list[BusinessImpact] = state["business_impacts"]
        ai_opportunities: list[AIOpportunity] = state["ai_opportunities"]
        return {
            "retrieved_solutions": retrieve_solution_candidates(
                case=case,
                source_index=source_index,
                ai_opportunities=ai_opportunities,
                underlying_pains=underlying_pains,
                business_impacts=business_impacts,
                top_k=self.top_k,
                min_score=self.min_score,
            )
        }
