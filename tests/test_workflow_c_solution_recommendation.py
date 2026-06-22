from __future__ import annotations

import json

from agent.workflow_c.executor import execute_node
from agent.workflow_c.fake_llm import (
    FakeWorkflowLLMClient,
    default_ai_opportunity_response,
    default_information_gap_response,
    default_solution_recommendation_response,
)
from agent.workflow_c.nodes import SolutionRecommendationNode, SourceIndexingNode
from agent.workflow_c.services import WorkflowLLMResult, WorkflowServices
from agent.workflow_c.state import FailureCategory, WorkflowNodeName
from dataio.runtime_cases import load_runtime_cases
from llm.models import LLMMessage, LLMUsage
from schemas.common_models import OpportunitySuitability
from schemas.insight_models import InformationGap
from schemas.solution_models import AIOpportunity


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def source_index():
    return execute_node(
        SourceIndexingNode(),
        {"validated_case": dev_01_case()},
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )["source_index"]


def opportunities(payload: dict | None = None) -> list[AIOpportunity]:
    payload = payload or default_ai_opportunity_response()
    return [
        AIOpportunity.model_validate(item)
        for item in payload["ai_opportunities"]
    ]


def state_with_dependencies(ai_opportunities: list[AIOpportunity] | None = None) -> dict:
    return {
        "validated_case": dev_01_case(),
        "source_index": source_index(),
        "information_gaps": [
            InformationGap.model_validate(item)
            for item in default_information_gap_response()["information_gaps"]
        ],
        "ai_opportunities": ai_opportunities or opportunities(),
    }


def client_with_payload(payload: dict) -> FakeWorkflowLLMClient:
    return FakeWorkflowLLMClient(
        responses_by_node={WorkflowNodeName.solution_recommendation: payload}
    )


def run_payload(payload: dict, state: dict | None = None):
    return execute_node(
        SolutionRecommendationNode(),
        state or state_with_dependencies(),
        WorkflowServices(llm=client_with_payload(payload)),
    )


class ContentOnlyClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def complete_json_for_node(
        self,
        node_name: WorkflowNodeName,
        messages: list[LLMMessage],
    ) -> WorkflowLLMResult:
        self.calls += 1
        return WorkflowLLMResult(
            content=json.dumps(self.payload, ensure_ascii=False),
            parsed_json=None,
            model="content-only",
            usage=LLMUsage(),
            latency_ms=1,
        )


def test_valid_recommendation_passes() -> None:
    patch = run_payload(default_solution_recommendation_response())

    assert patch["solution_recommendations"][0].solution_id == "AI客服知识问答方案"


def test_empty_recommendations_are_valid() -> None:
    patch = run_payload({"solution_recommendations": []})

    assert patch["solution_recommendations"] == []


def test_node_calls_llm_once() -> None:
    client = FakeWorkflowLLMClient.with_default_batch3a_responses()

    execute_node(
        SolutionRecommendationNode(),
        state_with_dependencies(),
        WorkflowServices(llm=client),
    )

    assert client.calls_for_node(WorkflowNodeName.solution_recommendation) == 1


def test_prompt_version_is_correct() -> None:
    patch = run_payload(default_solution_recommendation_response())

    assert patch["node_records"][0].prompt_version == "solution_recommendation_v1"


def test_content_json_without_parsed_json_passes() -> None:
    client = ContentOnlyClient(default_solution_recommendation_response())

    patch = execute_node(
        SolutionRecommendationNode(),
        state_with_dependencies(),
        WorkflowServices(llm=client),
    )

    assert patch["solution_recommendations"][0].recommendation_id == "REC-01"
    assert client.calls == 1


def test_invalid_json_fails() -> None:
    client = FakeWorkflowLLMClient.with_default_batch3a_responses(
        invalid_json_nodes={"solution_recommendation"}
    )

    patch = execute_node(
        SolutionRecommendationNode(),
        state_with_dependencies(),
        WorkflowServices(llm=client),
    )

    assert patch["failures"][0].failure_category is FailureCategory.json_parse


