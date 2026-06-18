from __future__ import annotations

import pytest

from agent.workflow_c.executor import execute_node
from agent.workflow_c.fake_llm import FakeWorkflowLLMClient, default_fact_response
from agent.workflow_c.nodes import FactExtractionNode, SourceIndexingNode
from agent.workflow_c.services import WorkflowServices
from agent.workflow_c.state import FailureCategory, WorkflowNodeName, WorkflowStatus
from dataio.runtime_cases import load_runtime_cases
from schemas.common_models import EvidenceSourceType


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def state_with_source_index():
    case = dev_01_case()
    source_patch = execute_node(
        SourceIndexingNode(),
        {"validated_case": case},
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_fact_response()),
    )
    return {"validated_case": case, "source_index": source_patch["source_index"]}


def client_with_fact_payload(payload: dict) -> FakeWorkflowLLMClient:
    return FakeWorkflowLLMClient(
        responses_by_node={WorkflowNodeName.fact_extraction: payload},
    )


def test_fact_extraction_node_calls_llm_once() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1a_responses()

    patch = execute_node(FactExtractionNode(), state_with_source_index(), WorkflowServices(llm=client))

    assert patch["fact_extraction"].facts
    assert client.calls_for_node(WorkflowNodeName.fact_extraction) == 1


def test_fact_extraction_uses_formal_prompt_version() -> None:
    patch = execute_node(
        FactExtractionNode(),
        state_with_source_index(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch1a_responses()),
    )

    assert patch["node_records"][0].prompt_version == "fact_extraction_v1"


def test_fact_extraction_invalid_json_fails_as_json_parse() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1a_responses(
        invalid_json_nodes={"fact_extraction"}
    )

    patch = execute_node(FactExtractionNode(), state_with_source_index(), WorkflowServices(llm=client))

    assert patch["failures"][0].failure_category is FailureCategory.json_parse


def test_fact_extraction_schema_error_fails_as_schema_validation() -> None:
    client = client_with_fact_payload({"fact_extraction": {"facts": []}})

    patch = execute_node(FactExtractionNode(), state_with_source_index(), WorkflowServices(llm=client))

    assert patch["workflow_status"] is WorkflowStatus.awaiting_human_review
    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_fact_evidence_unknown_source_fails_business_validation() -> None:
    fact = default_fact_response()
    fact["facts"][0]["evidence"][0]["source_id"] = "MISSING-01"
    client = client_with_fact_payload({"fact_extraction": fact})

    patch = execute_node(FactExtractionNode(), state_with_source_index(), WorkflowServices(llm=client))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation
    assert "source_id" in patch["failures"][0].validation_issues[0].location


def test_fact_evidence_source_type_mismatch_fails_business_validation() -> None:
    fact = default_fact_response()
    fact["facts"][0]["evidence"][0]["source_type"] = EvidenceSourceType.customer_profile.value
    client = client_with_fact_payload({"fact_extraction": fact})

    patch = execute_node(FactExtractionNode(), state_with_source_index(), WorkflowServices(llm=client))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation
    assert "source_type" in patch["failures"][0].validation_issues[0].location


def test_fact_supported_only_by_unverified_sales_note_fails() -> None:
    fact = default_fact_response()
    fact["facts"][0]["evidence"] = [
        {
            "source_id": "NOTE-01",
            "source_type": EvidenceSourceType.salesperson_note.value,
            "evidence_summary": "销售备注中提到该事项。",
        }
    ]
    client = client_with_fact_payload({"fact_extraction": fact})

    patch = execute_node(FactExtractionNode(), state_with_source_index(), WorkflowServices(llm=client))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation
    assert "verified" in patch["failures"][0].validation_issues[0].message


def test_fact_can_include_unverified_note_when_verified_source_exists() -> None:
    fact = default_fact_response()
    fact["facts"][0]["evidence"].append(
        {
            "source_id": "NOTE-01",
            "source_type": EvidenceSourceType.salesperson_note.value,
            "evidence_summary": "销售备注提供了补充线索。",
        }
    )
    client = client_with_fact_payload({"fact_extraction": fact})

    patch = execute_node(FactExtractionNode(), state_with_source_index(), WorkflowServices(llm=client))

    assert patch["fact_extraction"].facts[0].fact_id == "FACT-01"


def test_fact_node_does_not_import_reference_pack() -> None:
    import agent.workflow_c.nodes.fact_extraction as module

    assert "evaluation_references" not in module.__dict__
