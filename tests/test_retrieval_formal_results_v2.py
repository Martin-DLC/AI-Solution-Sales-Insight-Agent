from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_retrieval_benchmark_v2 as cli
from evaluation.retrieval.storage_v2 import (
    publish_staged_formal_v2_outputs,
    stage_formal_v2_outputs,
)


def _fake_case_ids() -> list[str]:
    return [f"RET2-{index:03d}" for index in range(1, 17)]


def _fake_results(method: str, *, latency_ms: int = 1) -> list[dict]:
    results: list[dict] = []
    for index, case_id in enumerate(_fake_case_ids(), start=1):
        results.append(
            {
                "retrieval_case_id": case_id,
                "source_case_id": f"DEV-{index:02d}",
                "retrieval_method": method,
                "query_type": "solution_discovery",
                "candidate_count": 1,
                "candidates": [
                    {
                        "rank": 1,
                        "document_id": f"DOC-{index:03d}",
                        "chunk_id": f"DOC-{index:03d}#chunk-001",
                        "document_type": "solution",
                        "score": 1.0,
                        "scope_type": "solution_specific",
                        "applicable_solution_ids": ["SOL-001"],
                        "boundary_violation": False,
                        "lexical_rank": 1 if method == "hybrid_v1" else None,
                        "vector_rank": 1 if method == "hybrid_v1" else None,
                        "lexical_score": 1.0 if method == "hybrid_v1" else None,
                        "vector_score": 1.0 if method == "hybrid_v1" else None,
                        "rrf_score": 0.5 if method == "hybrid_v1" else None,
                    }
                ],
                "case_metrics": {
                    "recall_at_1": 1.0,
                    "recall_at_3": 1.0,
                    "recall_at_5": 1.0,
                    "precision_at_3": 1.0,
                    "precision_at_5": 1.0,
                    "reciprocal_rank": 1.0,
                    "forbidden_hit": False,
                    "solution_boundary_violation": False,
                    "request_error": False,
                },
                "failure_reasons": [],
                "passed_blocking_gate": True,
                "latency_ms": latency_ms,
                "error_type": None,
                "error_message": None,
            }
        )
    return results


def _fake_summary(method: str, *, method_hash: str, average_latency_ms: float) -> dict:
    payload = {
        "benchmark_version": "retrieval_benchmark_v2",
        "retrieval_method": method,
        "method_config_hash": method_hash,
        "benchmark_config_hash": "bench",
        "document_count": 20,
        "chunk_count": 40,
        "case_count": 16,
        "recall_at_1": 1.0,
        "recall_at_3": 1.0,
        "recall_at_5": 1.0,
        "precision_at_3": 1.0,
        "precision_at_5": 1.0,
        "mean_reciprocal_rank": 1.0,
        "forbidden_hit_rate": 0.0,
        "solution_boundary_violation_rate": 0.0,
        "request_error_count": 0,
        "failed_case_ids": [],
        "failure_taxonomy": {},
        "eligible_for_rag": True,
        "disqualification_reasons": [],
        "average_latency_ms": average_latency_ms,
        "model_name": None,
        "resolved_model_revision": None,
        "embedding_dimension": None,
        "corpus_embedding_count": None,
        "corpus_embedding_build_ms": None,
        "cache_hit_count": None,
        "cache_miss_count": None,
    }
    if method != "lexical_v1":
        payload.update(
            {
                "model_name": "intfloat/multilingual-e5-small",
                "resolved_model_revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
                "embedding_dimension": 384,
                "corpus_embedding_count": 40,
                "corpus_embedding_build_ms": 12,
                "cache_hit_count": 0,
                "cache_miss_count": 40,
            }
        )
    return payload


