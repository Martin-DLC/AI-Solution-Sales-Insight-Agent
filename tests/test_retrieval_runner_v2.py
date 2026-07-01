from __future__ import annotations

from datetime import date

from evaluation.retrieval.runner_v2 import (
    aggregate_summary_metrics_v2,
    evaluate_retrieval_case_v2,
    make_runtime_input_v2,
    project_v2_chunks_to_legacy_runtime_inputs,
    project_v2_documents_to_legacy_runtime_inputs,
    run_retrieval_evaluation_v2,
    runtime_input_has_gold_leak,
    runtime_input_to_retriever_filters,
)
from evaluation.retrieval.contracts_v2 import RetrievalEvaluationCaseV2, RetrievalEvaluationGoldV2, RetrievalRuntimeContextV2
from evaluation.retrieval.models import RetrievalCandidate, RetrievalMethod, RetrievalRunResult
from knowledge_base.contracts_v2 import KnowledgeChunkV2, KnowledgeDocumentV2


class FakeRetriever:
    def __init__(self, candidates: list[RetrievalCandidate], debug: dict[str, object]) -> None:
        self._candidates = candidates
        self._debug = debug
        self.last_filters: dict[str, object] | None = None

    @property
    def last_retrieval_debug(self) -> dict[str, object]:
        return dict(self._debug)

    def retrieve(self, *, query: str, filters: dict[str, object], top_k: int) -> list[RetrievalCandidate]:
        self.last_filters = dict(filters)
        return list(self._candidates[:top_k])


def _document(
    *,
    document_id: str,
    applicable_solution_ids: list[str],
    scope_type: str,
    excluded_solution_ids: list[str] | None = None,
    document_type: str = "solution",
    industries: list[str] | None = None,
    tags: list[str] | None = None,
) -> KnowledgeDocumentV2:
    return KnowledgeDocumentV2(
        document_id=document_id,
        title=document_id,
        document_type=document_type,
        status="approved",
        version="1.0",
        owner="demo-owner",
        summary="synthetic summary",
        content="synthetic content that is long enough for a stable payload.",
        tags=tags or ["demo"],
        industries=industries or ["retail"],
        source_uri=f"synthetic://{document_id}",
        confidentiality="synthetic_demo",
        primary_solution_id=applicable_solution_ids[0] if scope_type != "global_policy" else None,
        applicable_solution_ids=applicable_solution_ids,
        excluded_solution_ids=excluded_solution_ids or [],
        scope_type=scope_type,
        scope_notes="demo",
    )


def _chunk(
    *,
    chunk_id: str,
    document_id: str,
    applicable_solution_ids: list[str],
    scope_type: str,
    excluded_solution_ids: list[str] | None = None,
    document_type: str = "solution",
    industries: list[str] | None = None,
    tags: list[str] | None = None,
) -> KnowledgeChunkV2:
    return KnowledgeChunkV2(
        chunk_id=chunk_id,
        document_id=document_id,
        document_type=document_type,
        chunk_index=0,
        content="synthetic chunk content",
        token_estimate=12,
        tags=tags or ["demo"],
        industries=industries or ["retail"],
        metadata={},
        citation_label=chunk_id,
        primary_solution_id=applicable_solution_ids[0] if scope_type != "global_policy" else None,
        applicable_solution_ids=applicable_solution_ids,
        excluded_solution_ids=excluded_solution_ids or [],
        scope_type=scope_type,
        scope_notes="demo",
    )


def _case() -> RetrievalEvaluationCaseV2:
    return RetrievalEvaluationCaseV2(
        retrieval_case_id="RET2-TEST",
        source_case_id="DEV-TEST",
        query_type="solution_discovery",
        query="需要一个合规检索方案",
        runtime_context=RetrievalRuntimeContextV2(
            operational_filters={},
            operational_solution_scope=["合规政策RAG检索助手"],
            allowed_document_types=["solution"],
            industries=["retail"],
            tags=["priority"],
            effective_on=date(2026, 6, 29),
        ),
        evaluation_gold=RetrievalEvaluationGoldV2(
            expected_relevant_document_ids=["DOC-001"],
            expected_relevant_chunk_ids=["DOC-001#chunk-001"],
            forbidden_document_ids=[],
            forbidden_solution_ids=["客服辅助回复方案"],
            minimum_relevant_hits=1,
        ),
        tags=["descriptive-tag"],
    )


def test_runtime_input_does_not_include_gold_fields() -> None:
    runtime_input = make_runtime_input_v2(case=_case(), top_k=5)
    filters = runtime_input_to_retriever_filters(runtime_input)

    assert runtime_input_has_gold_leak(runtime_input) is False
    assert "expected_relevant_document_ids" not in filters
    assert filters["tags"] == ["priority"]


