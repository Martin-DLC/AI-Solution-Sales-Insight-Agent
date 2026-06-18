from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from agent.workflow_c.state import WorkflowNodeName
from llm.models import LLMMessage, LLMUsage
from schemas.common_models import StrictBaseModel


class WorkflowLLMResult(StrictBaseModel):
    content: str
    parsed_json: dict[str, Any] | None = None
    model: str
    usage: LLMUsage
    latency_ms: int


class WorkflowJSONClient(Protocol):
    def complete_json_for_node(
        self,
        node_name: WorkflowNodeName,
        messages: list[LLMMessage],
    ) -> WorkflowLLMResult:
        ...


@dataclass
class WorkflowServices:
    llm: WorkflowJSONClient
