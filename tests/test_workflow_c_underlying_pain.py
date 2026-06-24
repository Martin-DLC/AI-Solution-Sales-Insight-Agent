from __future__ import annotations

import json

from agent.workflow_c.executor import execute_node
from agent.workflow_c.fake_llm import (
    FakeWorkflowLLMClient,
    default_explicit_need_response,
    default_fact_response,
    default_underlying_pain_response,
)
from agent.workflow_c.nodes import SourceIndexingNode, UnderlyingPainNode
from agent.workflow_c.services import WorkflowLLMResult, WorkflowServices
from agent.workflow_c.state import FactExtractionResult, FailureCategory, WorkflowNodeName
from dataio.runtime_cases import load_runtime_cases
from llm.models import LLMMessage, LLMUsage
from schemas.common_models import ClaimType, EvidenceSourceType
from schemas.insight_models import ExplicitNeed


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
    }


def client_with_payload(payload: dict) -> FakeWorkflowLLMClient:
    return FakeWorkflowLLMClient(
        responses_by_node={WorkflowNodeName.underlying_pain: payload},
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


def test_valid_response_passes() -> None:
    patch = execute_node(
        UnderlyingPainNode(),
        state_with_dependencies(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch1b_responses()),
    )

    assert patch["underlying_pains"][0].pain_id == "PAIN-01"


def test_node_calls_llm_once() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1b_responses()

    execute_node(UnderlyingPainNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert client.calls_for_node(WorkflowNodeName.underlying_pain) == 1


def test_prompt_version_is_correct() -> None:
    patch = execute_node(
        UnderlyingPainNode(),
        state_with_dependencies(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch1b_responses()),
    )

    assert patch["node_records"][0].prompt_version == "underlying_pain_v2"


def test_content_json_without_parsed_json_passes() -> None:
    client = ContentOnlyClient(default_underlying_pain_response())

    patch = execute_node(UnderlyingPainNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert patch["underlying_pains"][0].pain_id == "PAIN-01"
    assert client.calls == 1


def test_invalid_json_fails() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1b_responses(
        invalid_json_nodes={"underlying_pain"}
    )

    patch = execute_node(UnderlyingPainNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert patch["failures"][0].failure_category is FailureCategory.json_parse


def test_missing_field_fails_schema_validation() -> None:
    payload = default_underlying_pain_response()
    del payload["underlying_pains"][0]["description"]

    patch = execute_node(
        UnderlyingPainNode(),
        state_with_dependencies(),
        WorkflowServices(llm=client_with_payload(payload)),
    )

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_claim_type_fact_fails() -> None:
    payload = default_underlying_pain_response()
    payload["underlying_pains"][0]["claim_type"] = ClaimType.fact.value

    patch = execute_node(UnderlyingPainNode(), state_with_dependencies(), WorkflowServices(llm=client_with_payload(payload)))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_claim_type_unknown_fails() -> None:
    payload = default_underlying_pain_response()
    payload["underlying_pains"][0]["claim_type"] = ClaimType.unknown.value

    patch = execute_node(UnderlyingPainNode(), state_with_dependencies(), WorkflowServices(llm=client_with_payload(payload)))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_without_evidence_fails() -> None:
    payload = default_underlying_pain_response()
    payload["underlying_pains"][0]["evidence"] = []

    patch = execute_node(UnderlyingPainNode(), state_with_dependencies(), WorkflowServices(llm=client_with_payload(payload)))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_unknown_source_id_fails() -> None:
    payload = default_underlying_pain_response()
    payload["underlying_pains"][0]["evidence"][0]["source_id"] = "BAD-01"

    patch = execute_node(UnderlyingPainNode(), state_with_dependencies(), WorkflowServices(llm=client_with_payload(payload)))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_source_type_mismatch_fails() -> None:
    payload = default_underlying_pain_response()
    payload["underlying_pains"][0]["evidence"][0]["source_type"] = EvidenceSourceType.customer_profile.value

    patch = execute_node(UnderlyingPainNode(), state_with_dependencies(), WorkflowServices(llm=client_with_payload(payload)))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_solution_library_evidence_fails() -> None:
    payload = default_underlying_pain_response()
    payload["underlying_pains"][0]["evidence"] = [
        {
            "source_id": "SOLUTION-01",
            "source_type": EvidenceSourceType.solution_library.value,
            "evidence_summary": "方案库不能作为痛点证据。",
        }
    ]

    patch = execute_node(UnderlyingPainNode(), state_with_dependencies(), WorkflowServices(llm=client_with_payload(payload)))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_reference_case_evidence_fails() -> None:
    payload = default_underlying_pain_response()
    payload["underlying_pains"][0]["evidence"][0]["source_type"] = EvidenceSourceType.reference_case.value

    patch = execute_node(UnderlyingPainNode(), state_with_dependencies(), WorkflowServices(llm=client_with_payload(payload)))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_unverified_sales_note_alone_fails() -> None:
    payload = default_underlying_pain_response()
    payload["underlying_pains"][0]["evidence"] = [
        {
            "source_id": "NOTE-01",
            "source_type": EvidenceSourceType.salesperson_note.value,
            "evidence_summary": "销售备注不能单独支持痛点。",
        }
    ]

    patch = execute_node(UnderlyingPainNode(), state_with_dependencies(), WorkflowServices(llm=client_with_payload(payload)))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_meeting_evidence_passes() -> None:
    patch = execute_node(UnderlyingPainNode(), state_with_dependencies(), WorkflowServices(llm=client_with_payload(default_underlying_pain_response())))

    assert patch["underlying_pains"][0].evidence[0].source_id == "MTG-01"


def test_known_constraint_evidence_passes() -> None:
    payload = default_underlying_pain_response()
    payload["underlying_pains"][0]["evidence"] = [
        {
            "source_id": "CONSTRAINT-01",
            "source_type": EvidenceSourceType.known_constraint.value,
            "evidence_summary": "已知限制可作为已验证支持。",
        }
    ]

    patch = execute_node(UnderlyingPainNode(), state_with_dependencies(), WorkflowServices(llm=client_with_payload(payload)))

    assert patch["underlying_pains"][0].evidence[0].source_id == "CONSTRAINT-01"


def test_duplicate_pain_id_fails() -> None:
    payload = default_underlying_pain_response()
    payload["underlying_pains"].append(payload["underlying_pains"][0].copy())

    patch = execute_node(UnderlyingPainNode(), state_with_dependencies(), WorkflowServices(llm=client_with_payload(payload)))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_duplicate_description_fails() -> None:
    payload = default_underlying_pain_response()
    clone = payload["underlying_pains"][0].copy()
    clone["pain_id"] = "PAIN-02"
    payload["underlying_pains"].append(clone)

    patch = execute_node(UnderlyingPainNode(), state_with_dependencies(), WorkflowServices(llm=client_with_payload(payload)))

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_validation_question_gets_question_mark() -> None:
    payload = default_underlying_pain_response()
    payload["underlying_pains"][0]["validation_question"] = "是否影响销售响应速度"

    patch = execute_node(UnderlyingPainNode(), state_with_dependencies(), WorkflowServices(llm=client_with_payload(payload)))

    assert patch["underlying_pains"][0].validation_question.endswith("？")