def test_chunk_scope_is_used_before_document_scope() -> None:
    case = _case()
    document = _document(
        document_id="DOC-001",
        applicable_solution_ids=["合规政策RAG检索助手", "客服辅助回复方案"],
        scope_type="multi_solution",
    )
    chunk = _chunk(
        chunk_id="DOC-001#chunk-001",
        document_id="DOC-001",
        applicable_solution_ids=["合规政策RAG检索助手"],
        scope_type="solution_specific",
    )
    result = RetrievalRunResult(
        retrieval_case_id=case.retrieval_case_id,
        retrieval_method=RetrievalMethod.lexical_v1,
        retrieved_candidates=[
            RetrievalCandidate(
                rank=1,
                document_id="DOC-001",
                chunk_id="DOC-001#chunk-001",
                score=1.0,
                retrieval_method="lexical_v1",
                matched_terms=["合规"],
                metadata={},
                citation_label="c1",
                solution_ids=["合规政策RAG检索助手"],
            )
        ],
        latency_ms=1,
    )
    score, reasons = evaluate_retrieval_case_v2(
        case=case,
        result=result,
        documents_by_id={"DOC-001": document},
        chunks_by_id={"DOC-001#chunk-001": chunk},
    )

    assert score.solution_boundary_violation is False
    assert reasons == [[]]


def test_single_candidate_matching_document_and_chunk_counts_as_one_relevant_item() -> None:
    case = _case()
    document = _document(
        document_id="DOC-001",
        applicable_solution_ids=["合规政策RAG检索助手"],
        scope_type="solution_specific",
    )
    chunk = _chunk(
        chunk_id="DOC-001#chunk-001",
        document_id="DOC-001",
        applicable_solution_ids=["合规政策RAG检索助手"],
        scope_type="solution_specific",
    )
    result = RetrievalRunResult(
        retrieval_case_id=case.retrieval_case_id,
        retrieval_method=RetrievalMethod.lexical_v1,
        retrieved_candidates=[
            RetrievalCandidate(
                rank=1,
                document_id="DOC-001",
                chunk_id="DOC-001#chunk-001",
                score=1.0,
                retrieval_method="lexical_v1",
                matched_terms=["合规"],
                metadata={},
                citation_label="c1",
                solution_ids=["合规政策RAG检索助手"],
            )
        ],
        latency_ms=1,
    )

    score, _ = evaluate_retrieval_case_v2(
        case=case,
        result=result,
        documents_by_id={"DOC-001": document},
        chunks_by_id={"DOC-001#chunk-001": chunk},
    )

    assert score.recall_at_1 == 0.5
    assert score.recall_at_5 == 0.5


def test_summary_uses_macro_average_over_case_metrics() -> None:
    left = RetrievalRunResult(
        retrieval_case_id="RET2-A",
        retrieval_method=RetrievalMethod.lexical_v1,
        retrieved_candidates=[],
        latency_ms=1,
    )
    right = RetrievalRunResult(
        retrieval_case_id="RET2-B",
        retrieval_method=RetrievalMethod.lexical_v1,
        retrieved_candidates=[],
        latency_ms=1,
    )
    case_a = _case().model_copy(
        update={
            "retrieval_case_id": "RET2-A",
            "evaluation_gold": _case().evaluation_gold.model_copy(
                update={
                    "expected_relevant_document_ids": ["DOC-001"],
                    "expected_relevant_chunk_ids": [],
                }
            ),
        }
    )
    case_b = _case().model_copy(
        update={
            "retrieval_case_id": "RET2-B",
            "evaluation_gold": _case().evaluation_gold.model_copy(
                update={
                    "expected_relevant_document_ids": ["DOC-001", "DOC-002"],
                    "expected_relevant_chunk_ids": [],
                }
            ),
        }
    )
    score_a, _ = evaluate_retrieval_case_v2(case=case_a, result=left, documents_by_id={}, chunks_by_id={})
    score_b, _ = evaluate_retrieval_case_v2(case=case_b, result=right, documents_by_id={}, chunks_by_id={})

    summary = aggregate_summary_metrics_v2([score_a, score_b])

    assert score_a.recall_at_5 == 0.0
    assert score_b.recall_at_5 == 0.0
    assert summary.recall_at_5 == 0.0


