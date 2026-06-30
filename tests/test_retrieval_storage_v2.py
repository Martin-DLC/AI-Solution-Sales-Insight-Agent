from __future__ import annotations

from evaluation.retrieval.storage_v2 import (
    NON_DETERMINISTIC_RESULT_FIELDS_V2,
    compare_payloads_ignoring_runtime_fields,
    publish_staged_formal_v2_outputs,
    remove_formal_v2_stage_dir,
    stage_formal_v2_outputs,
    formal_v2_output_paths,
    formal_v2_results_exist,
)


def test_formal_v2_output_paths_are_declared_but_not_present() -> None:
    paths = formal_v2_output_paths()

    assert sorted(paths) == [
        "comparison",
        "hybrid_results",
        "hybrid_summary",
        "lexical_results",
        "lexical_summary",
        "vector_results",
        "vector_summary",
    ]
    assert isinstance(formal_v2_results_exist(), bool)


def test_compare_payloads_ignores_only_runtime_fields() -> None:
    left = {"generated_at": "a", "average_latency_ms": 12, "stable": 1}
    right = {"generated_at": "b", "average_latency_ms": 99, "stable": 1}
    drift = {"generated_at": "b", "average_latency_ms": 99, "stable": 2}

    assert compare_payloads_ignoring_runtime_fields(left, right) == []
    assert compare_payloads_ignoring_runtime_fields(left, drift) == ["stable"]
    assert "generated_at" in NON_DETERMINISTIC_RESULT_FIELDS_V2


def test_stage_and_publish_formal_outputs(tmp_path) -> None:
    output_paths = {
        "lexical_results": tmp_path / "lexical_results.jsonl",
        "lexical_summary": tmp_path / "lexical_summary.json",
        "vector_results": tmp_path / "vector_results.jsonl",
        "vector_summary": tmp_path / "vector_summary.json",
        "hybrid_results": tmp_path / "hybrid_results.jsonl",
        "hybrid_summary": tmp_path / "hybrid_summary.json",
        "comparison": tmp_path / "comparison.json",
    }
    serialized = {key: f"{key}\n" for key in output_paths}

    stage_dir, staged_paths = stage_formal_v2_outputs(
        serialized_outputs=serialized,
        output_paths=output_paths,
        stage_root=tmp_path / "runtime",
    )
    publish_staged_formal_v2_outputs(staged_paths=staged_paths, output_paths=output_paths)

    for key, path in output_paths.items():
        assert path.read_text(encoding="utf-8") == serialized[key]
    remove_formal_v2_stage_dir(stage_dir)
