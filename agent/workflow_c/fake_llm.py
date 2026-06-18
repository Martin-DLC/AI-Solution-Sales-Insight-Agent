from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from agent.workflow_c.state import WorkflowNodeName
from agent.workflow_c.services import WorkflowLLMResult
from llm.errors import LLMRequestError
from llm.models import LLMMessage, LLMUsage
from schemas.common_models import ClaimType, ConfidenceLevel, ContextQuality, EvidenceSourceType


@dataclass
class FakeWorkflowLLMClient:
    responses_by_node: dict[WorkflowNodeName, dict[str, Any]] = field(default_factory=dict)
    request_error_nodes: set[WorkflowNodeName] = field(default_factory=set)
    invalid_json_nodes: set[WorkflowNodeName] = field(default_factory=set)
    schema_error_payloads: dict[WorkflowNodeName, dict[str, Any]] = field(default_factory=dict)
    model: str = "fake-workflow-model"
    call_count: int = 0
    calls_by_node: dict[WorkflowNodeName, int] = field(default_factory=lambda: defaultdict(int))
    last_messages: list[LLMMessage] | None = None

    @classmethod
    def with_default_fact_response(
        cls,
        *,
        request_error_nodes: set[WorkflowNodeName | str] | None = None,
        invalid_json_nodes: set[WorkflowNodeName | str] | None = None,
        schema_error_nodes: set[WorkflowNodeName | str] | None = None,
    ) -> "FakeWorkflowLLMClient":
        request_nodes = _normalize_nodes(request_error_nodes)
        invalid_nodes = _normalize_nodes(invalid_json_nodes)
        schema_nodes = _normalize_nodes(schema_error_nodes)
        _ensure_failure_modes_are_exclusive(
            request_nodes=request_nodes,
            invalid_nodes=invalid_nodes,
            schema_nodes=schema_nodes,
        )
        return cls(
            responses_by_node={
                WorkflowNodeName.fact_extraction: default_fact_response(),
            },
            request_error_nodes=request_nodes,
            invalid_json_nodes=invalid_nodes,
            schema_error_payloads={
                node: {"facts": []}
                for node in schema_nodes
            },
        )

    @property
    def total_calls(self) -> int:
        return self.call_count

    def calls_for_node(
        self,
        node_name: WorkflowNodeName | str,
    ) -> int:
        return self.calls_by_node[_normalize_node(node_name)]

    def complete_json_for_node(
        self,
        node_name: WorkflowNodeName | str,
        messages: list[LLMMessage],
    ) -> WorkflowLLMResult:
        node_name = _normalize_node(node_name)
        self.call_count += 1
        self.calls_by_node[node_name] += 1
        self.last_messages = messages
        if node_name in self.request_error_nodes:
            raise LLMRequestError("Fake workflow request failed.")
        if node_name in self.invalid_json_nodes:
            return WorkflowLLMResult(
                content="{not valid json",
                parsed_json=None,
                model=self.model,
                usage=LLMUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
                latency_ms=5,
            )
        payload = self.schema_error_payloads.get(
            node_name,
            self.responses_by_node.get(node_name, {}),
        )
        return WorkflowLLMResult(
            content=json.dumps(payload, ensure_ascii=False),
            parsed_json=payload,
            model=self.model,
            usage=LLMUsage(prompt_tokens=3, completion_tokens=4, total_tokens=7),
            latency_ms=7,
        )


def _normalize_nodes(values: set[WorkflowNodeName | str] | None) -> set[WorkflowNodeName]:
    return {_normalize_node(value) for value in values or set()}


def _normalize_node(value: WorkflowNodeName | str) -> WorkflowNodeName:
    if isinstance(value, WorkflowNodeName):
        return value
    return WorkflowNodeName(value)


def _ensure_failure_modes_are_exclusive(
    *,
    request_nodes: set[WorkflowNodeName],
    invalid_nodes: set[WorkflowNodeName],
    schema_nodes: set[WorkflowNodeName],
) -> None:
    overlaps = {
        "request_error_nodes and invalid_json_nodes": request_nodes & invalid_nodes,
        "request_error_nodes and schema_error_nodes": request_nodes & schema_nodes,
        "invalid_json_nodes and schema_error_nodes": invalid_nodes & schema_nodes,
    }
    conflicts = {
        label: sorted(node.value for node in nodes)
        for label, nodes in overlaps.items()
        if nodes
    }
    if conflicts:
        raise ValueError(f"Fake workflow failure modes are mutually exclusive: {conflicts}.")


def default_fact_response() -> dict[str, Any]:
    return {
        "facts": [
            {
                "fact_id": "FACT-01",
                "category": "business_goal",
                "statement": "客户希望提升销售线索跟进效率。",
                "claim_type": ClaimType.fact.value,
                "confidence": ConfidenceLevel.high.value,
                "evidence": [
                    {
                        "source_id": "MTG-01",
                        "source_type": EvidenceSourceType.meeting_transcript.value,
                        "evidence_summary": "会议中明确提到销售线索跟进效率。",
                    }
                ],
            },
            {
                "fact_id": "FACT-02",
                "category": "pain_or_problem",
                "statement": "现有流程存在手工整理信息的问题。",
                "claim_type": ClaimType.fact.value,
                "confidence": ConfidenceLevel.medium.value,
                "evidence": [
                    {
                        "source_id": "MTG-01",
                        "source_type": EvidenceSourceType.meeting_transcript.value,
                        "evidence_summary": "会议纪要描述了手工整理流程。",
                    }
                ],
            },
            {
                "fact_id": "FACT-03",
                "category": "stakeholders",
                "statement": "会议中存在业务和技术相关参与者。",
                "claim_type": ClaimType.fact.value,
                "confidence": ConfidenceLevel.medium.value,
                "evidence": [
                    {
                        "source_id": "MTG-01",
                        "source_type": EvidenceSourceType.meeting_transcript.value,
                        "evidence_summary": "会议参与者包含多个角色。",
                    }
                ],
            },
        ],
        "unknown_fields": ["budget", "success_metrics"],
        "customer_context_draft": {
            "company_name": "示例客户",
            "industry": "软件服务",
            "company_size": "中型企业",
            "current_systems": ["CRM"],
            "sales_stage_input": "discovery",
            "confirmed_constraints": ["需要人工复核"],
            "context_quality": ContextQuality.partially_sufficient.value,
        },
    }
