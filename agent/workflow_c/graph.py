from __future__ import annotations

import uuid
from typing import Any, Callable

from agent.workflow_c.executor import execute_node
from agent.workflow_c.nodes import (
    AIOpportunityNode,
    BusinessImpactNode,
    BuyingIntentNode,
    ContextSufficiencyNode,
    ExplicitNeedNode,
    FactExtractionNode,
    HumanReviewGateNode,
    InformationGapNode,
    InputValidationNode,
    SolutionRetrievalNode,
    SolutionRecommendationNode,
    StakeholderNode,
    SourceIndexingNode,
    UnderlyingPainNode,
)
from agent.workflow_c.services import WorkflowServices
from agent.workflow_c.state import (
    ArchitectureCGraphState,
    ArchitectureCStateSnapshot,
    AnalysisMode,
    WorkflowStatus,
)
from schemas import EvaluationCaseInput


def create_initial_state(
    case: EvaluationCaseInput | dict,
) -> ArchitectureCGraphState:
    return {
        "run_id": f"C-{uuid.uuid4().hex}",
        "architecture_version": "C",
        "workflow_version": "c_skeleton_v1",
        "schema_version": "1.0",
        "workflow_status": WorkflowStatus.initialized,
        "current_node": None,
        "case_input": case,
        "node_records": [],
        "failures": [],
        "warnings": [],
        "human_review_required": True,
        "human_review_reasons": [],
    }


def build_architecture_c_skeleton(
    services: WorkflowServices,
):
    nodes = {
        "input_validation": InputValidationNode(),
        "source_indexing": SourceIndexingNode(),
        "fact_extraction": FactExtractionNode(),
        "context_sufficiency": ContextSufficiencyNode(),
        "explicit_need": ExplicitNeedNode(),
        "underlying_pain": UnderlyingPainNode(),
        "business_impact": BusinessImpactNode(),
        "buying_intent": BuyingIntentNode(),
        "stakeholder": StakeholderNode(),
        "information_gap": InformationGapNode(),
        "ai_opportunity": AIOpportunityNode(),
        "solution_retrieval": SolutionRetrievalNode(),
        "solution_recommendation": SolutionRecommendationNode(),
        "human_review_gate": HumanReviewGateNode(),
    }

    try:
        from langgraph.graph import END, START, StateGraph
    except Exception:
        return _FallbackGraph(services, nodes)

    builder = StateGraph(ArchitectureCGraphState)
    for name, node in nodes.items():
        builder.add_node(name, _node_fn(node, services))
    builder.add_edge(START, "input_validation")
    builder.add_conditional_edges(
        "input_validation",
        _route_after_input_validation,
        {"end": END, "source_indexing": "source_indexing"},
    )
    builder.add_conditional_edges(
        "source_indexing",
        _route_to_next_or_review("fact_extraction"),
        {"end": END, "human_review_gate": "human_review_gate", "fact_extraction": "fact_extraction"},
    )
    builder.add_conditional_edges(
        "fact_extraction",
        _route_to_next_or_review("context_sufficiency"),
        {
            "end": END,
            "human_review_gate": "human_review_gate",
            "context_sufficiency": "context_sufficiency",
        },
    )
    builder.add_conditional_edges(
        "context_sufficiency",
        _route_after_context_sufficiency,
        {
            "end": END,
            "human_review_gate": "human_review_gate",
            "information_gap": "information_gap",
            "explicit_need": "explicit_need",
        },
    )
    builder.add_conditional_edges(
        "explicit_need",
        _route_to_next_or_review("underlying_pain"),
        {"end": END, "human_review_gate": "human_review_gate", "underlying_pain": "underlying_pain"},
    )
    builder.add_conditional_edges(
        "underlying_pain",
        _route_to_next_or_review("business_impact"),
        {"end": END, "human_review_gate": "human_review_gate", "business_impact": "business_impact"},
    )
    builder.add_conditional_edges(
        "business_impact",
        _route_to_next_or_review("buying_intent"),
        {"end": END, "human_review_gate": "human_review_gate", "buying_intent": "buying_intent"},
    )
    builder.add_conditional_edges(
        "buying_intent",
        _route_to_next_or_review("stakeholder"),
        {"end": END, "human_review_gate": "human_review_gate", "stakeholder": "stakeholder"},
    )
    builder.add_conditional_edges(
        "stakeholder",
        _route_to_next_or_review("information_gap"),
        {"end": END, "human_review_gate": "human_review_gate", "information_gap": "information_gap"},
    )
    builder.add_conditional_edges(
        "information_gap",
        _route_after_information_gap,
        {
            "end": END,
            "human_review_gate": "human_review_gate",
            "ai_opportunity": "ai_opportunity",
        },
    )
    builder.add_conditional_edges(
        "ai_opportunity",
        _route_to_next_or_review("solution_retrieval"),
        {
            "end": END,
            "human_review_gate": "human_review_gate",
            "solution_retrieval": "solution_retrieval",
        },
    )
    builder.add_conditional_edges(
        "solution_retrieval",
        _route_after_solution_retrieval,
        {
            "end": END,
            "human_review_gate": "human_review_gate",
            "solution_recommendation": "solution_recommendation",
        },
    )
    builder.add_conditional_edges(
        "solution_recommendation",
        _route_to_next_or_review("human_review_gate"),
        {"end": END, "human_review_gate": "human_review_gate"},
    )
    builder.add_edge("human_review_gate", END)
    return builder.compile()


