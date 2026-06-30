from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
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
FORMAL_V2_ATTEMPT_ROOT = Path("data/runtime/retrieval_benchmark_v2_attempts")


def formal_v2_output_paths() -> dict[str, Path]:
    return dict(FORMAL_V2_OUTPUT_PATHS)


def formal_v2_results_exist() -> bool:
    return any(path.exists() for path in FORMAL_V2_OUTPUT_PATHS.values())


def formal_v2_missing_outputs() -> list[Path]:
    return [path for path in FORMAL_V2_OUTPUT_PATHS.values() if not path.exists()]


def create_formal_v2_stage_dir(stage_root: str | Path | None = None) -> Path:
    root = Path(stage_root) if stage_root is not None else FORMAL_V2_ATTEMPT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="formal_v2_publish_", dir=root))


def stage_formal_v2_outputs(
    *,
    serialized_outputs: dict[str, str],
    output_paths: dict[str, Path] | None = None,
    stage_root: str | Path | None = None,
) -> tuple[Path, dict[str, Path]]:
    resolved_paths = output_paths or formal_v2_output_paths()
    stage_dir = create_formal_v2_stage_dir(stage_root)
    staged_paths: dict[str, Path] = {}
    for key, final_path in resolved_paths.items():
        if key not in serialized_outputs:
            raise ValueError(f"Missing serialized output for {key}.")
        staged_path = stage_dir / final_path.name
        staged_path.write_text(serialized_outputs[key], encoding="utf-8")
        staged_paths[key] = staged_path
    return stage_dir, staged_paths


def publish_staged_formal_v2_outputs(
    *,
    staged_paths: dict[str, Path],
    output_paths: dict[str, Path] | None = None,
) -> None:
    resolved_paths = output_paths or formal_v2_output_paths()
    existing = [path for path in resolved_paths.values() if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Formal v2 results already exist and cannot be overwritten: {joined}")

    published_paths: list[Path] = []
    try:
        for key, final_path in resolved_paths.items():
            staged_path = staged_paths[key]
            final_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.replace(final_path)
            published_paths.append(final_path)
    except Exception:
        for path in published_paths:
            if path.exists():
                path.unlink()
        raise


def remove_formal_v2_stage_dir(stage_dir: str | Path) -> None:
    shutil.rmtree(Path(stage_dir), ignore_errors=True)


def write_attempt_metadata(
    *,
    attempt_root: str | Path,
    payload: dict[str, Any],
) -> Path:
    root = Path(attempt_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "attempt_metadata.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


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