def _fake_payloads() -> dict[str, object]:
    lexical_summary = _fake_summary("lexical_v1", method_hash="lex", average_latency_ms=3.0)
    vector_summary = _fake_summary("vector_v1", method_hash="vec", average_latency_ms=1.0)
    hybrid_summary = _fake_summary("hybrid_v1", method_hash="hyb", average_latency_ms=4.0)
    return {
        "lexical_results": _fake_results("lexical_v1", latency_ms=3),
        "lexical_summary": lexical_summary,
        "vector_results": _fake_results("vector_v1", latency_ms=1),
        "vector_summary": vector_summary,
        "hybrid_results": _fake_results("hybrid_v1", latency_ms=4),
        "hybrid_summary": hybrid_summary,
        "comparison": {
            "benchmark_version": "retrieval_benchmark_v2",
            "benchmark_config_hash": "bench",
            "method_config_hashes": {"lexical": "lex", "vector": "vec", "hybrid": "hyb"},
            "method_summaries": [
                {
                    "retrieval_method": "lexical_v1",
                    "case_count": 16,
                    "recall_at_1": 1.0,
                    "recall_at_3": 1.0,
                    "recall_at_5": 1.0,
                    "precision_at_3": 1.0,
                    "precision_at_5": 1.0,
                    "mean_reciprocal_rank": 1.0,
                    "forbidden_hit_rate": 0.0,
                    "solution_boundary_violation_rate": 0.0,
                    "average_latency_ms": 3.0,
                    "eligible_for_rag": True,
                    "disqualification_reasons": [],
                    "failed_case_ids": [],
                },
                {
                    "retrieval_method": "vector_v1",
                    "case_count": 16,
                    "recall_at_1": 1.0,
                    "recall_at_3": 1.0,
                    "recall_at_5": 1.0,
                    "precision_at_3": 1.0,
                    "precision_at_5": 1.0,
                    "mean_reciprocal_rank": 1.0,
                    "forbidden_hit_rate": 0.0,
                    "solution_boundary_violation_rate": 0.0,
                    "average_latency_ms": 1.0,
                    "eligible_for_rag": True,
                    "disqualification_reasons": [],
                    "failed_case_ids": [],
                },
                {
                    "retrieval_method": "hybrid_v1",
                    "case_count": 16,
                    "recall_at_1": 1.0,
                    "recall_at_3": 1.0,
                    "recall_at_5": 1.0,
                    "precision_at_3": 1.0,
                    "precision_at_5": 1.0,
                    "mean_reciprocal_rank": 1.0,
                    "forbidden_hit_rate": 0.0,
                    "solution_boundary_violation_rate": 0.0,
                    "average_latency_ms": 4.0,
                    "eligible_for_rag": True,
                    "disqualification_reasons": [],
                    "failed_case_ids": [],
                },
            ],
            "entries": [],
            "selected_method": "vector_v1",
            "selection_status": "eligible_method_selected",
            "selection_reasons": ["selected"],
            "rejected_methods": ["lexical_v1", "hybrid_v1"],
            "comparison_limitations": ["synthetic only"],
            "retrieval_contract_version": "v2_method_aware",
            "failure_taxonomy_version": "v2_method_aware",
            "boundary_contract_version": "v2",
        },
    }


def _write_payloads(output_paths: dict[str, Path], payloads: dict[str, object]) -> None:
    output_paths["lexical_results"].write_text(cli._to_jsonl(payloads["lexical_results"]), encoding="utf-8")
    output_paths["lexical_summary"].write_text(cli._to_json(payloads["lexical_summary"]), encoding="utf-8")
    output_paths["vector_results"].write_text(cli._to_jsonl(payloads["vector_results"]), encoding="utf-8")
    output_paths["vector_summary"].write_text(cli._to_json(payloads["vector_summary"]), encoding="utf-8")
    output_paths["hybrid_results"].write_text(cli._to_jsonl(payloads["hybrid_results"]), encoding="utf-8")
    output_paths["hybrid_summary"].write_text(cli._to_json(payloads["hybrid_summary"]), encoding="utf-8")
    output_paths["comparison"].write_text(cli._to_json(payloads["comparison"]), encoding="utf-8")


