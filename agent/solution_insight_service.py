from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any

from agent.models import (
    SolutionInsightEnterpriseContext,
    SolutionInsightEvidenceItem,
    SolutionInsightRequest,
    SolutionInsightResponse,
    SolutionInsightRetrievalDebug,
    SolutionInsightSkillTrace,
    SolutionInsightShadowDebug,
)
from agent.mcp_mock import EnterpriseContextMockClient
from agent.prompts.solution_insight_prompt import build_solution_insight_messages
from agent.skills import (
    EnterpriseContextSkill,
    FallbackAssessmentSkill,
    FormalRetrievalSkill,
    RequirementUnderstandingSkill,
    ShadowRetrievalSkill,
    SkillInput,
    SkillRegistry,
    SolutionGenerationSkill,
)
from dataio.jsonl_loader import load_jsonl_models
from evaluation.retrieval.contracts_v2 import RetrievalRuntimeContextV2
from evaluation.retrieval.runner_v2 import (
    project_v2_chunks_to_legacy_runtime_inputs,
    project_v2_documents_to_legacy_runtime_inputs,
)
from knowledge_base import KnowledgeChunkV2, KnowledgeDocumentV2
from knowledge_base.retrieval import (
    FakeEmbeddingProvider,
    HierarchicalRetrievalMode,
    HierarchicalShadowConfig,
    LexicalBaselineConfig,
    ShadowHierarchicalRetrievalService,
    WeightedBM25Retriever,
    build_query_hash,
)
from llm import LLMClient, LLMConfigurationError, create_llm_client


DOCUMENTS_V2_PATH = Path("data/knowledge_base/documents.v2.jsonl")
CHUNKS_V2_PATH = Path("data/knowledge_base/chunks.v2.jsonl")
LEXICAL_CONFIG_V2_PATH = Path("data/evaluation/retrieval/lexical_baseline_config.v2.json")
RETRIEVAL_COMPARISON_V2_PATH = Path("data/evaluation/retrieval/retrieval_method_comparison.v2.json")
MIN_FORMAL_EVIDENCE_COUNT = 2


