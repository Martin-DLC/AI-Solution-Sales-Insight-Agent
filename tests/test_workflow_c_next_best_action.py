from __future__ import annotations

from copy import deepcopy

from agent.workflow_c import (
    FakeWorkflowLLMClient,
    WorkflowNodeName,
    WorkflowServices,
    run_architecture_c_skeleton,
)
from agent.workflow_c.decision_models import WorkflowActionType
from dataio.runtime_cases import load_runtime_cases


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def valid_payload() -> dict:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )
    return {
        "next_best_actions": [
            snapshot.next_best_actions[0].model_dump(mode="json")
        ],
        "action_traces": [snapshot.action_traces[0].model_dump(mode="json")],
    }


def run_with_payload(payload: dict):
    client = FakeWorkflowLLMClient.with_default_batch4b_responses(
        custom_payloads={"next_best_action": payload}
    )
    return run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))


def test_valid_action_passes() -> None:
    assert run_with_payload(valid_payload()).failures == []


def test_node_calls_llm_once() -> None:
    client = FakeWorkflowLLMClient.with_default_batch4b_responses()
    run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    assert client.calls_for_node(WorkflowNodeName.next_best_action) == 1


def test_prompt_version_is_correct() -> None:
    snapshot = run_with_payload(valid_payload())
    record = next(record for record in snapshot.node_records if record.node_name is WorkflowNodeName.next_best_action)
    assert record.prompt_version == "next_best_action_v1"


def test_invalid_json_fails() -> None:
    client = FakeWorkflowLLMClient.with_default_batch4b_responses(
        invalid_json_nodes={"next_best_action"}
    )
    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    assert snapshot.failures[0].node_name is WorkflowNodeName.next_best_action


def test_schema_missing_field_fails() -> None:
    assert run_with_payload({"next_best_actions": []}).failures


def test_duplicate_action_id_fails() -> None:
    payload = valid_payload()
    payload["next_best_actions"].append(deepcopy(payload["next_best_actions"][0]))
    payload["action_traces"].append(deepcopy(payload["action_traces"][0]))
    assert run_with_payload(payload).failures


def test_duplicate_action_description_fails() -> None:
    payload = valid_payload()
    second = deepcopy(payload["next_best_actions"][0])
    second["action_id"] = "ACT-02"
    payload["next_best_actions"].append(second)
    trace = deepcopy(payload["action_traces"][0])
    trace["action_id"] = "ACT-02"
    payload["action_traces"].append(trace)
    assert run_with_payload(payload).failures


def test_gap_id_missing_fails() -> None:
    payload = valid_payload()
    payload["next_best_actions"][0]["related_gap_ids"] = ["GAP-MISSING"]
    assert run_with_payload(payload).failures


def test_risk_id_missing_fails() -> None:
    payload = valid_payload()
    payload["action_traces"][0]["related_risk_ids"] = ["RISK-MISSING"]
    assert run_with_payload(payload).failures


def test_p0_without_high_gap_or_risk_fails() -> None:
    payload = valid_payload()
    payload["next_best_actions"][0]["related_gap_ids"] = []
    payload["action_traces"][0]["related_risk_ids"] = []
    assert run_with_payload(payload).failures


def test_discovery_commercial_proposal_fails() -> None:
    payload = valid_payload()
    payload["action_traces"][0]["action_type"] = WorkflowActionType.commercial_proposal.value
    assert run_with_payload(payload).failures


def test_low_score_qualification_passes() -> None:
    payload = valid_payload()
    payload["action_traces"][0]["action_type"] = WorkflowActionType.qualification.value
    assert run_with_payload(payload).failures == []


def test_vague_action_fails() -> None:
    payload = valid_payload()
    payload["next_best_actions"][0]["action"] = "后续确认"
    assert run_with_payload(payload).failures


def test_node_does_not_auto_fill_participants() -> None:
    payload = valid_payload()
    payload["next_best_actions"][0]["required_participants"] = []
    assert run_with_payload(payload).failures


def test_failure_does_not_write_actions() -> None:
    snapshot = run_with_payload({"next_best_actions": []})
    assert snapshot.next_best_actions is None
    assert snapshot.action_traces is None


def test_does_not_execute_external_actions() -> None:
    snapshot = run_with_payload(valid_payload())
    assert not hasattr(snapshot, "sent_email")
    assert not hasattr(snapshot, "crm_update")
    assert not hasattr(snapshot, "quote_sent")
