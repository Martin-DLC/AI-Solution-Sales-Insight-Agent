from __future__ import annotations

import json

from agent.workflow_c.executor import execute_node
from agent.workflow_c.fake_llm import (
    FakeWorkflowLLMClient,
    default_buying_intent_response,
    default_fact_response,
    default_stakeholder_response,
)
from agent.workflow_c.nodes import SourceIndexingNode, StakeholderNode
from agent.workflow_c.services import WorkflowLLMResult, WorkflowServices
from agent.workflow_c.state import FactExtractionResult, FailureCategory, WorkflowNodeName
from dataio.runtime_cases import load_runtime_cases
from llm.models import LLMMessage, LLMUsage
from schemas.common_models import (
    ClaimType,
    ConfidenceLevel,
    EvidenceSourceType,
    InfluenceLevel,
    SalesRole,
    StakeholderAttitude,
)
from schemas.insight_models import BuyingIntent


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
        "buying_intent": BuyingIntent.model_validate(default_buying_intent_response()["buying_intent"]),
    }


def client_with_payload(payload: dict) -> FakeWorkflowLLMClient:
    return FakeWorkflowLLMClient(responses_by_node={WorkflowNodeName.stakeholder: payload})


def run_payload(payload: dict):
    return execute_node(
        StakeholderNode(),
        state_with_dependencies(),
        WorkflowServices(llm=client_with_payload(payload)),
    )


class ContentOnlyClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def complete_json_for_node(self, node_name: WorkflowNodeName, messages: list[LLMMessage]) -> WorkflowLLMResult:
        self.calls += 1
        return WorkflowLLMResult(
            content=json.dumps(self.payload, ensure_ascii=False),
            parsed_json=None,
            model="content-only",
            usage=LLMUsage(),
            latency_ms=1,
        )


def confirmed_stakeholder(role: SalesRole = SalesRole.user) -> dict:
    return {
        "stakeholder_id": "STK-X",
        "name_or_role": "业务代表",
        "organization_role": "业务部门代表",
        "sales_role": role.value,
        "influence_level": InfluenceLevel.medium.value,
        "attitude": StakeholderAttitude.supportive.value,
        "confirmed": True,
        "claim_type": ClaimType.fact.value,
        "confidence": ConfidenceLevel.medium.value,
        "evidence": [
            {
                "source_id": "MTG-01",
                "source_type": EvidenceSourceType.meeting_transcript.value,
                "evidence_summary": "会议中出现该角色。",
            }
        ],
        "next_validation": None,
    }


def test_valid_stakeholder_list_passes() -> None:
    patch = run_payload(default_stakeholder_response())

    assert len(patch["stakeholder_map"]) == 2


