from __future__ import annotations

import json
from pathlib import Path

from evaluation.retrieval.dataset import load_retrieval_evaluation_cases
from evaluation.retrieval.runner import build_summary_payload, run_retrieval_evaluation
from knowledge_base.dataset import (
    load_demo_solution_scope,
    load_knowledge_chunks,
    load_knowledge_documents,
    load_knowledge_manifest,
)
from knowledge_base.retrieval.lexical import LexicalBaselineConfig, WeightedBM25Retriever


def _config() -> LexicalBaselineConfig:
    return LexicalBaselineConfig.model_validate(
        json.loads(Path("data/evaluation/retrieval/lexical_baseline_config.v1.json").read_text(encoding="utf-8"))
    )


def _report():
    retriever = WeightedBM25Retriever(config=_config())
    retriever.build_index(
        documents=load_knowledge_documents("data/knowledge_base/documents.v1.jsonl"),
        chunks=load_knowledge_chunks("data/knowledge_base/chunks.v1.jsonl"),
    )
    cases = load_retrieval_evaluation_cases("data/evaluation/retrieval/retrieval_cases.v1.jsonl")
    report = run_retrieval_evaluation(
        cases=cases,
        retriever=retriever,
        method_id="lexical_v1",
        top_k=5,
    )
    return cases, report


def test_runner_preserves_case_order_and_generates_case_results() -> None:
    cases, report = _report()

    assert [result.retrieval_case_id for result in report.case_results] == [
        case.retrieval_case_id for case in cases
    ]
    assert len(report.case_results) == 16


def test_runner_summary_payload_is_safe_and_relative() -> None:
    cases, report = _report()
    summary = build_summary_payload(
        cases=cases,
        config=_config(),
        manifest=load_knowledge_manifest("data/knowledge_base/manifest.v1.json"),
        demo_scope=load_demo_solution_scope("data/knowledge_base/demo_solution_scope.v1.json"),
        report=report,
    )

    assert summary["config_file"] == "data/evaluation/retrieval/lexical_baseline_config.v1.json"
    assert summary["generated_from_synthetic_data"] is True
    assert "/Users/" not in json.dumps(summary, ensure_ascii=False)


def test_runner_marks_empty_query_tokens_as_failure_reason() -> None:
    retriever = WeightedBM25Retriever(config=_config())
    retriever.build_index(
        documents=load_knowledge_documents("data/knowledge_base/documents.v1.jsonl"),
        chunks=load_knowledge_chunks("data/knowledge_base/chunks.v1.jsonl"),
    )
    case = load_retrieval_evaluation_cases("data/evaluation/retrieval/retrieval_cases.v1.jsonl")[0]
    case = case.model_copy(update={"query": "   "})
    report = run_retrieval_evaluation(
        cases=[case],
        retriever=retriever,
        method_id="lexical_v1",
        top_k=5,
    )

    assert report.case_results[0].passed_blocking_gate is False
    assert "empty_query_tokens" in report.case_results[0].failure_reasons
