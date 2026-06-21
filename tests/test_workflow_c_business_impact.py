from __future__ import annotations

from agent.workflow_c.executor import execute_node
from agent.workflow_c.fake_llm import (
    FakeWorkflowLLMClient,
    default_business_impact_response,
    default_explicit_need_response,
    default_fact_response,
    default_underlying_pain_response,
)
from agent.workflow_c.nodes import BusinessImpactNode, SourceIndexingNode
from agent.workflow_c.services import WorkflowServices
from agent.workflow_c.state import FactExtractionResult, FailureCategory, WorkflowNodeName
from dataio.runtime_cases import load_runtime_cases
from schemas.common_models import ClaimType, EvidenceSourceType
from schemas.insight_models import ExplicitNeed, UnderlyingPain


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
        "explicit_needs": [
            ExplicitNeed.model_validate(item)
            for item in default_explicit_need_response()["explicit_needs"]
        ],
        "underlying_pains": [
            UnderlyingPain.model_validate(item)
            for item in default_underlying_pain_response()["underlying_pains"]
        ],
    }


def client_with_payload(payload: dict) -> FakeWorkflowLLMClient:
    return FakeWorkflowLLMClient(
        responses_by_node={WorkflowNodeName.business_impact: payload},
    )


def run_payload(payload: dict):
    return execute_node(
        BusinessImpactNode(),
        state_with_dependencies(),
        WorkflowServices(llm=client_with_payload(payload)),
    )


def test_valid_unquantified_impact_passes() -> None:
    patch = execute_node(
        BusinessImpactNode(),
        state_with_dependencies(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch1b_responses()),
    )

    assert patch["business_impacts"][0].impact_id == "IMPACT-01"


def test_node_calls_llm_once() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1b_responses()

    execute_node(BusinessImpactNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert client.calls_for_node(WorkflowNodeName.business_impact) == 1


def test_prompt_version_is_correct() -> None:
    patch = execute_node(
        BusinessImpactNode(),
        state_with_dependencies(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch1b_responses()),
    )

    assert patch["node_records"][0].prompt_version == "business_impact_v1"


def test_invalid_json_fails() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1b_responses(
        invalid_json_nodes={"business_impact"}
    )

    patch = execute_node(BusinessImpactNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert patch["failures"][0].failure_category is FailureCategory.json_parse


def test_missing_field_fails_schema_validation() -> None:
    payload = default_business_impact_response()
    del payload["business_impacts"][0]["description"]

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_quantified_without_values_fails() -> None:
    payload = default_business_impact_response()
    payload["business_impacts"][0]["quantified"] = True
    payload["business_impacts"][0]["measurement_needed"] = None

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_unquantified_without_measurement_needed_fails() -> None:
    payload = default_business_impact_response()
    payload["business_impacts"][0]["measurement_needed"] = None

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_claim_type_unknown_fails() -> None:
    payload = default_business_impact_response()
    payload["business_impacts"][0]["claim_type"] = ClaimType.unknown.value

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_without_evidence_fails() -> None:
    payload = default_business_impact_response()
    payload["business_impacts"][0]["evidence"] = []

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_unknown_source_id_fails() -> None:
    payload = default_business_impact_response()
    payload["business_impacts"][0]["evidence"][0]["source_id"] = "BAD-01"

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_source_type_mismatch_fails() -> None:
    payload = default_business_impact_response()
    payload["business_impacts"][0]["evidence"][0]["source_type"] = EvidenceSourceType.customer_profile.value

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_solution_library_evidence_fails() -> None:
    payload = default_business_impact_response()
    payload["business_impacts"][0]["evidence"] = [
        {
            "source_id": "SOLUTION-01",
            "source_type": EvidenceSourceType.solution_library.value,
            "evidence_summary": "方案库不能作为影响证据。",
        }
    ]

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_reference_case_evidence_fails() -> None:
    payload = default_business_impact_response()
    payload["business_impacts"][0]["evidence"][0]["source_type"] = EvidenceSourceType.reference_case.value

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_unverified_sales_note_alone_fails() -> None:
    payload = default_business_impact_response()
    payload["business_impacts"][0]["evidence"] = [
        {
            "source_id": "NOTE-01",
            "source_type": EvidenceSourceType.salesperson_note.value,
            "evidence_summary": "销售备注不能单独支持影响。",
        }
    ]

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_meeting_evidence_passes() -> None:
    patch = run_payload(default_business_impact_response())

    assert patch["business_impacts"][0].evidence[0].source_id == "MTG-01"


def test_known_constraint_evidence_passes() -> None:
    payload = default_business_impact_response()
    payload["business_impacts"][0]["evidence"] = [
        {
            "source_id": "CONSTRAINT-01",
            "source_type": EvidenceSourceType.known_constraint.value,
            "evidence_summary": "已知限制可作为已验证支持。",
        }
    ]

    patch = run_payload(payload)

    assert patch["business_impacts"][0].evidence[0].source_id == "CONSTRAINT-01"


def test_duplicate_impact_id_fails() -> None:
    payload = default_business_impact_response()
    payload["business_impacts"].append(payload["business_impacts"][0].copy())

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_duplicate_description_fails() -> None:
    payload = default_business_impact_response()
    clone = payload["business_impacts"][0].copy()
    clone["impact_id"] = "IMPACT-02"
    payload["business_impacts"].append(clone)

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_does_not_auto_generate_roi_field_or_number() -> None:
    patch = run_payload(default_business_impact_response())
    dumped = patch["business_impacts"][0].model_dump(mode="json")

    assert "roi" not in dumped
    assert dumped["quantified"] is False
    assert dumped["current_value"] is None
    assert dumped["target_value"] is None


def test_failure_does_not_write_business_impacts() -> None:
    payload = default_business_impact_response()
    payload["business_impacts"][0]["evidence"] = []

    patch = run_payload(payload)

    assert "business_impacts" not in patch