def test_node_calls_llm_once() -> None:
    client = FakeWorkflowLLMClient.with_default_batch2a_responses()

    execute_node(StakeholderNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert client.calls_for_node(WorkflowNodeName.stakeholder) == 1


def test_prompt_version_is_correct() -> None:
    patch = run_payload(default_stakeholder_response())

    assert patch["node_records"][0].prompt_version == "stakeholder_v1"


def test_content_json_without_parsed_json_passes() -> None:
    client = ContentOnlyClient(default_stakeholder_response())

    patch = execute_node(StakeholderNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert patch["stakeholder_map"][0].stakeholder_id == "STK-01"
    assert client.calls == 1


def test_invalid_json_fails() -> None:
    client = FakeWorkflowLLMClient.with_default_batch2a_responses(invalid_json_nodes={"stakeholder"})

    patch = execute_node(StakeholderNode(), state_with_dependencies(), WorkflowServices(llm=client))

    assert patch["failures"][0].failure_category is FailureCategory.json_parse


def test_schema_missing_field_fails() -> None:
    payload = default_stakeholder_response()
    del payload["stakeholder_map"][0]["organization_role"]

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_duplicate_stakeholder_id_fails() -> None:
    payload = {"stakeholder_map": [confirmed_stakeholder(), confirmed_stakeholder()]}

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_duplicate_name_or_role_fails() -> None:
    first = confirmed_stakeholder()
    second = confirmed_stakeholder()
    second["stakeholder_id"] = "STK-Y"
    second["name_or_role"] = "  业务代表  "
    payload = {"stakeholder_map": [first, second]}

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_unconfirmed_without_next_validation_fails() -> None:
    payload = default_stakeholder_response()
    payload["stakeholder_map"][1]["next_validation"] = None

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_unconfirmed_short_next_validation_fails() -> None:
    payload = default_stakeholder_response()
    payload["stakeholder_map"][1]["next_validation"] = "确认"

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_confirmed_without_evidence_fails() -> None:
    payload = {"stakeholder_map": [confirmed_stakeholder()]}
    payload["stakeholder_map"][0]["evidence"] = []

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_unknown_source_id_fails() -> None:
    payload = {"stakeholder_map": [confirmed_stakeholder()]}
    payload["stakeholder_map"][0]["evidence"][0]["source_id"] = "BAD-01"

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_source_type_mismatch_fails() -> None:
    payload = {"stakeholder_map": [confirmed_stakeholder()]}
    payload["stakeholder_map"][0]["evidence"][0]["source_type"] = EvidenceSourceType.customer_profile.value

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_solution_library_evidence_fails() -> None:
    payload = {"stakeholder_map": [confirmed_stakeholder()]}
    payload["stakeholder_map"][0]["evidence"] = [
        {
            "source_id": "SOLUTION-01",
            "source_type": EvidenceSourceType.solution_library.value,
            "evidence_summary": "方案库不能确认角色。",
        }
    ]

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_reference_case_evidence_fails() -> None:
    payload = {"stakeholder_map": [confirmed_stakeholder()]}
    payload["stakeholder_map"][0]["evidence"][0]["source_type"] = EvidenceSourceType.reference_case.value

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_unverified_note_alone_confirmed_role_fails() -> None:
    payload = {"stakeholder_map": [confirmed_stakeholder()]}
    payload["stakeholder_map"][0]["evidence"] = [
        {
            "source_id": "NOTE-01",
            "source_type": EvidenceSourceType.salesperson_note.value,
            "evidence_summary": "销售备注不能单独确认角色。",
        }
    ]

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_known_constraint_alone_confirmed_decision_maker_fails() -> None:
    payload = {"stakeholder_map": [confirmed_stakeholder(SalesRole.decision_maker)]}
    payload["stakeholder_map"][0]["evidence"] = [
        {
            "source_id": "CONSTRAINT-01",
            "source_type": EvidenceSourceType.known_constraint.value,
            "evidence_summary": "已知限制不能单独确认决策角色。",
        }
    ]

    patch = run_payload(payload)

    assert patch["failures"][0].failure_category is FailureCategory.schema_validation


def test_meeting_evidence_confirms_regular_participant() -> None:
    patch = run_payload({"stakeholder_map": [confirmed_stakeholder()]})

    assert patch["stakeholder_map"][0].confirmed is True


def test_meeting_evidence_confirms_decision_maker() -> None:
    patch = run_payload({"stakeholder_map": [confirmed_stakeholder(SalesRole.decision_maker)]})

    assert patch["stakeholder_map"][0].sales_role is SalesRole.decision_maker


def test_unknown_role_with_next_validation_passes() -> None:
    payload = default_stakeholder_response()
    payload["stakeholder_map"][1]["sales_role"] = SalesRole.unknown.value

    patch = run_payload(payload)

    assert patch["stakeholder_map"][1].sales_role is SalesRole.unknown


def test_supportive_attitude_is_not_auto_promoted_to_champion() -> None:
    patch = run_payload({"stakeholder_map": [confirmed_stakeholder()]})

    assert patch["stakeholder_map"][0].attitude is StakeholderAttitude.supportive
    assert patch["stakeholder_map"][0].sales_role is SalesRole.user


def test_node_does_not_auto_fill_next_validation() -> None:
    payload = default_stakeholder_response()
    payload["stakeholder_map"][1]["next_validation"] = None

    patch = run_payload(payload)

    assert "stakeholder_map" not in patch


def test_failure_does_not_write_stakeholder_map() -> None:
    payload = {"stakeholder_map": [confirmed_stakeholder()]}
    payload["stakeholder_map"][0]["evidence"] = []

    patch = run_payload(payload)

    assert "stakeholder_map" not in patch
