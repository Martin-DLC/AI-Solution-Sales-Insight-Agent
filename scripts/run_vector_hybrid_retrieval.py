from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.retrieval.comparison import RetrievalMethodComparisonEntry, select_retrieval_method
from evaluation.retrieval.dataset import load_retrieval_evaluation_cases
from evaluation.retrieval.runner import (
    build_formal_case_results,
    build_formal_summary_payload,
    run_retrieval_evaluation,
)
from evaluation.retrieval.storage import (
    diff_json_objects_ignoring_paths,
    load_json_record,
    load_jsonl_records,
    write_many_atomic,
)
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
    get_embedding_dependency_versions,
    is_local_sentence_transformer_model_available,
)


LEXICAL_CONFIG_PATH = Path("data/evaluation/retrieval/lexical_baseline_config.v1.json")
LEXICAL_SUMMARY_PATH = Path("data/evaluation/retrieval/lexical_baseline_summary.v1.json")
VECTOR_CONFIG_PATH = Path("data/evaluation/retrieval/vector_baseline_config.v1.json")
HYBRID_CONFIG_PATH = Path("data/evaluation/retrieval/hybrid_baseline_config.v1.json")
VECTOR_RESULTS_PATH = Path("data/evaluation/retrieval/vector_baseline_results.v1.jsonl")
VECTOR_SUMMARY_PATH = Path("data/evaluation/retrieval/vector_baseline_summary.v1.json")
HYBRID_RESULTS_PATH = Path("data/evaluation/retrieval/hybrid_baseline_results.v1.jsonl")
HYBRID_SUMMARY_PATH = Path("data/evaluation/retrieval/hybrid_baseline_summary.v1.json")
COMPARISON_PATH = Path("data/evaluation/retrieval/retrieval_method_comparison.v1.json")
IGNORED_CHECK_SUFFIXES = {
    "latency_ms",
    "average_latency_ms",
    "corpus_embedding_build_ms",
    "generated_at",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan, validate, prepare, run, or check vector/hybrid retrieval.")
    parser.add_argument("--validate", action="store_true", help="Validate configs, data, and provider availability.")
    parser.add_argument("--fake-smoke", action="store_true", help="Run a deterministic fake smoke through vector and hybrid retrieval.")
    parser.add_argument("--prepare-model", action="store_true", help="Prepare the frozen local embedding model without running formal cases.")
    parser.add_argument("--run", action="store_true", help="Run the frozen vector and hybrid retrieval experiments.")
    parser.add_argument("--write", action="store_true", help="Write formal vector/hybrid result artifacts.")
    parser.add_argument("--check", action="store_true", help="Re-run vector/hybrid retrieval and compare with tracked artifacts.")
    parser.add_argument(
        "--allow-model-download",
        action="store_true",
        help="Allow the frozen embedding model to be downloaded when explicitly preparing it.",
    )
    args = parser.parse_args()

    active_modes = [args.validate, args.fake_smoke, args.prepare_model, args.run, args.check]
    if sum(bool(value) for value in active_modes) > 1:
        print("Choose only one of --validate, --fake-smoke, --prepare-model, --run, or --check.", file=sys.stderr)
        return 2
    if args.write and not args.run:
        print("--write must be used together with --run.", file=sys.stderr)
        return 2
    if args.allow_model_download and not args.prepare_model:
        print("--allow-model-download can only be used together with --prepare-model.", file=sys.stderr)
        return 2
    if args.prepare_model and args.run:
        print("--prepare-model cannot be combined with --run.", file=sys.stderr)
        return 2
    if args.check and any((args.validate, args.fake_smoke, args.prepare_model, args.run, args.write, args.allow_model_download)):
        print("--check cannot be combined with other modes.", file=sys.stderr)
        return 2

    context = _load_context()
    dependency_report = get_embedding_dependency_report()
    local_model_available = is_local_sentence_transformer_model_available(context["vector_config"].model_name_or_path)

    if args.validate:
        payload = {
            "mode": "validate",
            "knowledge_base_version": context["manifest"].knowledge_base_version,
            "document_count": len(context["documents"]),
            "chunk_count": len(context["chunks"]),
            "retrieval_case_count": len(context["cases"]),
            "vector_config": context["vector_config"].model_dump(mode="json"),
            "hybrid_config": context["hybrid_config"].model_dump(mode="json"),
            "dependency_report": dependency_report,
            "local_model_available": local_model_available,
            "cache_directory_safe": _is_safe_cache_directory(context["vector_config"].cache_directory),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.fake_smoke:
        return _run_fake_smoke(context=context)

    if args.prepare_model:
        provider = SentenceTransformerEmbeddingProvider(
            model_name_or_path=context["vector_config"].model_name_or_path,
            batch_size=context["vector_config"].batch_size,
            device=context["vector_config"].device,
            normalize_embeddings=context["vector_config"].normalize_embeddings,
            allow_model_download=args.allow_model_download,
            query_prefix=context["vector_config"].query_prefix,
            document_prefix=context["vector_config"].document_prefix,
        )
        if not args.allow_model_download and not local_model_available:
            print(
                "Local embedding model is unavailable. Re-run with --prepare-model --allow-model-download if you want to permit the frozen model download.",
                file=sys.stderr,
            )
            return 1
        summary = provider.prepare_model()
        summary["dependency_versions"] = get_embedding_dependency_versions()
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.check:
        missing = [path for path in _formal_output_paths() if not path.exists()]
        if missing:
            print("Formal vector/hybrid result files do not exist yet.", file=sys.stderr)
            return 1
        if not local_model_available:
            print("Local embedding model is unavailable for --check.", file=sys.stderr)
            return 1
        payload = _run_formal(context=context, write=False)
        differences = _compare_formal_artifacts(payload)
        if differences:
            for difference in differences:
                print(difference, file=sys.stderr)
            return 1
        print("Vector and hybrid retrieval artifacts are up to date.")
        return 0

    if args.run:
        if not local_model_available:
            print("Local embedding model is unavailable. Formal run does not permit implicit downloads.", file=sys.stderr)
            return 1
        payload = _run_formal(context=context, write=args.write)
        print(
            json.dumps(
                {
                    "mode": "run",
                    "vector_case_count": len(payload["vector_results"]),
                    "hybrid_case_count": len(payload["hybrid_results"]),
                    "selected_method": payload["comparison"]["selected_method"],
                    "selection_status": payload["comparison"]["selection_status"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0

    payload = {
        "mode": "plan",
        "lexical_baseline_metrics": context["lexical_summary"],
        "knowledge_document_count": len(context["documents"]),
        "chunk_count": len(context["chunks"]),
        "retrieval_case_count": len(context["cases"]),
        "demo_solution_count": len(context["demo_scope"].selected_solution_ids),
        "embedding_model": DEFAULT_EMBEDDING_MODEL,
        "query_prefix": DEFAULT_QUERY_PREFIX,
        "vector_config": context["vector_config"].model_dump(mode="json"),
        "hybrid_config": context["hybrid_config"].model_dump(mode="json"),
        "dependency_report": dependency_report,
        "local_model_available": local_model_available,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _load_context() -> dict[str, Any]:
    lexical_summary = json.loads(LEXICAL_SUMMARY_PATH.read_text(encoding="utf-8"))
    lexical_config = LexicalBaselineConfig.model_validate(json.loads(LEXICAL_CONFIG_PATH.read_text(encoding="utf-8")))
    vector_config = VectorBaselineConfig.model_validate(json.loads(VECTOR_CONFIG_PATH.read_text(encoding="utf-8")))
    hybrid_config = HybridBaselineConfig.model_validate(json.loads(HYBRID_CONFIG_PATH.read_text(encoding="utf-8")))
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")
    chunks = load_knowledge_chunks("data/knowledge_base/chunks.v1.jsonl")
    manifest = load_knowledge_manifest("data/knowledge_base/manifest.v1.json")
    demo_scope = load_demo_solution_scope("data/knowledge_base/demo_solution_scope.v1.json")
    cases = load_retrieval_evaluation_cases("data/evaluation/retrieval/retrieval_cases.v1.jsonl")
    return {
        "lexical_summary": lexical_summary,
        "lexical_config": lexical_config,
        "vector_config": vector_config,
        "hybrid_config": hybrid_config,
        "documents": documents,
        "chunks": chunks,
        "manifest": manifest,
        "demo_scope": demo_scope,
        "cases": cases,
    }


def _run_fake_smoke(*, context: dict[str, Any]) -> int:
    smoke_cases = context["cases"][:1]
    lexical_retriever = _build_lexical_retriever(
        lexical_config=context["lexical_config"],
        documents=context["documents"],
        chunks=context["chunks"],
    )

    with tempfile.TemporaryDirectory(prefix="vector_hybrid_smoke_") as temp_dir:
        fake_vector_config = context["vector_config"].model_copy(
            update={"cache_enabled": False, "cache_directory": "data/runtime/fake-smoke-cache"}
        )
        vector_retriever = ExactVectorRetriever(
            config=fake_vector_config,
            embedding_provider=FakeEmbeddingProvider(),
            project_root=Path(temp_dir),
        )
        vector_retriever.build_index(
            documents=context["documents"],
            chunks=context["chunks"],
            knowledge_base_version=context["manifest"].knowledge_base_version,
        )
        hybrid_retriever = ReciprocalRankFusionRetriever(
            config=context["hybrid_config"],
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
            top_k=context["hybrid_config"].output_top_k,
        )

    comparison = select_retrieval_method(
        [
            _to_comparison_entry(
                method_id="vector_v1",
                report=vector_report,
                failed_case_ids=[result.retrieval_case_id for result in vector_report.case_results if not result.passed_blocking_gate],
                runtime_dependencies=["fake_embedding_provider"],
            ),
            _to_comparison_entry(
                method_id="hybrid_v1",
                report=hybrid_report,
                failed_case_ids=[result.retrieval_case_id for result in hybrid_report.case_results if not result.passed_blocking_gate],
                runtime_dependencies=["weighted_bm25", "fake_embedding_provider"],
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


def _run_formal(*, context: dict[str, Any], write: bool) -> dict[str, Any]:
    provider = SentenceTransformerEmbeddingProvider(
        model_name_or_path=context["vector_config"].model_name_or_path,
        batch_size=context["vector_config"].batch_size,
        device=context["vector_config"].device,
        normalize_embeddings=context["vector_config"].normalize_embeddings,
        allow_model_download=False,
        query_prefix=context["vector_config"].query_prefix,
        document_prefix=context["vector_config"].document_prefix,
    )
    lexical_retriever = _build_lexical_retriever(
        lexical_config=context["lexical_config"],
        documents=context["documents"],
        chunks=context["chunks"],
    )
    vector_retriever = ExactVectorRetriever(
        config=context["vector_config"],
        embedding_provider=provider,
        project_root=PROJECT_ROOT,
    )
    vector_retriever.build_index(
        documents=context["documents"],
        chunks=context["chunks"],
        knowledge_base_version=context["manifest"].knowledge_base_version,
    )
    hybrid_retriever = ReciprocalRankFusionRetriever(
        config=context["hybrid_config"],
        lexical_retriever=lexical_retriever,
        vector_retriever=vector_retriever,
    )

    vector_report = run_retrieval_evaluation(
        cases=context["cases"],
        retriever=vector_retriever,
        method_id="vector_v1",
        top_k=context["vector_config"].top_k,
    )
    hybrid_report = run_retrieval_evaluation(
        cases=context["cases"],
        retriever=hybrid_retriever,
        method_id="hybrid_v1",
        top_k=context["hybrid_config"].output_top_k,
    )

    dependency_versions = get_embedding_dependency_versions()
    vector_results = [result.model_dump(mode="json") for result in build_formal_case_results(vector_report)]
    hybrid_results = [result.model_dump(mode="json") for result in build_formal_case_results(hybrid_report)]
    vector_summary = build_formal_summary_payload(
        cases=context["cases"],
        config=context["vector_config"],
        config_file="data/evaluation/retrieval/vector_baseline_config.v1.json",
        manifest=context["manifest"],
        demo_scope=context["demo_scope"],
        report=vector_report,
        model_name=provider.model_name,
        resolved_model_revision=provider.resolved_revision,
        embedding_dimension=provider.dimension,
        dependency_versions=dependency_versions,
        corpus_embedding_count=vector_retriever.corpus_embedding_count,
        cache_hit_count=vector_retriever.cache_hit_count,
        cache_miss_count=vector_retriever.cache_miss_count,
        corpus_embedding_build_ms=vector_retriever.corpus_embedding_build_ms,
        limitations=[
            "This benchmark uses the 6-solution synthetic demo scope only.",
            "No reranker, FAISS, or vector database is included in vector_v1.",
        ],
    ).model_dump(mode="json")
    hybrid_summary = build_formal_summary_payload(
        cases=context["cases"],
        config=context["hybrid_config"],
        config_file="data/evaluation/retrieval/hybrid_baseline_config.v1.json",
        manifest=context["manifest"],
        demo_scope=context["demo_scope"],
        report=hybrid_report,
        model_name=provider.model_name,
        resolved_model_revision=provider.resolved_revision,
        embedding_dimension=provider.dimension,
        dependency_versions=dependency_versions,
        corpus_embedding_count=vector_retriever.corpus_embedding_count,
        cache_hit_count=vector_retriever.cache_hit_count,
        cache_miss_count=vector_retriever.cache_miss_count,
        corpus_embedding_build_ms=vector_retriever.corpus_embedding_build_ms,
        limitations=[
            "Hybrid_v1 uses frozen weighted BM25 plus frozen dense cosine retrieval.",
            "Hybrid_v1 does not rerank or relax the frozen blocking gate.",
        ],
    ).model_dump(mode="json")
    comparison = select_retrieval_method(
        [
            _lexical_entry(context["lexical_summary"]),
            _to_comparison_entry(
                method_id="vector_v1",
                report=vector_report,
                failed_case_ids=vector_summary["failed_case_ids"],
                runtime_dependencies=["sentence_transformers", "torch", "transformers", "numpy"],
            ),
            _to_comparison_entry(
                method_id="hybrid_v1",
                report=hybrid_report,
                failed_case_ids=hybrid_summary["failed_case_ids"],
                runtime_dependencies=["weighted_bm25", "sentence_transformers", "torch", "transformers", "numpy"],
            ),
        ]
    ).model_dump(mode="json")

    payload = {
        "vector_results": vector_results,
        "vector_summary": vector_summary,
        "hybrid_results": hybrid_results,
        "hybrid_summary": hybrid_summary,
        "comparison": comparison,
    }
    if write:
        write_many_atomic(
            [
                (VECTOR_RESULTS_PATH, _to_jsonl(vector_results)),
                (VECTOR_SUMMARY_PATH, _to_json(vector_summary)),
                (HYBRID_RESULTS_PATH, _to_jsonl(hybrid_results)),
                (HYBRID_SUMMARY_PATH, _to_json(hybrid_summary)),
                (COMPARISON_PATH, _to_json(comparison)),
            ]
        )
    return payload


def _compare_formal_artifacts(payload: dict[str, Any]) -> list[str]:
    tracked_objects = {
        "vector_results": load_jsonl_records(VECTOR_RESULTS_PATH),
        "vector_summary": load_json_record(VECTOR_SUMMARY_PATH),
        "hybrid_results": load_jsonl_records(HYBRID_RESULTS_PATH),
        "hybrid_summary": load_json_record(HYBRID_SUMMARY_PATH),
        "comparison": load_json_record(COMPARISON_PATH),
    }
    differences: list[str] = []
    for label, current in payload.items():
        tracked = tracked_objects[label]
        if isinstance(tracked, list):
            if len(tracked) != len(current):
                differences.append(f"{label}:length")
                continue
            for tracked_item, current_item in zip(tracked, current):
                item_id = current_item.get("retrieval_case_id", label)
                for path in diff_json_objects_ignoring_paths(tracked_item, current_item, ignored_suffixes=IGNORED_CHECK_SUFFIXES):
                    differences.append(f"{item_id}:{path}")
            continue
        for path in diff_json_objects_ignoring_paths(tracked, current, ignored_suffixes=IGNORED_CHECK_SUFFIXES):
            differences.append(f"{label}:{path}")
    return differences


def _build_lexical_retriever(*, lexical_config: LexicalBaselineConfig, documents, chunks):
    from knowledge_base.retrieval import WeightedBM25Retriever

    retriever = WeightedBM25Retriever(config=lexical_config)
    retriever.build_index(documents=documents, chunks=chunks)
    return retriever


def _lexical_entry(summary: dict[str, Any]) -> RetrievalMethodComparisonEntry:
    return RetrievalMethodComparisonEntry(
        retrieval_method="lexical_v1",
        case_count=summary["case_count"],
        recall_at_1=summary["recall_at_1"],
        recall_at_3=summary["recall_at_3"],
        recall_at_5=summary["recall_at_5"],
        precision_at_3=summary["precision_at_3"],
        precision_at_5=summary["precision_at_5"],
        mean_reciprocal_rank=summary["mean_reciprocal_rank"],
        forbidden_hit_rate=summary["forbidden_hit_rate"],
        solution_boundary_violation_rate=summary["solution_boundary_violation_rate"],
        average_latency_ms=summary["average_latency_ms"],
        eligible_for_rag=summary["eligible_for_rag"],
        disqualification_reasons=list(summary["disqualification_reasons"]),
        failed_case_ids=list(summary["failed_case_ids"]),
        implementation_complexity="low",
        runtime_dependencies=["weighted_bm25"],
    )


def _to_comparison_entry(
    *,
    method_id: str,
    report,
    failed_case_ids: list[str],
    runtime_dependencies: list[str],
) -> RetrievalMethodComparisonEntry:
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
        implementation_complexity="medium" if method_id == "vector_v1" else "medium_high",
        runtime_dependencies=runtime_dependencies,
    )


def _formal_output_paths() -> list[Path]:
    return [
        VECTOR_RESULTS_PATH,
        VECTOR_SUMMARY_PATH,
        HYBRID_RESULTS_PATH,
        HYBRID_SUMMARY_PATH,
        COMPARISON_PATH,
    ]


def _to_jsonl(records: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for record in records) + "\n"


def _to_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _is_safe_cache_directory(value: str) -> bool:
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and path.parts[:2] == ("data", "runtime")


if __name__ == "__main__":
    raise SystemExit(main())