def test_run_formal_write_publishes_all_seven_files(monkeypatch, tmp_path) -> None:
    payloads = _fake_payloads()
    output_paths = {key: tmp_path / f"{key}.json" for key in cli.formal_v2_output_paths()}
    output_paths["lexical_results"] = tmp_path / "lexical_results.jsonl"
    output_paths["vector_results"] = tmp_path / "vector_results.jsonl"
    output_paths["hybrid_results"] = tmp_path / "hybrid_results.jsonl"

    monkeypatch.setattr(cli, "build_formal_readiness_payload", lambda: {"ready_for_single_formal_run": True})
    monkeypatch.setattr(cli, "formal_v2_results_exist", lambda: False)
    monkeypatch.setattr(cli, "build_formal_payloads", lambda: payloads)
    monkeypatch.setattr(cli, "formal_v2_output_paths", lambda: output_paths)
    monkeypatch.setattr(cli, "_expected_case_order", _fake_case_ids)
    monkeypatch.setattr(
        cli,
        "stage_formal_v2_outputs",
        lambda *, serialized_outputs, output_paths: stage_formal_v2_outputs(
            serialized_outputs=serialized_outputs,
            output_paths=output_paths,
            stage_root=tmp_path / "runtime",
        ),
    )
    monkeypatch.setattr(cli, "write_attempt_metadata", lambda **kwargs: tmp_path / "attempt.json")
    monkeypatch.setattr(
        cli,
        "_create_attempt_payload",
        lambda: {
            "attempt_id": "ATTEMPT-1",
            "attempt_number": 1,
            "status": "started",
            "started_at": "2026-07-01T00:00:00+00:00",
            "completed_at": None,
            "technical_failure": False,
            "formal_results_published": False,
        },
    )

    result = cli.run_formal_write()

    assert result["formal_results_published"] is True
    for path in output_paths.values():
        assert path.exists()


def test_run_formal_write_failure_does_not_leave_partial_results(monkeypatch, tmp_path) -> None:
    payloads = _fake_payloads()
    output_paths = {key: tmp_path / f"{key}.json" for key in cli.formal_v2_output_paths()}
    output_paths["lexical_results"] = tmp_path / "lexical_results.jsonl"
    output_paths["vector_results"] = tmp_path / "vector_results.jsonl"
    output_paths["hybrid_results"] = tmp_path / "hybrid_results.jsonl"

    monkeypatch.setattr(cli, "build_formal_readiness_payload", lambda: {"ready_for_single_formal_run": True})
    monkeypatch.setattr(cli, "formal_v2_results_exist", lambda: False)
    monkeypatch.setattr(cli, "build_formal_payloads", lambda: payloads)
    monkeypatch.setattr(cli, "formal_v2_output_paths", lambda: output_paths)
    monkeypatch.setattr(cli, "_expected_case_order", _fake_case_ids)
    monkeypatch.setattr(
        cli,
        "stage_formal_v2_outputs",
        lambda *, serialized_outputs, output_paths: stage_formal_v2_outputs(
            serialized_outputs=serialized_outputs,
            output_paths=output_paths,
            stage_root=tmp_path / "runtime",
        ),
    )
    monkeypatch.setattr(cli, "publish_staged_formal_v2_outputs", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("publish failed")))
    monkeypatch.setattr(cli, "write_attempt_metadata", lambda **kwargs: tmp_path / "attempt.json")
    monkeypatch.setattr(
        cli,
        "_create_attempt_payload",
        lambda: {
            "attempt_id": "ATTEMPT-2",
            "attempt_number": 2,
            "status": "started",
            "started_at": "2026-07-01T00:00:00+00:00",
            "completed_at": None,
            "technical_failure": False,
            "formal_results_published": False,
        },
    )

    with pytest.raises(RuntimeError, match="publish failed"):
        cli.run_formal_write()

    assert not any(path.exists() for path in output_paths.values())


