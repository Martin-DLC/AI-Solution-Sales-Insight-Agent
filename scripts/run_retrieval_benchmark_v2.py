from __future__ import annotations

import argparse
import json
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.retrieval import RetrievalMethodComparisonEntry
from evaluation.retrieval.comparison_v2 import select_retrieval_method_v2
from evaluation.retrieval.contracts_v2 import RetrievalEvaluationCaseV2
from evaluation.retrieval.runner_v2 import (
    project_v2_chunks_to_legacy_runtime_inputs,
    project_v2_documents_to_legacy_runtime_inputs,
    run_retrieval_evaluation_v2,
)
from evaluation.retrieval.storage_v2 import (
    NON_DETERMINISTIC_RESULT_FIELDS_V2,
    compute_file_sha256,
    formal_v2_output_paths,
    formal_v2_results_exist,
    load_json_record,
    load_jsonl_records,
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
    parser = argparse.ArgumentParser(description="Plan, validate, or non-formally smoke Retrieval Benchmark v2.")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--fake-smoke", action="store_true")
    parser.add_argument("--offline-model-smoke", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    modes = [args.validate, args.fake_smoke, args.offline_model_smoke, args.check]
    if sum(bool(item) for item in modes) > 1:
        print("Choose only one of --validate, --fake-smoke, --offline-model-smoke, or --check.", file=sys.stderr)
        return 2

    if args.validate:
        payload = build_validate_payload()
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.fake_smoke:
        payload = run_fake_smoke()
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.offline_model_smoke:
        payload = run_offline_model_smoke()
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.check:
        payload = build_check_payload()
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
        raise ValueError("Formal v2 result files already exist; D4C1 validate expects them to be absent.")
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


def build_check_payload() -> dict[str, Any]:
    validate_payload = build_validate_payload()
    return {
        "mode": "check",
        "status": "formal_results_not_generated",
        "formal_output_paths": {name: str(path) for name, path in formal_v2_output_paths().items()},
        "formal_results_exist": formal_v2_results_exist(),
        "non_deterministic_result_fields": sorted(NON_DETERMINISTIC_RESULT_FIELDS_V2),
        "validate": validate_payload,
    }


def _load_documents_v2() -> list[KnowledgeDocumentV2]:
    benchmark_config = load_json_record(BENCHMARK_CONFIG_V2_PATH)
    return [
        KnowledgeDocumentV2.model_validate(row)
        for row in load_jsonl_records(Path(benchmark_config["document_file"]))
    ]


def _load_chunks_v2() -> list[KnowledgeChunkV2]:
    benchmark_config = load_json_record(BENCHMARK_CONFIG_V2_PATH)
    return [
        KnowledgeChunkV2.model_validate(row)
        for row in load_jsonl_records(Path(benchmark_config["chunk_file"]))
    ]


def _load_cases_v2() -> list[RetrievalEvaluationCaseV2]:
    benchmark_config = load_json_record(BENCHMARK_CONFIG_V2_PATH)
    return [
        RetrievalEvaluationCaseV2.model_validate(row)
        for row in load_jsonl_records(Path(benchmark_config["case_file"]))
    ]


def _method_config_paths() -> dict[str, Path]:
    return {
        "lexical": LEXICAL_CONFIG_V2_PATH,
        "vector": VECTOR_CONFIG_V2_PATH,
        "hybrid": HYBRID_CONFIG_V2_PATH,
    }


def _load_method_configs() -> dict[str, dict[str, Any]]:
    return {name: load_json_record(path) for name, path in _method_config_paths().items()}


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


def _network_is_blocked() -> bool:
    try:
        socket.gethostbyname("huggingface.co")
        return False
    except OSError:
        return True


if __name__ == "__main__":
    raise SystemExit(main())
