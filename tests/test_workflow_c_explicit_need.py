from __future__ import annotations

from agent.workflow_c.executor import execute_node
from agent.workflow_c.fake_llm import (
    FakeWorkflowLLMClient,
    default_explicit_need_response,
    default_fact_response,
)
from agent.workflow_c.nodes import ExplicitNeedNode, SourceIndexingNode
from agent.workflow_c.services import WorkflowServices
from agent.workflow_c.state import FactExtractionResult, FailureCategory, WorkflowNodeName
from dataio.runtime_cases import load_runtime_cases
from schemas.common_models import ClaimType, EvidenceSourceType


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def state_with_dependencies():
    case = dev_01_case()
    source_patch = execute_node(
        SourceIndexingNode(),
        {"validated_case": case},
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )
    return {
        "validated_case": case,
        "source_index": source_patch["source_index"],
        "fact_extraction": FactExtractionResult.model_validate(default_fact_response()),
    }


def client_with_needs(payload: dict) -> FakeWorkflowLLMClient:
    return FakeWorkflowLLMClient(
        responses_by_node={WorkflowNodeName.explicit_need: payload},
    )


def test_explicit_need_node_calls_llm_once() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1a_responses()

    patch = execute_node(ExplicitNeedNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert patch["explicit_needs"][0].need_id == "NEED-01"
    assert client.calls_for_node(WorkflowNodeName.explicit_need) == 1


def test_explicit_need_uses_formal_prompt_version() -> None:
    patch = execute_node(
        ExplicitNeedNode(),
        state_with_dependencies(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch1a_responses()),
    )

    assert patch["node_records"][0].prompt_version == "explicit_need_v1"


def test_explicit_need_invalid_json_fails_as_json_parse() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1a_responses(
        invalid_json_nodes={"explicit_need"}
    )

    patch = execute_node(ExplicitNeedNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert patch["failures"][0].failure_category is FailureCategory.json_parse


def test_explicit_need_without_needs_fails_schema_validation() -> None:
    client = client_with_needs({"explicit_needs": []})

    patch = execute_node(ExplicitNeedNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_explicit_need_claim_type_must_be_fact() -> None:
    payload = default_explicit_need_response()
    payload["explicit_needs"][0]["claim_type"] = ClaimType.inference.value
    client = client_with_needs(payload)

    patch = execute_node(ExplicitNeedNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_explicit_need_solution_library_evidence_fails() -> None:
    payload = default_explicit_need_response()
    payload["explicit_needs"][0]["evidence"] = [
        {
            "source_id": "SOLUTION-01",
            "source_type": EvidenceSourceType.solution_library.value,
            "evidence_summary": "方案库不能证明客户明确表达需求。",
        }
    ]
    client = client_with_needs(payload)

    patch = execute_node(ExplicitNeedNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation
    assert "Solution library" in patch["failures"][0].validation_issues[0].message


def test_explicit_need_known_constraint_alone_fails() -> None:
    payload = default_explicit_need_response()
    payload["explicit_needs"][0]["evidence"] = [
        {
            "source_id": "CONSTRAINT-01",
            "source_type": EvidenceSourceType.known_constraint.value,
            "evidence_summary": "已知限制不能单独证明显性需求。",
        }
    ]
    client = client_with_needs(payload)

    patch = execute_node(ExplicitNeedNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation
    assert "verified customer" in patch["failures"][0].validation_issues[0].message


def test_explicit_need_unverified_note_alone_fails() -> None:
    payload = default_explicit_need_response()
    payload["explicit_needs"][0]["evidence"] = [
        {
            "source_id": "NOTE-01",
            "source_type": EvidenceSourceType.salesperson_note.value,
            "evidence_summary": "销售备注不能单独证明显性需求。",
        }
    ]
    client = client_with_needs(payload)

    patch = execute_node(ExplicitNeedNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation
    assert "verified customer" in patch["failures"][0].validation_issues[0].message


def test_explicit_need_duplicate_id_fails() -> None:
    payload = default_explicit_need_response()
    payload["explicit_needs"].append(payload["explicit_needs"][0].copy())
    client = client_with_needs(payload)

    patch = execute_node(ExplicitNeedNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_explicit_need_does_not_auto_create_underlying_pain() -> None:
    patch = execute_node(
        ExplicitNeedNode(),
        state_with_dependencies(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch1a_responses()),
    )

    assert "underlying_pains" not in patch


def test_explicit_need_custom_payload_keeps_node_validation_responsible() -> None:
    payload = default_explicit_need_response()
    payload["explicit_needs"][0]["evidence"] = [
        {
            "source_id": "NOTE-01",
            "source_type": EvidenceSourceType.salesperson_note.value,
            "evidence_summary": "销售备注不能单独证明显性需求。",
        }
    ]
    client = FakeWorkflowLLMClient.with_default_batch1a_responses(
        custom_payloads={"explicit_need": payload}
    )

    patch = execute_node(ExplicitNeedNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation
    assert "explicit_needs" not in patch
