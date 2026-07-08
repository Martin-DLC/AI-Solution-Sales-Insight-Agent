from __future__ import annotations

from agent.models import SolutionInsightRequest
from agent.prompts.solution_insight_prompt import build_solution_insight_messages
from agent.solution_insight_service import SolutionInsightService
from evaluation.retrieval.models import RetrievalCandidate, RetrievalMethod
from knowledge_base.contracts_v2 import KnowledgeChunkV2, KnowledgeDocumentV2, load_demo_solution_ids_v2
from knowledge_base.retrieval.embeddings import FakeEmbeddingProvider
from knowledge_base.retrieval.shadow import HierarchicalShadowConfig, ShadowHierarchicalRetrievalService


class FakeRetriever:
    def __init__(self, candidates: list[RetrievalCandidate], *, fail: bool = False) -> None:
        self._candidates = candidates
        self._fail = fail
        self.calls = 0

    def retrieve(self, *, query: str, filters: dict[str, object], top_k: int) -> list[RetrievalCandidate]:
        self.calls += 1
        if self._fail:
            raise RuntimeError("retrieval failed")
        return list(self._candidates[:top_k])


class FailingLLMClient:
    def complete_json(self, messages):  # type: ignore[no-untyped-def]
        raise RuntimeError("llm failed")


def _solution_ids() -> tuple[str, str]:
    ids = load_demo_solution_ids_v2()
    return ids[0], ids[1]


def _document(document_id: str, *, applicable: list[str]) -> KnowledgeDocumentV2:
    return KnowledgeDocumentV2(
        document_id=document_id,
        title=f"title-{document_id}",
        document_type="solution",
        status="approved",
        summary="这是一个足够长的摘要文本。",
        content="这是一个足够长的正文内容，用于端到端 service 测试。",
        tags=["priority"],
        industries=["retail"],
        source_uri=f"synthetic://{document_id}",
        primary_solution_id=applicable[0],
        applicable_solution_ids=applicable,
        excluded_solution_ids=[],
        scope_type="solution_specific",
        scope_notes="test",
    )


def _chunk(chunk_id: str, document_id: str, *, applicable: list[str]) -> KnowledgeChunkV2:
    return KnowledgeChunkV2(
        chunk_id=chunk_id,
        document_id=document_id,
        document_type="solution",
        chunk_index=0,
        content=f"{chunk_id} 对应的正式证据内容，长度足够稳定。",
        token_estimate=20,
        tags=["priority"],
        industries=["retail"],
        metadata={"section_title": "Overview"},
        citation_label=f"{document_id} - Overview",
        primary_solution_id=applicable[0],
        applicable_solution_ids=applicable,
        excluded_solution_ids=[],
        scope_type="solution_specific",
        scope_notes="test",
    )


def _candidate(document_id: str, chunk_id: str | None, score: float, rank: int, solution_id: str) -> RetrievalCandidate:
    return RetrievalCandidate(
        rank=rank,
        document_id=document_id,
        chunk_id=chunk_id,
        score=score,
        retrieval_method=RetrievalMethod.lexical_v1,
        matched_terms=[],
        metadata={},
        citation_label=f"{document_id} - Overview",
        solution_ids=[solution_id],
    )


def _service(
    *,
    formal_candidates: list[RetrievalCandidate],
    shadow_candidates: list[RetrievalCandidate] | None = None,
    formal_fail: bool = False,
    llm_client=None,
    llm_mode: str = "deterministic",
) -> SolutionInsightService:
    solution_a, _solution_b = _solution_ids()
    documents = [_document("DOC-001", applicable=[solution_a]), _document("DOC-002", applicable=[solution_a])]
    chunks = [
        _chunk("DOC-001#chunk-1", "DOC-001", applicable=[solution_a]),
        _chunk("DOC-002#chunk-1", "DOC-002", applicable=[solution_a]),
    ]
    shadow_service = None
    if shadow_candidates is not None:
        shadow_service = ShadowHierarchicalRetrievalService(
            formal_retriever=FakeRetriever(formal_candidates, fail=formal_fail),
            shadow_chunk_ranker=FakeRetriever(shadow_candidates),
            embedding_provider=FakeEmbeddingProvider(dimension=384, provider_id="shadow_fake_embedding_v1"),
            documents=documents,
            chunks=chunks,
            config=HierarchicalShadowConfig(mode="shadow"),
        )
        formal_retriever = shadow_service._formal_retriever  # type: ignore[attr-defined]
    else:
        formal_retriever = FakeRetriever(formal_candidates, fail=formal_fail)
    comparison_payload = {
        "selected_method": None,
        "selection_status": "no_eligible_method",
    }
    return SolutionInsightService(
        formal_retriever=formal_retriever,
        documents=documents,
        chunks=chunks,
        comparison_payload=comparison_payload,
        shadow_service=shadow_service,
        llm_client=llm_client,
        llm_mode=llm_mode,
    )


