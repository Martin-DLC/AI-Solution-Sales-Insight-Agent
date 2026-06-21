from __future__ import annotations

from pathlib import Path

from agent.workflow_c import (
    FakeWorkflowLLMClient,
    WorkflowNodeName,
    WorkflowServices,
    WorkflowStatus,
    run_architecture_c_skeleton,
)
from dataio.runtime_cases import load_runtime_cases


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def test_invalid_input_does_not_execute_source_index() -> None:
    bad = dev_01_case().model_dump(mode="json")
    bad["case_id"] = "DEV-1"

    snapshot = run_architecture_c_skeleton(
        bad,
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch1b_responses()),
    )

    assert snapshot.workflow_status is WorkflowStatus.failed
    assert [record.node_name for record in snapshot.node_records] == [WorkflowNodeName.input_validation]


def test_llm_request_error_enters_human_review() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1b_responses()
    client.request_error_nodes.add(WorkflowNodeName.fact_extraction)

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.workflow_status is WorkflowStatus.awaiting_human_review


def test_llm_request_error_does_not_execute_context_sufficiency() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1b_responses()
    client.request_error_nodes.add(WorkflowNodeName.fact_extraction)

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert WorkflowNodeName.context_sufficiency not in [record.node_name for record in snapshot.node_records]


def test_invalid_json_generates_json_parse_failure() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1a_responses(
        invalid_json_nodes={"fact_extraction"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.failures[0].failure_category.value == "json_parse"


def test_invalid_json_factory_path_enters_human_review_and_stops_downstream() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1a_responses(
        invalid_json_nodes={"fact_extraction"}
    )

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))
    node_order = [record.node_name for record in snapshot.node_records]

    assert snapshot.workflow_status is WorkflowStatus.awaiting_human_review
    assert snapshot.failures[0].node_name is WorkflowNodeName.fact_extraction
    assert snapshot.failures[0].failure_category.value == "json_parse"
    assert WorkflowNodeName.context_sufficiency not in node_order
    assert WorkflowNodeName.explicit_need not in node_order
    assert WorkflowNodeName.underlying_pain not in node_order
    assert WorkflowNodeName.business_impact not in node_order
    assert node_order[-1] is WorkflowNodeName.human_review_gate
    assert client.total_calls == 1


def test_schema_error_generates_schema_validation_failure() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1b_responses()
    client.schema_error_payloads[WorkflowNodeName.fact_extraction] = {
        "fact_extraction": {"facts": []}
    }

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.failures[0].failure_category.value == "schema_validation"


def test_unauthorized_field_generates_internal_error(monkeypatch) -> None:
    from agent.workflow_c.nodes.fact_extraction import FactExtractionNode

    def bad_run(self, state, services):
        return {"fact_extraction": {}, "extra": "bad"}

    monkeypatch.setattr(FactExtractionNode, "run", bad_run)

    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch1b_responses()),
    )

    assert snapshot.failures[0].failure_category.value == "internal_error"


def test_downstream_nodes_do_not_continue_after_failure() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1b_responses()
    client.request_error_nodes.add(WorkflowNodeName.fact_extraction)

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    node_order = [record.node_name for record in snapshot.node_records]

    assert WorkflowNodeName.context_sufficiency not in node_order
    assert WorkflowNodeName.explicit_need not in node_order
    assert WorkflowNodeName.underlying_pain not in node_order
    assert WorkflowNodeName.business_impact not in node_order


def test_human_review_gate_runs_after_non_input_failure() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1b_responses()
    client.request_error_nodes.add(WorkflowNodeName.fact_extraction)

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert snapshot.node_records[-1].node_name is WorkflowNodeName.human_review_gate


def test_failure_state_does_not_contain_api_key() -> None:
    client = FakeWorkflowLLMClient.with_default_batch1b_responses()
    client.request_error_nodes.add(WorkflowNodeName.fact_extraction)

    snapshot = run_architecture_c_skeleton(dev_01_case(), WorkflowServices(llm=client))

    assert "sk-test-secret" not in str(snapshot.model_dump(mode="json"))


def test_workflow_c_code_does_not_import_evaluation_references() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in Path("agent/workflow_c").rglob("*.py"))

    assert "evaluation_references" not in source


def test_workflow_c_code_does_not_contain_hidden_reference_pack() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in Path("agent/workflow_c").rglob("*.py"))

    assert "HiddenReferencePack" not in source


def test_workflow_c_code_does_not_load_env() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in Path("agent/workflow_c").rglob("*.py"))

    assert ".env" not in source
    assert "load_dotenv" not in source


def test_pytest_does_not_access_network(monkeypatch) -> None:
    import socket

    def fail_socket(*args, **kwargs):
        raise AssertionError("network should not be used")

    monkeypatch.setattr(socket, "socket", fail_socket)

    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch1b_responses()),
    )

    assert snapshot.workflow_status is WorkflowStatus.awaiting_human_review
