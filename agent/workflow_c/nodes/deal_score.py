from __future__ import annotations

from typing import Any

from agent.workflow_c.contracts import NodeContract, NodeFailurePolicy
from agent.workflow_c.deal_scoring import calculate_deal_score
from agent.workflow_c.node_outputs import DealScoreNodeOutput
from agent.workflow_c.retrieval_models import SolutionRetrievalResult
from agent.workflow_c.state import (
    ContextSufficiencyResult,
    FactExtractionResult,
    SourceIndexResult,
    WorkflowNodeName,
)
from schemas.insight_models import (
    BusinessImpact,
    BuyingIntent,
    ExplicitNeed,
    InformationGap,
    Stakeholder,
    UnderlyingPain,
)
from schemas.solution_models import AIOpportunity, SolutionRecommendation


class DealScoreNode:
    contract = NodeContract(
        name=WorkflowNodeName.deal_score,
        required_state_fields=(
            "source_index",
            "context_sufficiency",
            "fact_extraction",
            "explicit_needs",
            "underlying_pains",
            "business_impacts",
            "buying_intent",
            "stakeholder_map",
            "information_gaps",
            "ai_opportunities",
            "retrieved_solutions",
        ),
        produced_state_fields=("deal_score",),
        output_model=DealScoreNodeOutput,
        failure_policy=NodeFailurePolicy.require_human_review,
        prompt_version=None,
    )

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        return {
            "deal_score": calculate_deal_score(
                source_index=state["source_index"],
                context_sufficiency=state["context_sufficiency"],
                fact_extraction=state["fact_extraction"],
                explicit_needs=state["explicit_needs"],
                underlying_pains=state["underlying_pains"],
                business_impacts=state["business_impacts"],
                buying_intent=state["buying_intent"],
                stakeholder_map=state["stakeholder_map"],
                information_gaps=state["information_gaps"],
                ai_opportunities=state["ai_opportunities"],
                retrieved_solutions=state["retrieved_solutions"],
                solution_recommendations=state.get("solution_recommendations") or [],
            )
        }