def test_service_runs_without_llm_api_key() -> None:
    solution_a, _solution_b = _solution_ids()
    service = _service(
        formal_candidates=[
            _candidate("DOC-001", "DOC-001#chunk-1", 0.8, 1, solution_a),
            _candidate("DOC-002", "DOC-002#chunk-1", 0.7, 2, solution_a),
        ]
    )
    response = service.generate_insight(
        SolutionInsightRequest(
            user_query="一家中型 SaaS 公司想提升销售线索转化和客户成功效率",
            industry="SaaS",
        )
    )

    assert response.llm_mode == "deterministic"
    assert response.evidence_items
    assert response.requirement_summary
    assert response.human_confirmation_required is True
    assert "boundary_status_blocked_or_unknown" in response.fallback_reasons
    assert response.enterprise_context is None
    assert response.skill_trace is not None
    assert response.skill_trace.executed_skills == [
        "requirement_understanding",
        "enterprise_context",
        "formal_retrieval",
        "shadow_retrieval",
        "fallback_assessment",
        "solution_generation",
    ]


def test_no_evidence_triggers_fallback() -> None:
    service = _service(formal_candidates=[])

    response = service.generate_insight(SolutionInsightRequest(user_query="希望做一个企业知识问答助手"))

    assert response.fallback_recommended is True
    assert "no_evidence_found" in response.fallback_reasons
    assert response.response_note == "当前证据不足，需要人工确认或补充资料"


def test_llm_error_triggers_fallback_template() -> None:
    solution_a, _solution_b = _solution_ids()
    service = _service(
        formal_candidates=[_candidate("DOC-001", "DOC-001#chunk-1", 0.8, 1, solution_a)],
        llm_client=FailingLLMClient(),
        llm_mode="llm",
    )

    response = service.generate_insight(SolutionInsightRequest(user_query="希望提升客服支持效率"))

    assert response.requirement_summary
    assert response.llm_mode == "llm"
    assert response.fallback_recommended is True


def test_shadow_mode_does_not_change_formal_evidence() -> None:
    solution_a, _solution_b = _solution_ids()
    formal = [_candidate("DOC-001", "DOC-001#chunk-1", 0.8, 1, solution_a)]
    shadow = [
        _candidate("DOC-001", "DOC-001#chunk-1", 0.9, 1, solution_a),
        _candidate("DOC-002", "DOC-002#chunk-1", 0.7, 2, solution_a),
    ]
    service = _service(formal_candidates=formal, shadow_candidates=shadow)

    response = service.generate_insight(
        SolutionInsightRequest(
            user_query="想做带证据引用的内部知识检索",
            enable_shadow_retrieval=True,
        )
    )

    assert [item.document_id for item in response.evidence_items] == ["DOC-001"]
    assert response.shadow_retrieval_debug is not None
    assert response.shadow_retrieval_debug.candidate_count >= 2


def test_prompt_uses_only_formal_evidence_not_shadow_debug() -> None:
    request = SolutionInsightRequest(
        user_query="想做带证据引用的内部知识检索",
        enable_shadow_retrieval=True,
    )
    messages = build_solution_insight_messages(
        request=request,
        formal_evidence_payload=[
            {
                "title": "Formal Doc",
                "candidate_type": "chunk",
                "document_id": "DOC-001",
                "chunk_id": "DOC-001#chunk-1",
                "citation_label": "DOC-001 - Overview",
                "content_excerpt": "formal evidence",
            }
        ],
    )
    prompt_text = messages[1].content

    assert "Formal Doc" in prompt_text
    assert "shadow" in messages[0].content.casefold()
    assert "document:DOC-002" not in prompt_text