def test_check_accepts_runtime_only_field_drift_but_rejects_rank_drift(monkeypatch, tmp_path) -> None:
    payloads = _fake_payloads()
    output_paths = {key: tmp_path / f"{key}.json" for key in cli.formal_v2_output_paths()}
    output_paths["lexical_results"] = tmp_path / "lexical_results.jsonl"
    output_paths["vector_results"] = tmp_path / "vector_results.jsonl"
    output_paths["hybrid_results"] = tmp_path / "hybrid_results.jsonl"

    payloads_with_runtime_drift = json.loads(json.dumps(payloads))
    payloads_with_runtime_drift["vector_results"][0]["latency_ms"] = 999
    _write_payloads(output_paths, payloads_with_runtime_drift)

    monkeypatch.setattr(cli, "_build_core_validation_payload", lambda: {"mode": "validate"})
    monkeypatch.setattr(cli, "formal_v2_output_paths", lambda: output_paths)
    monkeypatch.setattr(cli, "build_formal_payloads", lambda: payloads)
    monkeypatch.setattr(
        cli,
        "inspect_formal_result_state",
        lambda: {
            "state": cli.FORMAL_RESULT_STATE_COMPLETE,
            "existing_paths": {name: str(path) for name, path in output_paths.items()},
            "missing_paths": {},
            "formal_results_exist": True,
        },
    )

    payload, ok = cli.build_check_payload()
    assert ok is True
    assert payload["status"] == "formal_results_match"

    payloads_with_rank_drift = json.loads(json.dumps(payloads))
    payloads_with_rank_drift["vector_results"][0]["candidates"][0]["rank"] = 2
    _write_payloads(output_paths, payloads_with_rank_drift)

    payload, ok = cli.build_check_payload()
    assert ok is False
    assert payload["status"] == "formal_results_mismatch"
    assert any("vector_results" in item for item in payload["differences"])

    payloads_with_revision_drift = json.loads(json.dumps(payloads))
    payloads_with_revision_drift["vector_summary"]["resolved_model_revision"] = "different-revision"
    _write_payloads(output_paths, payloads_with_revision_drift)

    payload, ok = cli.build_check_payload()
    assert ok is False
    assert any("vector_summary" in item for item in payload["differences"])


def test_check_reports_partial_formal_results(monkeypatch, tmp_path) -> None:
    output_paths = {key: tmp_path / f"{key}.json" for key in cli.formal_v2_output_paths()}
    output_paths["lexical_results"] = tmp_path / "lexical_results.jsonl"
    output_paths["vector_results"] = tmp_path / "vector_results.jsonl"
    output_paths["hybrid_results"] = tmp_path / "hybrid_results.jsonl"

    monkeypatch.setattr(cli, "_build_core_validation_payload", lambda: {"mode": "validate"})
    monkeypatch.setattr(cli, "formal_v2_output_paths", lambda: output_paths)
    monkeypatch.setattr(
        cli,
        "inspect_formal_result_state",
        lambda: {
            "state": cli.FORMAL_RESULT_STATE_PARTIAL,
            "existing_paths": {"lexical_results": str(output_paths["lexical_results"])},
            "missing_paths": {"comparison": str(output_paths["comparison"])},
            "formal_results_exist": True,
        },
    )

    payload, ok = cli.build_check_payload()

    assert ok is False
    assert payload["status"] == "partial_formal_results_detected"
    assert payload["formal_result_state"] == cli.FORMAL_RESULT_STATE_PARTIAL
    assert "lexical_results" in payload["existing_formal_output_paths"]
    assert "comparison" in payload["missing_formal_output_paths"]


def test_check_reports_not_generated_without_requiring_absence_validation(monkeypatch, tmp_path) -> None:
    output_paths = {key: tmp_path / f"{key}.json" for key in cli.formal_v2_output_paths()}
    output_paths["lexical_results"] = tmp_path / "lexical_results.jsonl"
    output_paths["vector_results"] = tmp_path / "vector_results.jsonl"
    output_paths["hybrid_results"] = tmp_path / "hybrid_results.jsonl"

    monkeypatch.setattr(cli, "_build_core_validation_payload", lambda: {"mode": "validate"})
    monkeypatch.setattr(cli, "formal_v2_output_paths", lambda: output_paths)
    monkeypatch.setattr(
        cli,
        "inspect_formal_result_state",
        lambda: {
            "state": cli.FORMAL_RESULT_STATE_NOT_GENERATED,
            "existing_paths": {},
            "missing_paths": {name: str(path) for name, path in output_paths.items()},
            "formal_results_exist": False,
        },
    )

    payload, ok = cli.build_check_payload()

    assert ok is True
    assert payload["status"] == "formal_results_not_generated"
    assert payload["formal_result_state"] == cli.FORMAL_RESULT_STATE_NOT_GENERATED
