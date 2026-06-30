from __future__ import annotations

import json
from pathlib import Path


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_v2_method_configs_keep_algorithm_parameters_identical_to_v1() -> None:
    assert _load("data/evaluation/retrieval/lexical_baseline_config.v2.json")["algorithm_config"] == _load(
        "data/evaluation/retrieval/lexical_baseline_config.v1.json"
    )
    assert _load("data/evaluation/retrieval/vector_baseline_config.v2.json")["algorithm_config"] == _load(
        "data/evaluation/retrieval/vector_baseline_config.v1.json"
    )
    assert _load("data/evaluation/retrieval/hybrid_baseline_config.v2.json")["algorithm_config"] == _load(
        "data/evaluation/retrieval/hybrid_baseline_config.v1.json"
    )


def test_v2_method_configs_reference_v2_benchmark_and_artifacts() -> None:
    for path in [
        "data/evaluation/retrieval/lexical_baseline_config.v2.json",
        "data/evaluation/retrieval/vector_baseline_config.v2.json",
        "data/evaluation/retrieval/hybrid_baseline_config.v2.json",
    ]:
        payload = _load(path)
        assert payload["benchmark_config_file"] == "data/evaluation/retrieval/retrieval_benchmark_config.v2.json"
        assert payload["document_file"] == "data/knowledge_base/documents.v2.jsonl"
        assert payload["chunk_file"] == "data/knowledge_base/chunks.v2.jsonl"
        assert payload["case_file"] == "data/evaluation/retrieval/retrieval_cases.v2.jsonl"
        assert payload["retrieval_contract_version"] == "v2_method_aware"