class SolutionInsightService:
    def __init__(
        self,
        *,
        formal_retriever: Any,
        documents: list[KnowledgeDocumentV2],
        chunks: list[KnowledgeChunkV2],
        comparison_payload: dict[str, Any],
        shadow_service: ShadowHierarchicalRetrievalService | None = None,
        llm_client: LLMClient | None = None,
        llm_mode: str = "deterministic",
    ) -> None:
        self._formal_retriever = formal_retriever
        self._documents = documents
        self._chunks = chunks
        self._documents_by_id = {document.document_id: document for document in documents}
        self._chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        self._comparison_payload = comparison_payload
        self._shadow_service = shadow_service
        self._llm_client = llm_client
        self._llm_mode = llm_mode
        self._enterprise_context_client = EnterpriseContextMockClient()
        self._skills = self._build_skill_registry()

    @classmethod
    def from_defaults(
        cls,
        *,
        enable_shadow_retrieval: bool = False,
        llm_mode: str = "deterministic",
    ) -> "SolutionInsightService":
        documents = load_jsonl_models(DOCUMENTS_V2_PATH, KnowledgeDocumentV2)
        chunks = load_jsonl_models(CHUNKS_V2_PATH, KnowledgeChunkV2)
        comparison_payload = json.loads(RETRIEVAL_COMPARISON_V2_PATH.read_text(encoding="utf-8"))
        lexical_config = LexicalBaselineConfig.model_validate(
            json.loads(LEXICAL_CONFIG_V2_PATH.read_text(encoding="utf-8"))["algorithm_config"]
        )
        formal_retriever = WeightedBM25Retriever(config=lexical_config)
        formal_retriever.build_index(
            documents=project_v2_documents_to_legacy_runtime_inputs(documents),
            chunks=project_v2_chunks_to_legacy_runtime_inputs(chunks),
        )

        shadow_service = None
        if enable_shadow_retrieval or os.getenv("HIERARCHICAL_RETRIEVAL_MODE", "").strip().casefold() == "shadow":
            shadow_service = ShadowHierarchicalRetrievalService(
                formal_retriever=formal_retriever,
                shadow_chunk_ranker=formal_retriever,
                embedding_provider=FakeEmbeddingProvider(dimension=384, provider_id="shadow_fake_embedding_v1"),
                documents=documents,
                chunks=chunks,
                config=HierarchicalShadowConfig(
                    mode=HierarchicalRetrievalMode.shadow,
                    formal_top_k=lexical_config.top_k,
                    shadow_candidate_k=20,
                ),
            )

        llm_client = None
        resolved_mode = llm_mode
        if llm_mode == "auto":
            try:
                llm_client = create_llm_client()
                resolved_mode = "llm"
            except (LLMConfigurationError, Exception):
                llm_client = None
                resolved_mode = "deterministic"

        return cls(
            formal_retriever=formal_retriever,
            documents=documents,
            chunks=chunks,
            comparison_payload=comparison_payload,
            shadow_service=shadow_service,
            llm_client=llm_client,
            llm_mode=resolved_mode,
        )

    def generate_insight(self, request: SolutionInsightRequest) -> SolutionInsightResponse:
        request_id = f"insight-{secrets.token_hex(6)}"
        effective_llm_mode = request.llm_mode if request.llm_mode != "deterministic" else self._llm_mode
        if effective_llm_mode in {"auto", "llm"} and self._llm_client is None:
            try:
                self._llm_client = create_llm_client()
            except (LLMConfigurationError, Exception):
                effective_llm_mode = "deterministic"
        previous_outputs, skill_outputs, skill_trace = self._skills.execute_sequence(
            [
                "requirement_understanding",
                "enterprise_context",
                "formal_retrieval",
                "shadow_retrieval",
                "fallback_assessment",
                "solution_generation",
            ],
            SkillInput(
                request_id=request_id,
                user_query=request.user_query,
                context={
                    "request": request,
                    "effective_llm_mode": effective_llm_mode,
                },
            ),
        )

        formal_output = previous_outputs["formal_retrieval"]
        fallback_output = previous_outputs["fallback_assessment"]
        generation = previous_outputs["solution_generation"]
        enterprise_context_output = previous_outputs["enterprise_context"]
        evidence_items = formal_output["evidence_items"]
        retrieval_debug = formal_output["retrieval_debug"]
        shadow_debug = previous_outputs["shadow_retrieval"].get("shadow_retrieval_debug")
        fallback_recommended = bool(fallback_output["fallback_recommended"])
        fallback_reasons = list(fallback_output["fallback_reasons"])
        query_hash = formal_output["query_hash"]
        enterprise_context_payload = enterprise_context_output.get("enterprise_context")

        note = (
            "当前证据不足，需要人工确认或补充资料"
            if fallback_recommended
            else generation["response_note"]
        )
        log_record = {
            "request_id": request_id,
            "query_hash": query_hash,
            "formal_candidate_count": len(formal_output["formal_candidates"]),
            "evidence_count": len(evidence_items),
            "fallback_recommended": fallback_recommended,
            "fallback_reasons": list(fallback_reasons),
            "shadow_mode": "shadow" if shadow_debug is not None else "off",
            "shadow_error": shadow_debug.shadow_error if shadow_debug is not None else None,
            "llm_mode": effective_llm_mode,
            "skill_count": skill_trace.skill_count,
            "failed_skill_count": skill_trace.failed_skill_count,
            "enterprise_context_present": enterprise_context_payload is not None,
        }

        return SolutionInsightResponse(
            request_id=request_id,
            requirement_summary=generation["requirement_summary"],
            pain_points=generation["pain_points"],
            ai_opportunity_points=generation["ai_opportunity_points"],
            proposed_solution=generation["proposed_solution"],
            evidence_items=evidence_items,
            evidence_completeness=fallback_output["evidence_completeness"],
            fallback_recommended=fallback_recommended,
            fallback_reasons=fallback_reasons,
            human_confirmation_required=fallback_output["human_confirmation_required"],
            llm_mode=effective_llm_mode,
            retrieval_debug=retrieval_debug,
            shadow_retrieval_debug=shadow_debug,
            enterprise_context=(
                SolutionInsightEnterpriseContext.model_validate(enterprise_context_payload)
                if enterprise_context_payload is not None
                else None
            ),
            skill_trace=skill_trace,
            response_note=note,
            log_record=log_record,
        )

    def _build_skill_registry(self) -> SkillRegistry:
        registry = SkillRegistry()
        registry.register(RequirementUnderstandingSkill(service=self))
        registry.register(EnterpriseContextSkill(service=self))
        registry.register(FormalRetrievalSkill(service=self))
        registry.register(ShadowRetrievalSkill(service=self))
        registry.register(FallbackAssessmentSkill(service=self))
        registry.register(SolutionGenerationSkill(service=self))
        return registry

    def _build_runtime_context(self, request: SolutionInsightRequest) -> RetrievalRuntimeContextV2:
        allowed_document_types = [
            "solution",
            "capability",
            "case_study",
            "implementation_playbook",
            "security_compliance",
            "delivery_constraint",
            "integration_requirement",
            "commercial_rule",
            "unsupported_scenario",
            "readiness_requirement",
        ]
        known_industries = {
            industry.casefold()
            for document in self._documents
            for industry in document.industries
        }
        industries = [request.industry] if request.industry and request.industry.casefold() in known_industries else []
        return RetrievalRuntimeContextV2(
            operational_solution_scope=sorted({solution_id for document in self._documents for solution_id in document.applicable_solution_ids}),
            allowed_document_types=allowed_document_types,
            industries=industries,
            tags=[],
        )

    def _build_filters(self, runtime_context: RetrievalRuntimeContextV2) -> dict[str, object]:
        filters: dict[str, object] = {
            "solution_ids": list(runtime_context.operational_solution_scope),
            "document_types": list(runtime_context.allowed_document_types),
        }
        if runtime_context.industries:
            filters["industries"] = list(runtime_context.industries)
        if runtime_context.tags:
            filters["tags"] = list(runtime_context.tags)
        return filters

    def _build_query(self, request: SolutionInsightRequest) -> str:
        parts = [request.user_query]
        if request.industry:
            parts.append(f"行业：{request.industry}")
        if request.company_size:
            parts.append(f"企业规模：{request.company_size}")
        if request.target_goal:
            parts.append(f"目标：{request.target_goal}")
        if request.current_systems:
            parts.append(f"现有系统：{', '.join(request.current_systems)}")
        if request.constraints:
            parts.append(f"约束：{', '.join(request.constraints)}")
        return "\n".join(part for part in parts if part).strip()

    def _should_run_shadow(self, request: SolutionInsightRequest) -> bool:
        return request.enable_shadow_retrieval or (
            self._shadow_service is not None and self._shadow_service.mode == HierarchicalRetrievalMode.shadow
        )

    def _create_default_shadow_service(self) -> ShadowHierarchicalRetrievalService:
        return ShadowHierarchicalRetrievalService(
            formal_retriever=self._formal_retriever,
            shadow_chunk_ranker=self._formal_retriever,
            embedding_provider=FakeEmbeddingProvider(dimension=384, provider_id="shadow_fake_embedding_v1"),
            documents=self._documents,
            chunks=self._chunks,
            config=HierarchicalShadowConfig(mode=HierarchicalRetrievalMode.shadow),
        )

    def _build_query_hash(self, query: str) -> str:
        return build_query_hash(query)

    def _build_evidence_items(self, candidates: list[Any]) -> list[SolutionInsightEvidenceItem]:
        items: list[SolutionInsightEvidenceItem] = []
        for candidate in candidates:
            document = self._documents_by_id[candidate.document_id]
            chunk = self._chunks_by_id.get(candidate.chunk_id) if candidate.chunk_id else None
            excerpt = (chunk.content if chunk is not None else document.summary)[:220]
            items.append(
                SolutionInsightEvidenceItem(
                    title=document.title,
                    candidate_type="chunk" if candidate.chunk_id else "document",
                    document_id=document.document_id,
                    chunk_id=candidate.chunk_id,
                    citation_label=candidate.citation_label,
                    content_excerpt=excerpt,
                    runtime_eligible=True,
                    rejection_reasons=[],
                )
            )
        return items

    def _build_retrieval_debug(
        self,
        *,
        formal_candidates: list[Any],
        evidence_items: list[SolutionInsightEvidenceItem],
        query_hash: str,
    ) -> SolutionInsightRetrievalDebug:
        return SolutionInsightRetrievalDebug(
            retrieval_method="lexical_v2_formal",
            formal_candidate_count=len(formal_candidates),
            evidence_count=len(evidence_items),
            top_k=5,
            query_hash=query_hash,
            blocked_retrieval_status=self._comparison_payload.get("selection_status", "unknown"),
            selected_method=self._comparison_payload.get("selected_method"),
            selection_status=self._comparison_payload.get("selection_status"),
        )

    def _build_shadow_debug(self, shadow_result: Any) -> SolutionInsightShadowDebug:
        return SolutionInsightShadowDebug(
            hierarchical_mode=shadow_result.hierarchical_mode.value,
            candidate_count=shadow_result.candidate_count,
            document_candidate_count=shadow_result.document_candidate_count,
            chunk_candidate_count=shadow_result.chunk_candidate_count,
            runtime_eligible_count=shadow_result.runtime_eligible_count,
            runtime_rejected_count=shadow_result.runtime_rejected_count,
            rejection_reason_counts=shadow_result.rejection_reason_counts,
            evidence_complete=shadow_result.evidence_complete,
            fallback_recommended=shadow_result.fallback_recommended,
            fallback_reasons=shadow_result.fallback_reasons,
            shadow_error=shadow_result.shadow_error,
        )

    def _assess_fallback(
        self,
        *,
        evidence_items: list[SolutionInsightEvidenceItem],
        retrieval_error: str | None,
        shadow_result: Any | None,
        company_id: str | None = None,
        enterprise_context: dict[str, Any] | None = None,
    ) -> list[str]:
        reasons: list[str] = []
        if retrieval_error is not None:
            reasons.append("retrieval_error")
        if not evidence_items and retrieval_error is None:
            reasons.append("no_evidence_found")
        if evidence_items and all(item.runtime_eligible is False for item in evidence_items):
            reasons.append("all_evidence_filtered")
        if len(evidence_items) < MIN_FORMAL_EVIDENCE_COUNT:
            reasons.append("evidence_count_below_minimum")
        if self._comparison_payload.get("selection_status") != "eligible_method_selected":
            reasons.append("boundary_status_blocked_or_unknown")
        if shadow_result is not None:
            has_shadow_parent = any(
                candidate.candidate_type.value == "document" and candidate.runtime_eligible
                for candidate in shadow_result.candidates
            )
            if has_shadow_parent and len(evidence_items) < shadow_result.runtime_eligible_count:
                reasons.append("shadow_detected_parent_child_gap")
            if shadow_result.shadow_error:
                reasons.append("shadow_pipeline_error")
        if company_id and enterprise_context is None:
            reasons.append("enterprise_context_missing")
        if company_id and enterprise_context is not None:
            readiness = (
                enterprise_context.get("knowledge_context", {}).get("data_readiness_level", "")
                if isinstance(enterprise_context, dict)
                else ""
            )
            if str(readiness).strip().casefold() == "low":
                reasons.append("enterprise_context_data_readiness_low")
        return _deduplicate(reasons)

    def _generate_content(
        self,
        *,
        request: SolutionInsightRequest,
        evidence_items: list[SolutionInsightEvidenceItem],
        formal_evidence_payload: list[dict[str, Any]],
        fallback_recommended: bool,
        llm_mode: str,
    ) -> dict[str, Any]:
        if self._llm_client is not None and llm_mode in {"auto", "llm"}:
            try:
                messages = build_solution_insight_messages(
                    request=request,
                    formal_evidence_payload=[
                        {
                            "title": item["title"],
                            "candidate_type": item["candidate_type"],
                            "document_id": item["document_id"],
                            "chunk_id": item.get("chunk_id"),
                            "citation_label": item["citation_label"],
                            "content_excerpt": item["content_excerpt"],
                        }
                        for item in formal_evidence_payload
                    ],
                )
                response = self._llm_client.complete_json(messages)
                parsed = response.parsed_json or {}
                return {
                    "requirement_summary": str(parsed.get("requirement_summary") or self._default_requirement_summary(request)),
                    "pain_points": _ensure_string_list(parsed.get("pain_points")) or self._default_pain_points(request),
                    "ai_opportunity_points": _ensure_string_list(parsed.get("ai_opportunity_points")) or self._default_ai_opportunities(request, evidence_items),
                    "proposed_solution": str(parsed.get("proposed_solution") or self._default_proposed_solution(evidence_items)),
                    "response_note": str(parsed.get("response_note") or self._default_response_note(fallback_recommended)),
                }
            except Exception:
                pass

        return {
            "requirement_summary": self._default_requirement_summary(request),
            "pain_points": self._default_pain_points(request),
            "ai_opportunity_points": self._default_ai_opportunities(request, evidence_items),
            "proposed_solution": self._default_proposed_solution(evidence_items),
            "response_note": self._default_response_note(fallback_recommended),
        }

    def _default_requirement_summary(self, request: SolutionInsightRequest) -> str:
        summary = request.user_query.strip()
        if request.target_goal:
            summary = f"{summary} 目标是 {request.target_goal}。"
        return summary

    def _default_pain_points(self, request: SolutionInsightRequest) -> list[str]:
        pain_points: list[str] = []
        text = " ".join([request.user_query, request.target_goal or "", " ".join(request.constraints)]).casefold()
        if any(keyword in text for keyword in ["转化", "线索", "销售"]):
            pain_points.append("销售线索识别与转化效率不稳定。")
        if any(keyword in text for keyword in ["客服", "成功", "支持", "服务"]):
            pain_points.append("客户支持与客户成功团队需要更快拿到可引用的信息。")
        if any(keyword in text for keyword in ["合规", "风险", "审计", "安全"]):
            pain_points.append("高风险场景下需要更严格的证据引用和人工确认。")
        if not pain_points:
            pain_points.append("当前需求描述尚需进一步澄清业务流程、数据准备度和上线约束。")
        return pain_points

    def _default_ai_opportunities(
        self,
        request: SolutionInsightRequest,
        evidence_items: list[SolutionInsightEvidenceItem],
    ) -> list[str]:
        points: list[str] = []
        text = request.user_query.casefold()
        if any(keyword in text for keyword in ["知识库", "检索", "问答", "支持"]):
            points.append("构建带证据引用的企业知识检索助手。")
        if any(keyword in text for keyword in ["销售", "线索", "转化"]):
            points.append("围绕销售场景做线索优先级判断和话术辅助。")
        if evidence_items:
            points.append(f"优先从已检索到的 {len(evidence_items)} 条正式证据里收敛可落地方向。")
        return points or ["先建立可验证证据链，再逐步扩展到流程自动化。"]

    def _default_proposed_solution(self, evidence_items: list[SolutionInsightEvidenceItem]) -> str:
        if not evidence_items:
            return "当前没有足够正式证据支持具体方案，建议先补充业务流程、数据源和约束信息。"
        titles = _deduplicate([item.title for item in evidence_items[:3]])
        return f"建议优先围绕这些已命中的知识主题做方案收敛：{'; '.join(titles)}。先做人工确认后的小范围试点，再决定是否扩展。"

    def _default_response_note(self, fallback_recommended: bool) -> str:
        if fallback_recommended:
            return "当前证据不足，需要人工确认或补充资料。"
        return "以下结论仅基于正式检索到的证据整理，仍建议在客户沟通前进行人工复核。"


def _ensure_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