def test_global_policy_candidate_is_not_automatic_boundary_violation() -> None:
    case = _case()
    document = _document(
        document_id="DOC-GLOBAL",
        applicable_solution_ids=[
            "合规政策RAG检索助手",
            "客户身份统一与数据集成方案",
            "商品知识库RAG方案",
            "客服辅助回复方案",
            "服务工单系统集成方案",
            "私有化大模型部署方案",
        ],
        scope_type="global_policy",
        document_type="commercial_rule",
    )
    chunk = _chunk(
        chunk_id="DOC-GLOBAL#chunk-001",
        document_id="DOC-GLOBAL",
        applicable_solution_ids=document.applicable_solution_ids,
        scope_type="global_policy",
        document_type="commercial_rule",
    )
    case = case.model_copy(
        update={
            "runtime_context": case.runtime_context.model_copy(update={"allowed_document_types": ["commercial_rule"]}),
            "evaluation_gold": case.evaluation_gold.model_copy(
                update={
                    "expected_relevant_document_ids": ["DOC-GLOBAL"],
                    "expected_relevant_chunk_ids": ["DOC-GLOBAL#chunk-001"],
                    "forbidden_solution_ids": ["客服辅助回复方案"],
                }
            ),
        }
    )
    result = RetrievalRunResult(
        retrieval_case_id=case.retrieval_case_id,
        retrieval_method=RetrievalMethod.lexical_v1,
        retrieved_candidates=[
            RetrievalCandidate(
                rank=1,
                document_id="DOC-GLOBAL",
                chunk_id="DOC-GLOBAL#chunk-001",
                score=1.0,
                retrieval_method="lexical_v1",
                matched_terms=["规则"],
                metadata={},
                citation_label="global",
                solution_ids=document.applicable_solution_ids,
            )
        ],
        latency_ms=1,
    )
    score, _ = evaluate_retrieval_case_v2(
        case=case,
        result=result,
        documents_by_id={"DOC-GLOBAL": document},
        chunks_by_id={"DOC-GLOBAL#chunk-001": chunk},
    )
    assert score.solution_boundary_violation is False


def test_runtime_tags_filter_is_forwarded_to_retriever() -> None:
    case = _case()
    document = _document(document_id="DOC-001", applicable_solution_ids=["合规政策RAG检索助手"], scope_type="solution_specific")
    chunk = _chunk(chunk_id="DOC-001#chunk-001", document_id="DOC-001", applicable_solution_ids=["合规政策RAG检索助手"], scope_type="solution_specific")
    retriever = FakeRetriever(
        candidates=[],
        debug={"query_tokens": ["合规"], "filtered_candidate_count": 0, "elapsed_ms": 0},
    )

    run_retrieval_evaluation_v2(
        cases=[case],
        retriever=retriever,
        method_id="lexical_v1",
        top_k=5,
        documents=[document],
        chunks=[chunk],
    )

    assert retriever.last_filters is not None
    assert retriever.last_filters["tags"] == ["priority"]
    assert "expected_relevant_document_ids" not in retriever.last_filters


def test_failure_taxonomy_v2_does_not_misreport_empty_query_for_vector() -> None:
    case = _case()
    document = _document(document_id="DOC-001", applicable_solution_ids=["合规政策RAG检索助手"], scope_type="solution_specific")
    chunk = _chunk(chunk_id="DOC-001#chunk-001", document_id="DOC-001", applicable_solution_ids=["合规政策RAG检索助手"], scope_type="solution_specific")
    candidate = RetrievalCandidate(
        rank=1,
        document_id="DOC-001",
        chunk_id="DOC-001#chunk-001",
        score=1.0,
        retrieval_method="vector_v1",
        matched_terms=[],
        metadata={},
        citation_label="c1",
        solution_ids=["合规政策RAG检索助手"],
    )
    retriever = FakeRetriever(
        candidates=[candidate],
        debug={"filtered_candidate_count": 1, "elapsed_ms": 1},
    )
    report = run_retrieval_evaluation_v2(
        cases=[case],
        retriever=retriever,
        method_id="vector_v1",
        top_k=5,
        documents=[document],
        chunks=[chunk],
    )

    assert "empty_query" not in report.case_results[0].failure_taxonomy


def test_projection_to_legacy_runtime_inputs_uses_v2_applicable_solution_ids() -> None:
    document = _document(document_id="DOC-001", applicable_solution_ids=["合规政策RAG检索助手"], scope_type="solution_specific")
    chunk = _chunk(chunk_id="DOC-001#chunk-001", document_id="DOC-001", applicable_solution_ids=["合规政策RAG检索助手"], scope_type="solution_specific")
    legacy_documents = project_v2_documents_to_legacy_runtime_inputs([document])
    legacy_chunks = project_v2_chunks_to_legacy_runtime_inputs([chunk])

    assert legacy_documents[0].solution_ids == ["合规政策RAG检索助手"]
    assert legacy_chunks[0].solution_ids == ["合规政策RAG检索助手"]
