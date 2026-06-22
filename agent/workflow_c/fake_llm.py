from __future__ import annotations

import json
from copy import deepcopy
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Mapping

from agent.workflow_c.state import WorkflowNodeName
from agent.workflow_c.services import WorkflowLLMResult
from llm.errors import LLMRequestError
from llm.models import LLMMessage, LLMUsage
from schemas.common_models import (
    BusinessDimension,
    ClaimType,
    ConfidenceLevel,
    ContextQuality,
    EvidenceSourceType,
    InfluenceLevel,
    IntentLevel,
    PriorityLevel,
    SalesRole,
    SalesStage,
    SeverityLevel,
    StakeholderAttitude,
)


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

    @classmethod
    def with_default_batch1a_responses(
        cls,
        *,
        request_error_nodes: set[WorkflowNodeName | str] | None = None,
        invalid_json_nodes: set[WorkflowNodeName | str] | None = None,
        schema_error_nodes: set[WorkflowNodeName | str] | None = None,
        custom_payloads: Mapping[WorkflowNodeName | str, dict[str, Any]] | None = None,
    ) -> "FakeWorkflowLLMClient":
        request_nodes = _normalize_nodes(request_error_nodes)
        invalid_nodes = _normalize_nodes(invalid_json_nodes)
        schema_nodes = _normalize_nodes(schema_error_nodes)
        _ensure_failure_modes_are_exclusive(
            request_nodes=request_nodes,
            invalid_nodes=invalid_nodes,
            schema_nodes=schema_nodes,
        )
        schema_error_payloads = {
            node: _schema_error_payload_for_node(node)
            for node in schema_nodes
        }
        responses_by_node = {
            WorkflowNodeName.fact_extraction: {
                "fact_extraction": default_fact_response(),
            },
            WorkflowNodeName.explicit_need: default_explicit_need_response(),
        }
        for node, payload in (custom_payloads or {}).items():
            responses_by_node[_normalize_node(node)] = deepcopy(payload)
        return cls(
            responses_by_node=responses_by_node,
            request_error_nodes=request_nodes,
            invalid_json_nodes=invalid_nodes,
            schema_error_payloads=schema_error_payloads,
        )

    @classmethod
    def with_default_batch1b_responses(
        cls,
        *,
        request_error_nodes: set[WorkflowNodeName | str] | None = None,
        invalid_json_nodes: set[WorkflowNodeName | str] | None = None,
        schema_error_nodes: set[WorkflowNodeName | str] | None = None,
        custom_payloads: Mapping[WorkflowNodeName | str, dict[str, Any]] | None = None,
    ) -> "FakeWorkflowLLMClient":
        request_nodes = _normalize_nodes(request_error_nodes)
        invalid_nodes = _normalize_nodes(invalid_json_nodes)
        schema_nodes = _normalize_nodes(schema_error_nodes)
        _ensure_failure_modes_are_exclusive(
            request_nodes=request_nodes,
            invalid_nodes=invalid_nodes,
            schema_nodes=schema_nodes,
        )
        schema_error_payloads = {
            node: _schema_error_payload_for_node(node)
            for node in schema_nodes
        }
        responses_by_node = {
            WorkflowNodeName.fact_extraction: {
                "fact_extraction": default_fact_response(),
            },
            WorkflowNodeName.explicit_need: default_explicit_need_response(),
            WorkflowNodeName.underlying_pain: default_underlying_pain_response(),
            WorkflowNodeName.business_impact: default_business_impact_response(),
        }
        for node, payload in (custom_payloads or {}).items():
            responses_by_node[_normalize_node(node)] = deepcopy(payload)
        return cls(
            responses_by_node=responses_by_node,
            request_error_nodes=request_nodes,
            invalid_json_nodes=invalid_nodes,
            schema_error_payloads=schema_error_payloads,
        )

    @classmethod
    def with_default_batch2a_responses(
        cls,
        *,
        request_error_nodes: set[WorkflowNodeName | str] | None = None,
        invalid_json_nodes: set[WorkflowNodeName | str] | None = None,
        schema_error_nodes: set[WorkflowNodeName | str] | None = None,
        custom_payloads: Mapping[WorkflowNodeName | str, dict[str, Any]] | None = None,
    ) -> "FakeWorkflowLLMClient":
        request_nodes = _normalize_nodes(request_error_nodes)
        invalid_nodes = _normalize_nodes(invalid_json_nodes)
        schema_nodes = _normalize_nodes(schema_error_nodes)
        _ensure_failure_modes_are_exclusive(
            request_nodes=request_nodes,
            invalid_nodes=invalid_nodes,
            schema_nodes=schema_nodes,
        )
        schema_error_payloads = {
            node: _schema_error_payload_for_node(node)
            for node in schema_nodes
        }
        responses_by_node = {
            WorkflowNodeName.fact_extraction: {
                "fact_extraction": default_fact_response(),
            },
            WorkflowNodeName.explicit_need: default_explicit_need_response(),
            WorkflowNodeName.underlying_pain: default_underlying_pain_response(),
            WorkflowNodeName.business_impact: default_business_impact_response(),
            WorkflowNodeName.buying_intent: default_buying_intent_response(),
            WorkflowNodeName.stakeholder: default_stakeholder_response(),
        }
        for node, payload in (custom_payloads or {}).items():
            responses_by_node[_normalize_node(node)] = deepcopy(payload)
        return cls(
            responses_by_node=responses_by_node,
            request_error_nodes=request_nodes,
            invalid_json_nodes=invalid_nodes,
            schema_error_payloads=schema_error_payloads,
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


def _schema_error_payload_for_node(node: WorkflowNodeName) -> dict[str, Any]:
    if node is WorkflowNodeName.fact_extraction:
        return {"fact_extraction": {"facts": []}}
    if node is WorkflowNodeName.explicit_need:
        return {"explicit_needs": []}
    if node is WorkflowNodeName.underlying_pain:
        return {"underlying_pains": []}
    if node is WorkflowNodeName.business_impact:
        return {"business_impacts": []}
    if node is WorkflowNodeName.buying_intent:
        return {"buying_intent": {}}
    if node is WorkflowNodeName.stakeholder:
        return {"stakeholder_map": []}
    return {}


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


def default_explicit_need_response() -> dict[str, Any]:
    return {
        "explicit_needs": [
            {
                "need_id": "NEED-01",
                "description": "客户明确希望提升销售线索跟进效率。",
                "priority": PriorityLevel.high.value,
                "claim_type": ClaimType.fact.value,
                "confidence": ConfidenceLevel.high.value,
                "evidence": [
                    {
                        "source_id": "MTG-01",
                        "source_type": EvidenceSourceType.meeting_transcript.value,
                        "evidence_summary": "会议中明确表达了提升销售线索跟进效率的需求。",
                    }
                ],
            }
        ]
    }


def default_underlying_pain_response() -> dict[str, Any]:
    return {
        "underlying_pains": [
            {
                "pain_id": "PAIN-01",
                "description": "客户线索跟进依赖人工整理，可能造成响应效率下降。",
                "business_dimension": BusinessDimension.efficiency.value,
                "severity": SeverityLevel.medium.value,
                "claim_type": ClaimType.inference.value,
                "reasoning_summary": "该痛点由会议中对销售线索跟进效率和手工整理流程的描述推断而来。",
                "confidence": ConfidenceLevel.medium.value,
                "evidence": [
                    {
                        "source_id": "MTG-01",
                        "source_type": EvidenceSourceType.meeting_transcript.value,
                        "evidence_summary": "会议中提到线索跟进效率和手工整理流程。",
                    }
                ],
                "validation_question": "目前人工整理线索信息是否影响了销售响应速度？",
            }
        ]
    }


def default_business_impact_response() -> dict[str, Any]:
    return {
        "business_impacts": [
            {
                "impact_id": "IMPACT-01",
                "description": "线索处理效率不足可能影响销售团队及时跟进潜在客户。",
                "impact_type": BusinessDimension.efficiency.value,
                "quantified": False,
                "current_value": None,
                "target_value": None,
                "claim_type": ClaimType.inference.value,
                "confidence": ConfidenceLevel.medium.value,
                "evidence": [
                    {
                        "source_id": "MTG-01",
                        "source_type": EvidenceSourceType.meeting_transcript.value,
                        "evidence_summary": "会议中描述了线索跟进效率和手工整理问题。",
                    }
                ],
                "measurement_needed": "需要确认当前线索处理周期和目标响应时间。",
            }
        ]
    }


def default_buying_intent_response() -> dict[str, Any]:
    return {
        "buying_intent": {
            "intent_level": IntentLevel.medium_high.value,
            "sales_stage": SalesStage.discovery.value,
            "confidence": ConfidenceLevel.medium.value,
            "positive_signals": ["客户明确表达希望提升销售线索跟进效率。"],
            "negative_signals": [],
            "unknown_factors": ["预算、决策权、采购流程和明确时间表尚未确认。"],
            "reasoning_summary": "客户表达了明确业务需求，但预算、决策权和采购流程仍需验证。",
        }
    }


def default_stakeholder_response() -> dict[str, Any]:
    return {
        "stakeholder_map": [
            {
                "stakeholder_id": "STK-01",
                "name_or_role": "业务参与者",
                "organization_role": "业务部门代表",
                "sales_role": SalesRole.user.value,
                "influence_level": InfluenceLevel.medium.value,
                "attitude": StakeholderAttitude.supportive.value,
                "confirmed": True,
                "claim_type": ClaimType.fact.value,
                "confidence": ConfidenceLevel.medium.value,
                "evidence": [
                    {
                        "source_id": "MTG-01",
                        "source_type": EvidenceSourceType.meeting_transcript.value,
                        "evidence_summary": "会议参与者包含业务相关角色。",
                    }
                ],
                "next_validation": None,
            },
            {
                "stakeholder_id": "STK-02",
                "name_or_role": "待确认决策角色",
                "organization_role": "可能参与预算或决策",
                "sales_role": SalesRole.decision_maker.value,
                "influence_level": InfluenceLevel.unknown.value,
                "attitude": StakeholderAttitude.unknown.value,
                "confirmed": False,
                "claim_type": ClaimType.assumption.value,
                "confidence": ConfidenceLevel.low.value,
                "evidence": [],
                "next_validation": "下一次会议确认谁负责预算和最终决策。",
            },
        ]
    }