def run_architecture_c_skeleton(
    case: EvaluationCaseInput | dict,
    services: WorkflowServices,
) -> ArchitectureCStateSnapshot:
    graph = build_architecture_c_skeleton(services)
    final_state = graph.invoke(create_initial_state(case))
    return ArchitectureCStateSnapshot.model_validate(final_state)


def _node_fn(node: Any, services: WorkflowServices) -> Callable[[ArchitectureCGraphState], dict[str, Any]]:
    def run(state: ArchitectureCGraphState) -> dict[str, Any]:
        return execute_node(node, state, services)

    return run


def _route_after_input_validation(state: ArchitectureCGraphState) -> str:
    if state.get("workflow_status") is WorkflowStatus.failed:
        return "end"
    return "source_indexing"


def _route_to_next_or_review(next_node: str) -> Callable[[ArchitectureCGraphState], str]:
    def route(state: ArchitectureCGraphState) -> str:
        if state.get("workflow_status") is WorkflowStatus.awaiting_human_review:
            return "human_review_gate"
        if state.get("workflow_status") is WorkflowStatus.failed:
            return "end"
        return next_node

    return route


def _route_after_context_sufficiency(state: ArchitectureCGraphState) -> str:
    if state.get("workflow_status") is WorkflowStatus.awaiting_human_review:
        return "human_review_gate"
    if state.get("workflow_status") is WorkflowStatus.failed:
        return "end"
    context = state.get("context_sufficiency")
    if context is not None and context.analysis_mode is AnalysisMode.clarification_only:
        return "information_gap"
    return "explicit_need"


def _route_after_information_gap(state: ArchitectureCGraphState) -> str:
    if state.get("workflow_status") is WorkflowStatus.awaiting_human_review:
        return "human_review_gate"
    if state.get("workflow_status") is WorkflowStatus.failed:
        return "end"
    context = state.get("context_sufficiency")
    if context is not None and context.analysis_mode is AnalysisMode.clarification_only:
        return "human_review_gate"
    return "ai_opportunity"


def _route_after_solution_retrieval(state: ArchitectureCGraphState) -> str:
    if state.get("workflow_status") is WorkflowStatus.awaiting_human_review:
        return "human_review_gate"
    if state.get("workflow_status") is WorkflowStatus.failed:
        return "end"
    retrieved = state.get("retrieved_solutions")
    if retrieved is not None and retrieved.candidate_count == 0:
        return "human_review_gate"
    return "solution_recommendation"


class _FallbackGraph:
    def __init__(self, services: WorkflowServices, nodes: dict[str, Any]) -> None:
        self.services = services
        self.nodes = nodes

    def invoke(self, state: ArchitectureCGraphState) -> ArchitectureCGraphState:
        current = dict(state)
        for name in (
            "input_validation",
            "source_indexing",
            "fact_extraction",
            "context_sufficiency",
        ):
            current = self._run_or_stop(name, current)
            if current.get("workflow_status") is WorkflowStatus.failed:
                return current
            if current.get("workflow_status") is WorkflowStatus.awaiting_human_review:
                break
        else:
            context = current.get("context_sufficiency")
            if context is not None and context.analysis_mode is AnalysisMode.clarification_only:
                current = self._run_or_stop("information_gap", current)
            else:
                for name in (
                    "explicit_need",
                    "underlying_pain",
                    "business_impact",
                    "buying_intent",
                    "stakeholder",
                    "information_gap",
                    "ai_opportunity",
                    "solution_retrieval",
                    "solution_recommendation",
                ):
                    current = self._run_or_stop(name, current)
                    if current.get("workflow_status") in {
                        WorkflowStatus.failed,
                        WorkflowStatus.awaiting_human_review,
                    }:
                        break
                    if (
                        name == "information_gap"
                        and current.get("context_sufficiency") is not None
                        and current["context_sufficiency"].analysis_mode
                        is AnalysisMode.clarification_only
                    ):
                        break
                    if (
                        name == "solution_retrieval"
                        and current.get("retrieved_solutions") is not None
                        and current["retrieved_solutions"].candidate_count == 0
                    ):
                        break
        if current.get("workflow_status") is WorkflowStatus.failed:
            return current
        patch = execute_node(self.nodes["human_review_gate"], current, self.services)
        return _merge_state(current, patch)

    def _run_or_stop(
        self,
        name: str,
        current: ArchitectureCGraphState,
    ) -> ArchitectureCGraphState:
        patch = execute_node(self.nodes[name], current, self.services)
        return _merge_state(current, patch)


def _merge_state(state: dict[str, Any], patch: dict[str, Any]) -> ArchitectureCGraphState:
    merged = dict(state)
    for key, value in patch.items():
        if key in {"node_records", "failures", "warnings", "human_review_reasons"}:
            merged[key] = list(merged.get(key, [])) + list(value)
        else:
            merged[key] = value
    return merged
