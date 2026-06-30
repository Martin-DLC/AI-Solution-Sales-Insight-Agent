from __future__ import annotations

import argparse
import json
import socket
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.retrieval import RetrievalMethodComparisonEntry
from evaluation.retrieval.comparison_v2 import select_retrieval_method_v2
from evaluation.retrieval.contracts_v2 import RetrievalEvaluationCaseV2
from evaluation.retrieval.runner_v2 import (
    RetrievalFormalCaseResultV2,
    RetrievalFormalSummaryV2,
    build_formal_case_results_v2,
    build_formal_summary_v2,
    project_v2_chunks_to_legacy_runtime_inputs,
    project_v2_documents_to_legacy_runtime_inputs,
    recompute_summary_metrics_from_formal_results_v2,
    run_retrieval_evaluation_v2,
)
from evaluation.retrieval.storage_v2 import (
    NON_DETERMINISTIC_RESULT_FIELDS_V2,
    compare_payloads_ignoring_runtime_fields,
    compute_file_sha256,
    formal_v2_missing_outputs,
    formal_v2_output_paths,
    formal_v2_results_exist,
    load_json_record,
    load_jsonl_records,
    publish_staged_formal_v2_outputs,
    remove_formal_v2_stage_dir,
    stage_formal_v2_outputs,
    write_attempt_metadata,
)
from knowledge_base import KnowledgeChunkV2, KnowledgeDocumentV2
from knowledge_base.retrieval import (
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
from knowledge_base.retrieval.embeddings import huggingface_offline_environment
from knowledge_base.retrieval.lexical import WeightedBM25Retriever


LEXICAL_CONFIG_V1_PATH = Path("data/evaluation/retrieval/lexical_baseline_config.v1.json")
VECTOR_CONFIG_V1_PATH = Path("data/evaluation/retrieval/vector_baseline_config.v1.json")
HYBRID_CONFIG_V1_PATH = Path("data/evaluation/retrieval/hybrid_baseline_config.v1.json")
LEXICAL_CONFIG_V2_PATH = Path("data/evaluation/retrieval/lexical_baseline_config.v2.json")
VECTOR_CONFIG_V2_PATH = Path("data/evaluation/retrieval/vector_baseline_config.v2.json")
HYBRID_CONFIG_V2_PATH = Path("data/evaluation/retrieval/hybrid_baseline_config.v2.json")
BENCHMARK_CONFIG_V2_PATH = Path("data/evaluation/retrieval/retrieval_benchmark_config.v2.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan, validate, smoke, readiness check, or formally run Retrieval Benchmark v2.")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--fake-smoke", action="store_true")
    parser.add_argument("--offline-model-smoke", action="store_true")
    parser.add_argument("--formal-readiness", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    modes = [args.validate, args.fake_smoke, args.offline_model_smoke, args.formal_readiness, args.run, args.check]
    if sum(bool(item) for item in modes) > 1:
        print(
            "Choose only one of --validate, --fake-smoke, --offline-model-smoke, --formal-readiness, --run, or --check.",
            file=sys.stderr,
        )
        return 2
    if args.write and not args.run:
        print("--write must be used together with --run.", file=sys.stderr)
        return 2
    if args.run and not args.write:
        print("Formal Retrieval Benchmark v2 requires the fixed command: --run --write.", file=sys.stderr)
        return 2

    if args.validate:
        print(json.dumps(build_validate_payload(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.fake_smoke:
        print(json.dumps(run_fake_smoke(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.offline_model_smoke:
        print(json.dumps(run_offline_model_smoke(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.formal_readiness:
        print(json.dumps(build_formal_readiness_payload(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.check:
        payload, ok = build_check_payload()
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if ok else 1
    if args.run:
        payload = run_formal_write()
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    print(json.dumps(build_plan_payload(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_plan_payload() -> dict[str, Any]:
    benchmark_config = load_json_record(BENCHMARK_CONFIG_V2_PATH)
    method_configs = _load_method_configs()
    return {
        "mode": "plan",
        "benchmark_version": benchmark_config["benchmark_version"],
        "document_count": benchmark_config["document_count"],
        "chunk_count": benchmark_config["chunk_count"],
        "case_count": benchmark_config["case_count"],
        "demo_solution_count": benchmark_config["demo_solution_count"],
        "retrieval_contract_version": benchmark_config["retrieval_contract_version"],
        "failure_taxonomy_version": benchmark_config["failure_taxonomy_version"],
        "boundary_contract_version": benchmark_config["boundary_contract_version"],
        "method_config_ids": [config["method_config_id"] for config in method_configs.values()],
        "formal_output_paths": {name: str(path) for name, path in formal_v2_output_paths().items()},
        "formal_results_exist": formal_v2_results_exist(),
    }


def build_validate_payload() -> dict[str, Any]:
    benchmark_config = load_json_record(BENCHMARK_CONFIG_V2_PATH)
    method_configs = _load_method_configs()
    _validate_method_configs_against_v1(method_configs)
    documents = _load_documents_v2()
    chunks = _load_chunks_v2()
    cases = _load_cases_v2()
    feasibility = load_json_record(Path(benchmark_config["feasibility_file"]))
    if feasibility["summary"]["infeasible_case_count"] != 0:
        raise ValueError("Retrieval Benchmark v2 validate requires all 16 cases to be feasible.")
    if formal_v2_results_exist():
        raise ValueError("Formal v2 result files already exist; validate expects them to be absent before the first formal run.")
    return {
        "mode": "validate",
        "benchmark_config_hash": compute_file_sha256(BENCHMARK_CONFIG_V2_PATH),
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "case_count": len(cases),
        "feasible_case_count": feasibility["summary"]["feasible_case_count"],
        "formal_results_exist": False,
        "dependency_report": get_embedding_dependency_report(),
        "method_configs": {
            name: {
                "method_config_id": config["method_config_id"],
                "source_v1_config_hash": config["source_v1_config_hash"],
                "retrieval_method": config["retrieval_method"],
            }
            for name, config in method_configs.items()
        },
    }


def build_formal_readiness_payload() -> dict[str, Any]:
    validate_payload = build_validate_payload()
    vector_config = _load_vector_config()
    runtime_root = Path("data/runtime/retrieval_benchmark_v2_attempts")
    cache_dir = PROJECT_ROOT / vector_config.cache_directory
    snapshot_available = is_local_sentence_transformer_model_available(
        vector_config.model_name_or_path,
        revision=vector_config.model_revision,
    )
    runtime_root.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    ready = (
        validate_payload["formal_results_exist"] is False
        and validate_payload["case_count"] == 16
        and validate_payload["document_count"] == 20
        and validate_payload["chunk_count"] == 40
        and validate_payload["feasible_case_count"] == 16
        and snapshot_available
        and _network_is_blocked()
        and _directory_writable(runtime_root)
        and _directory_writable(cache_dir)
    )
    return {
        "mode": "formal_readiness",
        "ready_for_single_formal_run": ready,
        "formal_results_exist": False,
        "network_blocked": _network_is_blocked(),
        "local_snapshot_available": snapshot_available,
        "runtime_directory_writable": _directory_writable(runtime_root),
        "cache_directory_writable": _directory_writable(cache_dir),
        "benchmark_config_hash": validate_payload["benchmark_config_hash"],
        "method_config_hashes": {name: compute_file_sha256(path) for name, path in _method_config_paths().items()},
        "document_count": validate_payload["document_count"],
        "chunk_count": validate_payload["chunk_count"],
        "case_count": validate_payload["case_count"],
        "feasible_case_count": validate_payload["feasible_case_count"],
        "vector_model_name": vector_config.model_name_or_path,
        "vector_model_revision": vector_config.model_revision,
        "embedding_dimension": 384,
    }


def run_fake_smoke() -> dict[str, Any]:
    method_configs = _load_method_configs()
    benchmark_config = load_json_record(BENCHMARK_CONFIG_V2_PATH)
    documents_v2 = _load_documents_v2()
    chunks_v2 = _load_chunks_v2()
    cases = _load_cases_v2()[:2]

    lexical_config = LexicalBaselineConfig.model_validate(method_configs["lexical"]["algorithm_config"])
    vector_config = VectorBaselineConfig.model_validate(
        {**method_configs["vector"]["algorithm_config"], "cache_enabled": False, "cache_directory": "data/runtime/fake-v2-cache"}
    )
    hybrid_config = HybridBaselineConfig.model_validate(method_configs["hybrid"]["algorithm_config"])

    documents_v1 = project_v2_documents_to_legacy_runtime_inputs(documents_v2)
    chunks_v1 = project_v2_chunks_to_legacy_runtime_inputs(chunks_v2)
    lexical = WeightedBM25Retriever(config=lexical_config)
    lexical.build_index(documents=documents_v1, chunks=chunks_v1)

    with tempfile.TemporaryDirectory(prefix="retrieval_v2_fake_smoke_") as temp_dir:
        vector = ExactVectorRetriever(
            config=vector_config,
            embedding_provider=FakeEmbeddingProvider(),
            project_root=Path(temp_dir),
        )
        vector.build_index(
            documents=documents_v1,
            chunks=chunks_v1,
            knowledge_base_version=load_json_record(Path(benchmark_config["manifest_file"]))["knowledge_base_version"],
        )
        hybrid = ReciprocalRankFusionRetriever(
            config=hybrid_config,
            lexical_retriever=lexical,
            vector_retriever=vector,
        )
        lexical_report = run_retrieval_evaluation_v2(
            cases=cases,
            retriever=lexical,
            method_id="lexical_v1",
            top_k=lexical_config.top_k,
            documents=documents_v2,
            chunks=chunks_v2,
        )
        vector_report = run_retrieval_evaluation_v2(
            cases=cases,
            retriever=vector,
            method_id="vector_v1",
            top_k=vector_config.top_k,
            documents=documents_v2,
            chunks=chunks_v2,
        )
        hybrid_report = run_retrieval_evaluation_v2(
            cases=cases,
            retriever=hybrid,
            method_id="hybrid_v1",
            top_k=hybrid_config.output_top_k,
            documents=documents_v2,
            chunks=chunks_v2,
        )

    comparison = select_retrieval_method_v2(
        benchmark_version=benchmark_config["benchmark_version"],
        entries=[
            _comparison_entry("lexical_v1", lexical_report),
            _comparison_entry("vector_v1", vector_report),
            _comparison_entry("hybrid_v1", hybrid_report),
        ],
        benchmark_config_hash=compute_file_sha256(BENCHMARK_CONFIG_V2_PATH),
        method_config_hashes={name: compute_file_sha256(path) for name, path in _method_config_paths().items()},
        retrieval_contract_version=benchmark_config["retrieval_contract_version"],
        failure_taxonomy_version=benchmark_config["failure_taxonomy_version"],
        boundary_contract_version=benchmark_config["boundary_contract_version"],
    )
    return {
        "mode": "fake_smoke",
        "case_count": len(cases),
        "reports": {
            "lexical": _report_summary(lexical_report),
            "vector": _report_summary(vector_report),
            "hybrid": _report_summary(hybrid_report),
        },
        "comparison": comparison.model_dump(mode="json"),
        "network_access_attempted": False,
    }


def run_offline_model_smoke() -> dict[str, Any]:
    method_configs = _load_method_configs()
    vector_config = VectorBaselineConfig.model_validate(method_configs["vector"]["algorithm_config"])
    local_available = is_local_sentence_transformer_model_available(
        vector_config.model_name_or_path,
        revision=vector_config.model_revision,
    )
    if not local_available:
        return {
            "mode": "offline_model_smoke",
            "local_model_available": False,
            "status": "local_model_unavailable",
        }
    with huggingface_offline_environment():
        provider = SentenceTransformerEmbeddingProvider(
            model_name_or_path=vector_config.model_name_or_path,
            batch_size=vector_config.batch_size,
            device=vector_config.device,
            normalize_embeddings=vector_config.normalize_embeddings,
            allow_model_download=False,
            query_prefix=vector_config.query_prefix,
            document_prefix=vector_config.document_prefix,
            expected_dimension=384,
            expected_revision=vector_config.model_revision,
        )
        query_vectors = provider.encode_queries(["synthetic v2 query probe"])
        document_vectors = provider.encode_documents(["synthetic v2 document probe"])
    return {
        "mode": "offline_model_smoke",
        "local_model_available": True,
        "embedding_dimension": provider.dimension,
        "resolved_model_revision": provider.resolved_revision,
        "query_prefix": vector_config.query_prefix,
        "document_prefix": vector_config.document_prefix,
        "query_probe_count": len(query_vectors),
        "document_probe_count": len(document_vectors),
        "network_access_attempted": False,
    }


def build_check_payload() -> tuple[dict[str, Any], bool]:
    validate_payload = build_validate_payload()
    if not formal_v2_results_exist():
        return (
            {
                "mode": "check",
                "status": "formal_results_not_generated",
                "formal_output_paths": {name: str(path) for name, path in formal_v2_output_paths().items()},
                "formal_results_exist": False,
                "non_deterministic_result_fields": sorted(NON_DETERMINISTIC_RESULT_FIELDS_V2),
                "validate": validate_payload,
            },
            True,
        )

    generated_payloads = build_formal_payloads()
    actual_payloads = _load_formal_result_payloads()
    differences = _compare_formal_payload_maps(expected=generated_payloads, actual=actual_payloads)
    ok = not differences
    return (
        {
            "mode": "check",
            "status": "formal_results_match" if ok else "formal_results_mismatch",
            "formal_results_exist": True,
            "formal_output_paths": {name: str(path) for name, path in formal_v2_output_paths().items()},
            "non_deterministic_result_fields": sorted(NON_DETERMINISTIC_RESULT_FIELDS_V2),
            "validate": validate_payload,
            "differences": differences,
        },
        ok,
    )


def run_formal_write() -> dict[str, Any]:
    readiness = build_formal_readiness_payload()
    if not readiness["ready_for_single_formal_run"]:
        raise RuntimeError("Formal readiness check failed; refusing to execute --run --write.")
    output_paths = formal_v2_output_paths()
    if formal_v2_results_exist():
        raise FileExistsError("Formal v2 result files already exist and cannot be overwritten.")

    attempt = _create_attempt_payload()
    attempt_root = Path("data/runtime/retrieval_benchmark_v2_attempts") / attempt["attempt_id"]
    write_attempt_metadata(attempt_root=attempt_root, payload=attempt)

    stage_dir: Path | None = None
    try:
        payloads = build_formal_payloads()
        serialized = _serialize_formal_payloads(payloads)
        stage_dir, staged_paths = stage_formal_v2_outputs(serialized_outputs=serialized, output_paths=output_paths)
        staged_payloads = _load_formal_result_payloads_from_paths(staged_paths)
        _validate_generated_formal_payloads(staged_payloads, formal_case_order=_expected_case_order())
        publish_staged_formal_v2_outputs(staged_paths=staged_paths, output_paths=output_paths)
        attempt.update(
            {
                "status": "completed",
                "completed_at": _utc_now(),
                "technical_failure": False,
                "formal_results_published": True,
            }
        )
        write_attempt_metadata(attempt_root=attempt_root, payload=attempt)
        return {
            "mode": "run",
            "attempt_id": attempt["attempt_id"],
            "attempt_number": attempt["attempt_number"],
            "formal_results_published": True,
            "published_files": {name: str(path) for name, path in output_paths.items()},
        }
    except Exception as exc:
        attempt.update(
            {
                "status": "technical_failure",
                "completed_at": _utc_now(),
                "technical_failure": True,
                "formal_results_published": False,
                "error_type": exc.__class__.__name__,
                "error_message": _safe_error_message(exc),
            }
        )
        write_attempt_metadata(attempt_root=attempt_root, payload=attempt)
        raise
    finally:
        if stage_dir is not None:
            remove_formal_v2_stage_dir(stage_dir)


def build_formal_payloads() -> dict[str, Any]:
    benchmark_config = load_json_record(BENCHMARK_CONFIG_V2_PATH)
    method_configs = _load_method_configs()
    _validate_method_configs_against_v1(method_configs)
    documents_v2 = _load_documents_v2()
    chunks_v2 = _load_chunks_v2()
    cases = _load_cases_v2()
    documents_v1 = project_v2_documents_to_legacy_runtime_inputs(documents_v2)
    chunks_v1 = project_v2_chunks_to_legacy_runtime_inputs(chunks_v2)

    lexical_config = LexicalBaselineConfig.model_validate(method_configs["lexical"]["algorithm_config"])
    vector_config = VectorBaselineConfig.model_validate(method_configs["vector"]["algorithm_config"])
    hybrid_config = HybridBaselineConfig.model_validate(method_configs["hybrid"]["algorithm_config"])
    lexical = WeightedBM25Retriever(config=lexical_config)
    lexical.build_index(documents=documents_v1, chunks=chunks_v1)

    with huggingface_offline_environment():
        provider = SentenceTransformerEmbeddingProvider(
            model_name_or_path=vector_config.model_name_or_path,
            batch_size=vector_config.batch_size,
            device=vector_config.device,
            normalize_embeddings=vector_config.normalize_embeddings,
            allow_model_download=False,
            query_prefix=vector_config.query_prefix,
            document_prefix=vector_config.document_prefix,
            expected_dimension=384,
            expected_revision=vector_config.model_revision,
        )
        vector = ExactVectorRetriever(
            config=vector_config,
            embedding_provider=provider,
            project_root=PROJECT_ROOT,
        )
        vector.build_index(
            documents=documents_v1,
            chunks=chunks_v1,
            knowledge_base_version=load_json_record(Path(benchmark_config["manifest_file"]))["knowledge_base_version"],
        )
        hybrid = ReciprocalRankFusionRetriever(
            config=hybrid_config,
            lexical_retriever=lexical,
            vector_retriever=vector,
        )

        lexical_report = run_retrieval_evaluation_v2(
            cases=cases,
            retriever=lexical,
            method_id="lexical_v1",
            top_k=lexical_config.top_k,
            documents=documents_v2,
            chunks=chunks_v2,
        )
        vector_report = run_retrieval_evaluation_v2(
            cases=cases,
            retriever=vector,
            method_id="vector_v1",
            top_k=vector_config.top_k,
            documents=documents_v2,
            chunks=chunks_v2,
        )
        hybrid_report = run_retrieval_evaluation_v2(
            cases=cases,
            retriever=hybrid,
            method_id="hybrid_v1",
            top_k=hybrid_config.output_top_k,
            documents=documents_v2,
            chunks=chunks_v2,
        )

    lexical_results = build_formal_case_results_v2(
        report=lexical_report,
        cases=cases,
        documents=documents_v2,
        chunks=chunks_v2,
    )
    vector_results = build_formal_case_results_v2(
        report=vector_report,
        cases=cases,
        documents=documents_v2,
        chunks=chunks_v2,
    )
    hybrid_results = build_formal_case_results_v2(
        report=hybrid_report,
        cases=cases,
        documents=documents_v2,
        chunks=chunks_v2,
    )

    benchmark_hash = compute_file_sha256(BENCHMARK_CONFIG_V2_PATH)
    method_hashes = {name: compute_file_sha256(path) for name, path in _method_config_paths().items()}
    lexical_summary = build_formal_summary_v2(
        benchmark_version=benchmark_config["benchmark_version"],
        benchmark_config_hash=benchmark_hash,
        method_config_hash=method_hashes["lexical"],
        retrieval_method=lexical_report.summary.retrieval_method,
        report=lexical_report,
        document_count=len(documents_v2),
        chunk_count=len(chunks_v2),
    )
    vector_summary = build_formal_summary_v2(
        benchmark_version=benchmark_config["benchmark_version"],
        benchmark_config_hash=benchmark_hash,
        method_config_hash=method_hashes["vector"],
        retrieval_method=vector_report.summary.retrieval_method,
        report=vector_report,
        document_count=len(documents_v2),
        chunk_count=len(chunks_v2),
        model_name=provider.model_name,
        resolved_model_revision=provider.resolved_revision,
        embedding_dimension=provider.dimension,
        corpus_embedding_count=vector.corpus_embedding_count,
        corpus_embedding_build_ms=vector.corpus_embedding_build_ms,
        cache_hit_count=vector.cache_hit_count,
        cache_miss_count=vector.cache_miss_count,
    )
    hybrid_summary = build_formal_summary_v2(
        benchmark_version=benchmark_config["benchmark_version"],
        benchmark_config_hash=benchmark_hash,
        method_config_hash=method_hashes["hybrid"],
        retrieval_method=hybrid_report.summary.retrieval_method,
        report=hybrid_report,
        document_count=len(documents_v2),
        chunk_count=len(chunks_v2),
        model_name=provider.model_name,
        resolved_model_revision=provider.resolved_revision,
        embedding_dimension=provider.dimension,
        corpus_embedding_count=vector.corpus_embedding_count,
        corpus_embedding_build_ms=vector.corpus_embedding_build_ms,
        cache_hit_count=vector.cache_hit_count,
        cache_miss_count=vector.cache_miss_count,
    )

    comparison = _build_formal_comparison_payload(
        benchmark_version=benchmark_config["benchmark_version"],
        benchmark_config_hash=benchmark_hash,
        method_config_hashes=method_hashes,
        benchmark_config=benchmark_config,
        summaries={
            "lexical": lexical_summary,
            "vector": vector_summary,
            "hybrid": hybrid_summary,
        },
    )
    payloads = {
        "lexical_results": [row.model_dump(mode="json") for row in lexical_results],
        "lexical_summary": lexical_summary.model_dump(mode="json"),
        "vector_results": [row.model_dump(mode="json") for row in vector_results],
        "vector_summary": vector_summary.model_dump(mode="json"),
        "hybrid_results": [row.model_dump(mode="json") for row in hybrid_results],
        "hybrid_summary": hybrid_summary.model_dump(mode="json"),
        "comparison": comparison,
    }
    _validate_generated_formal_payloads(payloads, formal_case_order=_expected_case_order())
    return payloads


def _validate_generated_formal_payloads(
    payloads: dict[str, Any],
    *,
    formal_case_order: list[str],
) -> None:
    for method_name in ("lexical", "vector", "hybrid"):
        results_key = f"{method_name}_results"
        summary_key = f"{method_name}_summary"
        results = [RetrievalFormalCaseResultV2.model_validate(row) for row in payloads[results_key]]
        summary = RetrievalFormalSummaryV2.model_validate(payloads[summary_key])
        if len(results) != 16:
            raise ValueError(f"{results_key} must contain exactly 16 records.")
        if [row.retrieval_case_id for row in results] != formal_case_order:
            raise ValueError(f"{results_key} must preserve RET2-001 to RET2-016 order.")
        recomputed = recompute_summary_metrics_from_formal_results_v2(results)
        summary_payload = summary.model_dump(mode="json")
        for field, expected_value in recomputed.items():
            if summary_payload[field] != expected_value:
                raise ValueError(f"{summary_key}.{field} does not match recomputed metrics.")
        _assert_safe_formal_result_payload(payloads[results_key], label=results_key)

    comparison = payloads["comparison"]
    method_summaries = comparison["method_summaries"]
    if len(method_summaries) != 3:
        raise ValueError("comparison.method_summaries must contain three methods.")
    summary_by_method = {
        payloads["lexical_summary"]["retrieval_method"]: payloads["lexical_summary"],
        payloads["vector_summary"]["retrieval_method"]: payloads["vector_summary"],
        payloads["hybrid_summary"]["retrieval_method"]: payloads["hybrid_summary"],
    }
    for method_summary in method_summaries:
        actual_summary = summary_by_method[method_summary["retrieval_method"]]
        for field in (
            "case_count",
            "recall_at_1",
            "recall_at_3",
            "recall_at_5",
            "precision_at_3",
            "precision_at_5",
            "mean_reciprocal_rank",
            "forbidden_hit_rate",
            "solution_boundary_violation_rate",
            "average_latency_ms",
            "eligible_for_rag",
            "failed_case_ids",
            "disqualification_reasons",
        ):
            if method_summary[field] != actual_summary[field]:
                raise ValueError(f"comparison.method_summaries mismatch for {method_summary['retrieval_method']} field {field}.")


def _assert_safe_formal_result_payload(records: list[dict[str, Any]], *, label: str) -> None:
    serialized = json.dumps(records, ensure_ascii=False, sort_keys=True)
    lowered = serialized.casefold()
    for forbidden in (
        "expected_relevant_document_ids",
        "expected_relevant_chunk_ids",
        "forbidden_document_ids",
        "forbidden_solution_ids",
        "minimum_relevant_hits",
        "\"query\":",
        "\"content\":",
        "\"embedding\":",
        "/users/",
        "\\\\users\\\\",
    ):
        if forbidden in lowered:
            raise ValueError(f"{label} contains forbidden runtime or secret-bearing field content: {forbidden}")


def _build_formal_comparison_payload(
    *,
    benchmark_version: str,
    benchmark_config_hash: str,
    method_config_hashes: dict[str, str],
    benchmark_config: dict[str, Any],
    summaries: dict[str, RetrievalFormalSummaryV2],
) -> dict[str, Any]:
    entries = [
        _comparison_entry_from_summary(summaries["lexical"]),
        _comparison_entry_from_summary(summaries["vector"]),
        _comparison_entry_from_summary(summaries["hybrid"]),
    ]
    comparison = select_retrieval_method_v2(
        benchmark_version=benchmark_version,
        entries=entries,
        benchmark_config_hash=benchmark_config_hash,
        method_config_hashes=dict(method_config_hashes),
        retrieval_contract_version=benchmark_config["retrieval_contract_version"],
        failure_taxonomy_version=benchmark_config["failure_taxonomy_version"],
        boundary_contract_version=benchmark_config["boundary_contract_version"],
    )
    return comparison.model_dump(mode="json")


def _comparison_entry_from_summary(summary: RetrievalFormalSummaryV2) -> RetrievalMethodComparisonEntry:
    return RetrievalMethodComparisonEntry(
        retrieval_method=summary.retrieval_method,
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
        failed_case_ids=list(summary.failed_case_ids),
        runtime_dependencies=_runtime_dependencies(summary.retrieval_method.value),
    )


def _load_formal_result_payloads() -> dict[str, Any]:
    return _load_formal_result_payloads_from_paths(formal_v2_output_paths())


def _load_formal_result_payloads_from_paths(paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "lexical_results": load_jsonl_records(paths["lexical_results"]),
        "lexical_summary": load_json_record(paths["lexical_summary"]),
        "vector_results": load_jsonl_records(paths["vector_results"]),
        "vector_summary": load_json_record(paths["vector_summary"]),
        "hybrid_results": load_jsonl_records(paths["hybrid_results"]),
        "hybrid_summary": load_json_record(paths["hybrid_summary"]),
        "comparison": load_json_record(paths["comparison"]),
    }


def _compare_formal_payload_maps(*, expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    differences: list[str] = []
    for key in sorted(set(expected) | set(actual)):
        if key not in expected or key not in actual:
            differences.append(key)
            continue
        for diff in compare_payloads_ignoring_runtime_fields(expected[key], actual[key]):
            differences.append(f"{key}:{diff}")
    return differences


def _serialize_formal_payloads(payloads: dict[str, Any]) -> dict[str, str]:
    return {
        "lexical_results": _to_jsonl(payloads["lexical_results"]),
        "lexical_summary": _to_json(payloads["lexical_summary"]),
        "vector_results": _to_jsonl(payloads["vector_results"]),
        "vector_summary": _to_json(payloads["vector_summary"]),
        "hybrid_results": _to_jsonl(payloads["hybrid_results"]),
        "hybrid_summary": _to_json(payloads["hybrid_summary"]),
        "comparison": _to_json(payloads["comparison"]),
    }


def _to_jsonl(records: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for record in records) + "\n"


def _to_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _load_documents_v2() -> list[KnowledgeDocumentV2]:
    benchmark_config = load_json_record(BENCHMARK_CONFIG_V2_PATH)
    return [KnowledgeDocumentV2.model_validate(row) for row in load_jsonl_records(Path(benchmark_config["document_file"]))]


def _load_chunks_v2() -> list[KnowledgeChunkV2]:
    benchmark_config = load_json_record(BENCHMARK_CONFIG_V2_PATH)
    return [KnowledgeChunkV2.model_validate(row) for row in load_jsonl_records(Path(benchmark_config["chunk_file"]))]


def _load_cases_v2() -> list[RetrievalEvaluationCaseV2]:
    benchmark_config = load_json_record(BENCHMARK_CONFIG_V2_PATH)
    return [RetrievalEvaluationCaseV2.model_validate(row) for row in load_jsonl_records(Path(benchmark_config["case_file"]))]


def _expected_case_order() -> list[str]:
    return [case.retrieval_case_id for case in _load_cases_v2()]


def _method_config_paths() -> dict[str, Path]:
    return {
        "lexical": LEXICAL_CONFIG_V2_PATH,
        "vector": VECTOR_CONFIG_V2_PATH,
        "hybrid": HYBRID_CONFIG_V2_PATH,
    }


def _load_method_configs() -> dict[str, dict[str, Any]]:
    return {name: load_json_record(path) for name, path in _method_config_paths().items()}


def _load_vector_config() -> VectorBaselineConfig:
    return VectorBaselineConfig.model_validate(load_json_record(VECTOR_CONFIG_V2_PATH)["algorithm_config"])


def _validate_method_configs_against_v1(method_configs: dict[str, dict[str, Any]]) -> None:
    v1_payloads = {
        "lexical": load_json_record(LEXICAL_CONFIG_V1_PATH),
        "vector": load_json_record(VECTOR_CONFIG_V1_PATH),
        "hybrid": load_json_record(HYBRID_CONFIG_V1_PATH),
    }
    for name, config in method_configs.items():
        if config["algorithm_config"] != v1_payloads[name]:
            raise ValueError(f"{name} v2 algorithm_config drifted from v1.")
        if config["source_v1_config_hash"] != compute_file_sha256(_method_config_v1_path(name)):
            raise ValueError(f"{name} v2 source_v1_config_hash does not match tracked v1 config.")
        if config["benchmark_config_hash"] != compute_file_sha256(BENCHMARK_CONFIG_V2_PATH):
            raise ValueError(f"{name} v2 benchmark_config_hash does not match retrieval_benchmark_config.v2.json.")


def _method_config_v1_path(name: str) -> Path:
    return {
        "lexical": LEXICAL_CONFIG_V1_PATH,
        "vector": VECTOR_CONFIG_V1_PATH,
        "hybrid": HYBRID_CONFIG_V1_PATH,
    }[name]


def _comparison_entry(method_name: str, report: Any) -> RetrievalMethodComparisonEntry:
    return RetrievalMethodComparisonEntry(
        retrieval_method=method_name,
        case_count=report.summary.case_count,
        recall_at_1=report.summary.recall_at_1,
        recall_at_3=report.summary.recall_at_3,
        recall_at_5=report.summary.recall_at_5,
        precision_at_3=report.summary.precision_at_3,
        precision_at_5=report.summary.precision_at_5,
        mean_reciprocal_rank=report.summary.mean_reciprocal_rank,
        forbidden_hit_rate=report.summary.forbidden_hit_rate,
        solution_boundary_violation_rate=report.summary.solution_boundary_violation_rate,
        average_latency_ms=report.summary.average_latency_ms,
        eligible_for_rag=report.summary.eligible_for_rag,
        disqualification_reasons=list(report.summary.disqualification_reasons),
        failed_case_ids=[row.retrieval_case_id for row in report.case_results if not row.passed_blocking_gate],
        runtime_dependencies=_runtime_dependencies(method_name),
    )


def _runtime_dependencies(method_name: str) -> list[str]:
    if method_name == "lexical_v1":
        return ["weighted_bm25"]
    if method_name == "vector_v1":
        return ["sentence_transformers_local_snapshot"]
    return ["weighted_bm25", "sentence_transformers_local_snapshot"]


def _report_summary(report: Any) -> dict[str, Any]:
    return {
        "case_count": report.summary.case_count,
        "eligible_for_rag": report.summary.eligible_for_rag,
        "failed_case_ids": [row.retrieval_case_id for row in report.case_results if not row.passed_blocking_gate],
        "failure_taxonomy": report.summary.disqualification_reasons,
    }


def _directory_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".writable_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _network_is_blocked() -> bool:
    try:
        socket.gethostbyname("huggingface.co")
        return False
    except OSError:
        return True


def _create_attempt_payload() -> dict[str, Any]:
    attempt_root = Path("data/runtime/retrieval_benchmark_v2_attempts")
    attempt_root.mkdir(parents=True, exist_ok=True)
    existing = sorted(path for path in attempt_root.iterdir() if path.is_dir())
    return {
        "attempt_id": f"RB2-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}",
        "attempt_number": len(existing) + 1,
        "status": "started",
        "started_at": _utc_now(),
        "completed_at": None,
        "technical_failure": False,
        "formal_results_published": False,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_error_message(error: Exception) -> str:
    return str(error).replace("\n", " ").strip() or error.__class__.__name__


if __name__ == "__main__":
    raise SystemExit(main())
