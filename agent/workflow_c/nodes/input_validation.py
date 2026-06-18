from __future__ import annotations

from typing import Any

from agent.workflow_c.contracts import InputValidationOutput, NodeContract, NodeFailurePolicy
from agent.workflow_c.state import WorkflowNodeName
from schemas import EvaluationCaseInput


class InputValidationNode:
    contract = NodeContract(
        name=WorkflowNodeName.input_validation,
        required_state_fields=("case_input",),
        produced_state_fields=("validated_case",),
        output_model=InputValidationOutput,
        failure_policy=NodeFailurePolicy.fail_workflow,
        prompt_version=None,
    )

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        return {"validated_case": EvaluationCaseInput.model_validate(state["case_input"])}
