from __future__ import annotations

from copy import deepcopy

from agent.workflow_c import (
    FakeWorkflowLLMClient,
    WorkflowNodeName,
    WorkflowServices,
    run_architecture_c_skeleton,
)
from dataio.runtime_cases import load_runtime_cases
from schemas.common_models import SeverityLevel


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def run_with_payload(payload: dict):
    client = FakeWorkflowLLMClient.with_default_batch4b_responses(
        custom_payloads={"risk": payload}
    )
    return run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))


def valid_payload() -> dict:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )
    return {
        "risks_and_objections": [
            snapshot.risks_and_objections[0].model_dump(mode="json")
        ],
        "risk_traces": [snapshot.risk_traces[0].model_dump(mode="json")],
    }


def test_valid_risk_passes() -> None:
    snapshot = run_with_payload(valid_payload())
    assert snapshot.failures == []
    assert snapshot.risks_and_objections


def test_node_calls_llm_once() -> None:
    client = FakeWorkflowLLMClient.with_default_batch4b_responses()
    run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    assert client.calls_for_node(WorkflowNodeName.risk) == 1


def test_prompt_version_is_correct() -> None:
    snapshot = run_with_payload(valid_payload())
    record = next(record for record in snapshot.node_records if record.node_name is WorkflowNodeName.risk)
    assert record.prompt_version == "risk_v1"


def test_invalid_json_fails() -> None:
    client = FakeWorkflowLLMClient.with_default_batch4b_responses(invalid_json_nodes={"risk"})
    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    assert snapshot.failures[0].node_name is WorkflowNodeName.risk


def test_schema_missing_field_fails() -> None:
    snapshot = run_with_payload({"risks_and_objections": []})
    assert snapshot.failures[0].node_name is WorkflowNodeName.risk


def test_duplicate_risk_id_fails() -> None:
    payload = valid_payload()
    payload["risks_and_objections"].append(deepcopy(payload["risks_and_objections"][0]))
    payload["risk_traces"].append(deepcopy(payload["risk_traces"][0]))
    assert run_with_payload(payload).failures


def test_duplicate_risk_description_fails() -> None:
    payload = valid_payload()
    second = deepcopy(payload["risks_and_objections"][0])
    second["risk_id"] = "RISK-02"
    payload["risks_and_objections"].append(second)
    trace = deepcopy(payload["risk_traces"][0])
    trace["risk_id"] = "RISK-02"
    payload["risk_traces"].append(trace)
    assert run_with_payload(payload).failures


def test_gap_id_missing_fails() -> None:
    payload = valid_payload()
    payload["risk_traces"][0]["related_gap_ids"] = ["GAP-MISSING"]
    assert run_with_payload(payload).failures


def test_opportunity_id_missing_fails() -> None:
    payload = valid_payload()
    payload["risk_traces"][0]["related_opportunity_ids"] = ["OPP-MISSING"]
    assert run_with_payload(payload).failures


def test_risk_without_trace_relation_fails() -> None:
    payload = valid_payload()
    payload["risk_traces"][0]["related_gap_ids"] = []
    payload["risk_traces"][0]["related_opportunity_ids"] = []
    assert run_with_payload(payload).failures


def test_medium_risk_passes() -> None:
    payload = valid_payload()
    payload["risks_and_objections"][0]["severity"] = SeverityLevel.medium.value
    snapshot = run_with_payload(payload)
    assert snapshot.failures == []


def test_unknown_evidence_source_fails() -> None:
    payload = valid_payload()
    payload["risks_and_objections"][0]["evidence"][0]["source_id"] = "NO-SOURCE"
    assert run_with_payload(payload).failures


def test_does_not_modify_deal_score() -> None:
    snapshot = run_with_payload(valid_payload())
    assert snapshot.deal_score.total_score == 50


def test_failure_does_not_write_risks() -> None:
    snapshot = run_with_payload({"risks_and_objections": []})
    assert snapshot.risks_and_objections is None
    assert snapshot.risk_traces is None


def test_does_not_generate_next_best_action_when_risk_fails() -> None:
    snapshot = run_with_payload({"risks_and_objections": []})
    assert snapshot.next_best_actions is None
