from __future__ import annotations

from agent.workflow_c.executor import execute_node
from agent.workflow_c.fake_llm import (
    FakeWorkflowLLMClient,
    default_ai_opportunity_response,
    default_business_impact_response,
    default_underlying_pain_response,
)
from agent.workflow_c.nodes import SolutionRetrievalNode, SourceIndexingNode
from agent.workflow_c.services import WorkflowServices
from agent.workflow_c.state import WorkflowNodeName
from dataio.runtime_cases import load_runtime_cases
from schemas.common_models import OpportunitySuitability
from schemas.insight_models import BusinessImpact, UnderlyingPain
from schemas.solution_models import AIOpportunity


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def source_index():
    return execute_node(
        SourceIndexingNode(),
        {"validated_case": dev_01_case()},
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )["source_index"]


def state(ai_opportunities: list[AIOpportunity] | None = None) -> dict:
    return {
        "validated_case": dev_01_case(),
        "source_index": source_index(),
        "underlying_pains": [
            UnderlyingPain.model_validate(item)
            for item in default_underlying_pain_response()["underlying_pains"]
        ],
        "business_impacts": [
            BusinessImpact.model_validate(item)
            for item in default_business_impact_response()["business_impacts"]
        ],
        "ai_opportunities": ai_opportunities
        or [
            AIOpportunity.model_validate(item)
            for item in default_ai_opportunity_response()["ai_opportunities"]
        ],
    }


def test_solution_retrieval_node_runs_without_llm_call() -> None:
    client = FakeWorkflowLLMClient.with_default_batch3a_responses()
    patch = execute_node(
        SolutionRetrievalNode(),
        state(),
        WorkflowServices(llm=client),
    )

    assert patch["retrieved_solutions"].candidate_count >= 1
    assert client.total_calls == 0


def test_solution_retrieval_node_contract() -> None:
    node = SolutionRetrievalNode()

    assert node.contract.name is WorkflowNodeName.solution_retrieval
    assert node.contract.prompt_version is None
    assert node.contract.produced_state_fields == ("retrieved_solutions",)


def test_solution_retrieval_node_empty_candidates_for_noneligible_opportunity() -> None:
    blocked = [
        AIOpportunity.model_validate(default_ai_opportunity_response()["ai_opportunities"][0]).model_copy(
            update={
                "suitability": OpportunitySuitability.not_suitable_for_ai,
                "major_limitations": ["当前问题不适合AI处理。"],
            }
        )
    ]

    patch = execute_node(
        SolutionRetrievalNode(),
        state(blocked),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch3a_responses()),
    )

    assert patch["retrieved_solutions"].candidate_count == 0