def test_schema_missing_field_fails() -> None:
    payload = default_solution_recommendation_response()
    del payload["solution_recommendations"][0]["solution_name"]

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_solution_id_outside_library_fails() -> None:
    payload = default_solution_recommendation_response()
    payload["solution_recommendations"][0]["solution_id"] = "outside-library-solution"

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_related_opportunity_id_not_found_fails() -> None:
    payload = default_solution_recommendation_response()
    payload["solution_recommendations"][0]["related_opportunity_ids"] = ["OPP-NOPE"]

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_no_knowledge_references_fails() -> None:
    payload = default_solution_recommendation_response()
    payload["solution_recommendations"][0]["knowledge_references"] = []

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_knowledge_reference_not_solution_library_fails() -> None:
    payload = default_solution_recommendation_response()
    payload["solution_recommendations"][0]["knowledge_references"] = [
        {
            "source_id": "MTG-01",
            "source_type": "meeting_transcript",
            "evidence_summary": "会议不能代替方案库引用。",
        }
    ]

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_knowledge_reference_source_id_not_found_fails() -> None:
    payload = default_solution_recommendation_response()
    payload["solution_recommendations"][0]["knowledge_references"][0]["source_id"] = "SOLUTION-99"

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_knowledge_reference_points_to_other_solution_fails() -> None:
    payload = default_solution_recommendation_response()
    payload["solution_recommendations"][0]["solution_id"] = "RAG企业知识库方案"

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_not_suitable_for_ai_opportunity_cannot_be_recommended() -> None:
    opp = opportunities()[0].model_copy(
        update={
            "suitability": OpportunitySuitability.not_suitable_for_ai,
            "major_limitations": ["当前问题不适合AI处理。"],
        }
    )

    patch = run_payload(default_solution_recommendation_response(), state_with_dependencies([opp]))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_insufficient_information_opportunity_cannot_be_recommended() -> None:
    opp = opportunities()[0].model_copy(
        update={
            "suitability": OpportunitySuitability.insufficient_information,
            "major_limitations": ["信息不足，不能推荐方案。"],
        }
    )

    patch = run_payload(default_solution_recommendation_response(), state_with_dependencies([opp]))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_eligible_opportunity_recommendation_passes() -> None:
    patch = run_payload(default_solution_recommendation_response())

    assert patch["solution_recommendations"][0].related_opportunity_ids == ["OPP-01"]


def test_duplicate_recommendation_id_fails() -> None:
    payload = default_solution_recommendation_response()
    clone = payload["solution_recommendations"][0].copy()
    clone["solution_id"] = "RAG企业知识库方案"
    clone["solution_name"] = "RAG企业知识库方案"
    clone["knowledge_references"] = [
        {
            "source_id": "SOLUTION-02",
            "source_type": "solution_library",
            "evidence_summary": "方案库中列出了RAG企业知识库方案。",
        }
    ]
    payload["solution_recommendations"].append(clone)

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_duplicate_solution_id_fails() -> None:
    payload = default_solution_recommendation_response()
    clone = payload["solution_recommendations"][0].copy()
    clone["recommendation_id"] = "REC-02"
    payload["solution_recommendations"].append(clone)

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_node_does_not_auto_modify_solution_id() -> None:
    payload = default_solution_recommendation_response()
    payload["solution_recommendations"][0]["solution_id"] = "AI客服知识问答"

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_node_does_not_do_fuzzy_matching() -> None:
    payload = default_solution_recommendation_response()
    payload["solution_recommendations"][0]["solution_id"] = "AI客服知识问答方案-扩展版"

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_failure_does_not_write_solution_recommendations() -> None:
    payload = default_solution_recommendation_response()
    payload["solution_recommendations"][0]["solution_id"] = "outside-library-solution"

    patch = run_payload(payload)

    assert "solution_recommendations" not in patch


def test_does_not_generate_deal_score() -> None:
    patch = run_payload(default_solution_recommendation_response())

    assert "deal_score" not in patch


def test_does_not_read_reference_pack() -> None:
    patch = run_payload(default_solution_recommendation_response())
    dumped = str([item.model_dump(mode="json") for item in patch["solution_recommendations"]])

    assert "Reference Pack" not in dumped
    assert "hard_failure_traps" not in dumped
    assert "solution_blacklist" not in dumped