def test_shadow_off_does_not_run_shadow_pipeline() -> None:
    solution_a, _solution_b = _solution_ids()
    service = _service(
        formal_candidates=[_candidate("DOC-001", "DOC-001#chunk-1", 0.8, 1, solution_a)],
        shadow_candidates=None,
    )

    response = service.generate_insight(SolutionInsightRequest(user_query="想做内部知识问答"))

    assert response.shadow_retrieval_debug is None
    assert response.skill_trace is not None
    assert response.skill_trace.skill_count == 6


def test_shadow_failure_does_not_break_formal_output() -> None:
    solution_a, _solution_b = _solution_ids()
    service = _service(
        formal_candidates=[_candidate("DOC-001", "DOC-001#chunk-1", 0.8, 1, solution_a)],
        shadow_candidates=[_candidate("DOC-002", "DOC-002#chunk-1", 0.7, 1, solution_a)],
        formal_fail=True,
    )

    response = service.generate_insight(
        SolutionInsightRequest(user_query="想做带证据引用的内部知识检索", enable_shadow_retrieval=True)
    )

    assert response.shadow_retrieval_debug is None
    assert response.fallback_recommended is True
    assert "retrieval_error" in response.fallback_reasons
    assert response.skill_trace is not None
    assert response.skill_trace.failed_skill_count >= 1


def test_company_context_is_exposed_when_company_id_is_present() -> None:
    solution_a, _solution_b = _solution_ids()
    service = _service(
        formal_candidates=[
            _candidate("DOC-001", "DOC-001#chunk-1", 0.8, 1, solution_a),
            _candidate("DOC-002", "DOC-002#chunk-1", 0.7, 2, solution_a),
        ]
    )

    response = service.generate_insight(
        SolutionInsightRequest(
            user_query="一家中型 SaaS 公司想提升销售线索转化和客户成功效率",
            industry="SaaS",
            company_id="demo_saas_001",
        )
    )

    assert response.enterprise_context is not None
    assert response.enterprise_context.context_source == "mcp_mock"
    assert response.enterprise_context.provider_success_count == 4
    assert response.enterprise_context.provider_failed_count == 0
    assert response.enterprise_context.provider_skipped_count == 0
    assert len(response.enterprise_context.provider_results) == 4
    assert response.skill_trace is not None
    assert "enterprise_context" in response.skill_trace.executed_skills


def test_unknown_company_id_does_not_break_main_flow() -> None:
    solution_a, _solution_b = _solution_ids()
    service = _service(
        formal_candidates=[
            _candidate("DOC-001", "DOC-001#chunk-1", 0.8, 1, solution_a),
            _candidate("DOC-002", "DOC-002#chunk-1", 0.7, 2, solution_a),
        ]
    )

    response = service.generate_insight(
        SolutionInsightRequest(
            user_query="一家中型 SaaS 公司想提升销售线索转化和客户成功效率",
            industry="SaaS",
            company_id="unknown_company",
        )
    )

    assert response.requirement_summary
    assert response.enterprise_context is None
    assert response.skill_trace is not None
    assert "company_id_not_found" in response.skill_trace.warnings


def test_low_data_readiness_adds_fallback_reason_only_when_company_present() -> None:
    solution_a, _solution_b = _solution_ids()
    service = _service(
        formal_candidates=[
            _candidate("DOC-001", "DOC-001#chunk-1", 0.8, 1, solution_a),
            _candidate("DOC-002", "DOC-002#chunk-1", 0.7, 2, solution_a),
        ]
    )

    response = service.generate_insight(
        SolutionInsightRequest(
            user_query="想建设售后知识检索",
            industry="Manufacturing",
            company_id="demo_manufacturing_001",
        )
    )

    assert "enterprise_context_data_readiness_low" in response.fallback_reasons
