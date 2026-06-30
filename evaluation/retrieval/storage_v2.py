from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


NON_DETERMINISTIC_RESULT_FIELDS_V2 = {
    "generated_at",
    "latency_ms",
    "average_latency_ms",
    "corpus_embedding_build_ms",
    "cache_hit_count",
    "cache_miss_count",
}

FORMAL_V2_OUTPUT_PATHS = {
    "lexical_results": Path("data/evaluation/retrieval/lexical_baseline_results.v2.jsonl"),
    "lexical_summary": Path("data/evaluation/retrieval/lexical_baseline_summary.v2.json"),
    "vector_results": Path("data/evaluation/retrieval/vector_baseline_results.v2.jsonl"),
    "vector_summary": Path("data/evaluation/retrieval/vector_baseline_summary.v2.json"),
    "hybrid_results": Path("data/evaluation/retrieval/hybrid_baseline_results.v2.jsonl"),
    "hybrid_summary": Path("data/evaluation/retrieval/hybrid_baseline_summary.v2.json"),
    "comparison": Path("data/evaluation/retrieval/retrieval_method_comparison.v2.json"),
}


def formal_v2_output_paths() -> dict[str, Path]:
    return dict(FORMAL_V2_OUTPUT_PATHS)


def formal_v2_results_exist() -> bool:
    return any(path.exists() for path in FORMAL_V2_OUTPUT_PATHS.values())


def compute_file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json_record(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Expected JSON object.")
    return payload


def load_jsonl_records(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def compare_payloads_ignoring_runtime_fields(
    expected: Any,
    actual: Any,
) -> list[str]:
    return _diff_json(expected, actual)


def _diff_json(expected: Any, actual: Any, path: str = "") -> list[str]:
    if path:
        last_key = path.split(".")[-1]
        if last_key in NON_DETERMINISTIC_RESULT_FIELDS_V2:
            return []
    if type(expected) is not type(actual):
        return [path or "$"]
    if isinstance(expected, dict):
        differences: list[str] = []
        for key in sorted(set(expected) | set(actual)):
            child = f"{path}.{key}" if path else key
            if key not in expected or key not in actual:
                differences.append(child)
                continue
            differences.extend(_diff_json(expected[key], actual[key], child))
        return differences
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return [path or "$"]
        differences: list[str] = []
        for index, (left, right) in enumerate(zip(expected, actual)):
            child = f"{path}[{index}]" if path else f"[{index}]"
            differences.extend(_diff_json(left, right, child))
        return differences
    if expected != actual:
        return [path or "$"]
    return []
