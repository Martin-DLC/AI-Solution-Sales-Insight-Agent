from __future__ import annotations

import json
from typing import Any

from agent.workflow_c.contracts import FakeFactExtractionOutput, NodeContract, NodeFailurePolicy
from agent.workflow_c.failures import NodeJSONParseError
from agent.workflow_c.state import WorkflowNodeName
from llm.models import LLMMessage, LLMRole


class FakeFactExtractionNode:
    contract = NodeContract(
        name=WorkflowNodeName.fact_extraction,
        required_state_fields=("validated_case", "source_index"),
        produced_state_fields=("fact_extraction",),
        output_model=FakeFactExtractionOutput,
        failure_policy=NodeFailurePolicy.require_human_review,
        prompt_version="fake_fact_extraction_v1",
    )

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        messages = [
            LLMMessage(role=LLMRole.system, content="NODE: fact_extraction\n只提取事实。"),
            LLMMessage(
                role=LLMRole.user,
                content=(
                    "NODE: fact_extraction\n"
                    "只提取事实，不生成推断、建议或最终报告。"
                ),
            ),
        ]
        result = services.llm.complete_json_for_node(WorkflowNodeName.fact_extraction, messages)
        parsed = result.parsed_json
        if parsed is None:
            try:
                parsed = json.loads(result.content)
            except json.JSONDecodeError as exc:
                raise NodeJSONParseError(
                    message="Fact extraction returned invalid JSON.",
                    content_length=len(result.content),
                    position=exc.pos,
                ) from exc
        return {"fact_extraction": parsed}
