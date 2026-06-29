from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.retrieval.comparison import RetrievalMethodComparisonEntry, select_retrieval_method
from evaluation.retrieval.dataset import load_retrieval_evaluation_cases
from evaluation.retrieval.runner import run_retrieval_evaluation
from knowledge_base.dataset import (
    load_demo_solution_scope,
    load_knowledge_chunks,
    load_knowledge_documents,
    load_knowledge_manifest,
)
from knowledge_base.retrieval import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_QUERY_PREFIX,
    ExactVectorRetriever,
    FakeEmbeddingProvider,
    HybridBaselineConfig,
    LexicalBaselineConfig,
    ReciprocalRankFusionRetriever,
    SentenceTransformerEmbeddingProvider,
    VectorBaselineConfig,
    get_embedding_dependency_report,
    is_local_sentence_transformer_model_available,
)


LEXICAL_CONFIG_PATH = Path("data/evaluation/retrieval/lexical_baseline_config.v1.json")
LEXICAL_SUMMARY_PATH = Path("data/evaluation/retrieval/lexical_baseline_summary.v1.json")
VECTOR_CONFIG_PATH = Path("data/evaluation/retrieval/vector_baseline_config.v1.json")
HYBRID_CONFIG_PATH = Path("data/evaluation/retrieval/hybrid_baseline_config.v1.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan or validate the vector/hybrid retrieval foundation.")
    parser.add_argument("--validate", action="store_true", help="Validate configs, data, and provider availability.")
    parser.add_argument("--fake-smoke", action="store_true", help="Run a deterministic fake smoke through vector and hybrid retrieval.")
    parser.add_argument("--run", action="store_true", help="Reserved for v1.2D2 formal vector/hybrid experiments.")
    parser.add_argument("--write", action="store_true", help="Reserved for v1.2D2 tracked artifact writes.")
    parser.add_argument(
        "--allow-model-download",
        action="store_true",
        help="Allow sentence-transformers to download a missing local model when --run is explicitly used.",
    )
    args = parser.parse_args()

    if sum(bool(flag) for flag in (args.validate, args.fake_smoke, args.run)) > 1:
        print("Choose only one of --validate, --fake-smoke, or --run.", file=sys.stderr)
        return 2
    if args.write and not args.run:
        print("--write must be used together with --run.", file=sys.stderr)
        return 2
    if args.allow_model_download and not args.run:
        print("--allow-model-download must be used together with --run.", file=sys.stderr)
        return 2

    lexical_summary = json.loads(LEXICAL_SUMMARY_PATH.read_text(encoding="utf-8"))
    lexical_config = LexicalBaselineConfig.model_validate(json.loads(LEXICAL_CONFIG_PATH.read_text(encoding="utf-8")))
    vector_config = VectorBaselineConfig.model_validate(json.loads(VECTOR_CONFIG_PATH.read_text(encoding="utf-8")))
    hybrid_config = HybridBaselineConfig.model_validate(json.loads(HYBRID_CONFIG_PATH.read_text(encoding="utf-8")))
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")
    chunks = load_knowledge_chunks("data/knowledge_base/chunks.v1.jsonl")
    manifest = load_knowledge_manifest("data/knowledge_base/manifest.v1.json")
    demo_scope = load_demo_solution_scope("data/knowledge_base/demo_solution_scope.v1.json")
    cases = load_retrieval_evaluation_cases("data/evaluation/retrieval/retrieval_cases.v1.jsonl")
    dependency_report = get_embedding_dependency_report()
    local_model_available = is_local_sentence_transformer_model_available(vector_config.model_name_or_path)

    if args.validate:
        payload = {
            "mode": "validate",
            "knowledge_base_version": manifest.knowledge_base_version,
            "document_count": len(documents),
            "chunk_count": len(chunks),
            "retrieval_case_count": len(cases),
            "vector_config": vector_config.model_dump(mode="json"),
            "hybrid_config": hybrid_config.model_dump(mode="json"),
            "dependency_report": dependency_report,
            "local_model_available": local_model_available,
            "cache_directory_safe": _is_safe_cache_directory(vector_config.cache_directory),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.fake_smoke:
        return _run_fake_smoke(
            lexical_config=lexical_config,
            vector_config=vector_config,
            hybrid_config=hybrid_config,
            documents=documents,
            chunks=chunks,
            cases=cases,
            knowledge_base_version=manifest.knowledge_base_version,
        )

    if args.run:
        if not local_model_available and not args.allow_model_download:
            print(
                "Local embedding model is unavailable. Re-run with --allow-model-download if you want to permit a first download.",
                file=sys.stderr,
            )
            return 1
        print("Formal vector/hybrid retrieval execution is reserved for v1.2D2.", file=sys.stderr)
        return 2

    payload = {
        "mode": "plan",
        "lexical_baseline_metrics": lexical_summary,
        "knowledge_document_count": len(documents),
        "chunk_count": len(chunks),
        "retrieval_case_count": len(cases),
        "demo_solution_count": len(demo_scope.selected_solution_ids),
        "embedding_model": DEFAULT_EMBEDDING_MODEL,
        "query_prefix": DEFAULT_QUERY_PREFIX,
        "vector_config": vector_config.model_dump(mode="json"),
        "hybrid_config": hybrid_config.model_dump(mode="json"),
        "dependency_report": dependency_report,
        "local_model_available": local_model_available,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _run_fake_smoke(
    *,
    lexical_config: LexicalBaselineConfig,
    vector_config: VectorBaselineConfig,
    hybrid_config: HybridBaselineConfig,
    documents,
    chunks,
    cases,
    knowledge_base_version: str,
) -> int:
    smoke_cases = cases[:1]
    lexical_retriever = _build_lexical_retriever(lexical_config=lexical_config, documents=documents, chunks=chunks)

    with tempfile.TemporaryDirectory(prefix="vector_hybrid_smoke_") as temp_dir:
        fake_vector_config = vector_config.model_copy(
            update={
                "cache_enabled": False,
                "cache_directory": str(Path(temp_dir).name),
            }
        )
        vector_retriever = ExactVectorRetriever(
            config=fake_vector_config,
            embedding_provider=FakeEmbeddingProvider(),
            project_root=Path(temp_dir).parent,
        )
        vector_retriever.build_index(
            documents=documents,
            chunks=chunks,
            knowledge_base_version=knowledge_base_version,
        )
        hybrid_retriever = ReciprocalRankFusionRetriever(
            config=hybrid_config,
            lexical_retriever=lexical_retriever,
            vector_retriever=vector_retriever,
        )

        vector_report = run_retrieval_evaluation(
            cases=smoke_cases,
            retriever=vector_retriever,
            method_id="vector_v1",
            top_k=fake_vector_config.top_k,
        )
        hybrid_report = run_retrieval_evaluation(
            cases=smoke_cases,
            retriever=hybrid_retriever,
            method_id="hybrid_v1",
            top_k=hybrid_config.output_top_k,
        )

    comparison = select_retrieval_method(
        [
            _to_comparison_entry(
                method_id="vector_v1",
                report=vector_report,
                failed_case_ids=[result.retrieval_case_id for result in vector_report.case_results if not result.passed_blocking_gate],
            ),
            _to_comparison_entry(
                method_id="hybrid_v1",
                report=hybrid_report,
                failed_case_ids=[result.retrieval_case_id for result in hybrid_report.case_results if not result.passed_blocking_gate],
            ),
        ]
    )
    payload = {
        "mode": "fake_smoke",
        "vector_case_count": len(vector_report.case_results),
        "hybrid_case_count": len(hybrid_report.case_results),
        "selected_method": comparison.selected_method.value if comparison.selected_method else None,
        "selection_status": comparison.selection_status,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def _build_lexical_retriever(*, lexical_config: LexicalBaselineConfig, documents, chunks):
    from knowledge_base.retrieval import WeightedBM25Retriever

    retriever = WeightedBM25Retriever(config=lexical_config)
    retriever.build_index(documents=documents, chunks=chunks)
    return retriever


def _to_comparison_entry(*, method_id: str, report, failed_case_ids: list[str]) -> RetrievalMethodComparisonEntry:
    summary = report.summary
    return RetrievalMethodComparisonEntry(
        retrieval_method=method_id,
        case_count=summary.case_count,
        recall_at_1=summary.recall_at_1,
        recall_at_3=summary.recall_at_3,
        recall_at_5=summary.recall_at_5,
        precision_at_3=summary.precision_at_3,
        precision_at_5=summary.precision_at_5,
        mean_reciprocal_rank=summary.mean_reciprocal_rank,
        forbidden_hit_rate=summary.forbidden_hit_rate,
        solution_boundary_violation_rate=summary.solution_boundary_violation_rate,
        average_latency_ms=summary.average_latency_ms,
        eligible_for_rag=summary.eligible_for_rag,
        disqualification_reasons=list(summary.disqualification_reasons),
        failed_case_ids=failed_case_ids,
    )


def _is_safe_cache_directory(value: str) -> bool:
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and path.parts[:2] == ("data", "runtime")


if __name__ == "__main__":
    raise SystemExit(main())
