from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_cli_module():
    script_path = Path("scripts/analyze_retrieval_v2_candidate_generation.py")
    spec = importlib.util.spec_from_file_location("analyze_retrieval_v2_candidate_generation", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load analyze_retrieval_v2_candidate_generation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plan_mode_does_not_build_full_analysis(monkeypatch, capsys) -> None:
    module = _load_cli_module()

    def fail_build() -> None:
        raise AssertionError("plan mode should not build the full analysis payload")

    monkeypatch.setattr(module, "build_candidate_generation_payload", fail_build)
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(module.sys, "argv", ["analyze_retrieval_v2_candidate_generation.py"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["mode"] == "plan"
    assert payload["diagnostic_only"] is True


def test_check_mode_returns_zero_when_outputs_match(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    monkeypatch.setattr(module, "check_candidate_generation_outputs", lambda: (True, []))
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(module.sys, "argv", ["analyze_retrieval_v2_candidate_generation.py", "--check"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "candidate_generation_outputs_match"
    assert payload["differences"] == []


def test_recall_round_1_plan_mode_does_not_build_main_analysis(monkeypatch, capsys) -> None:
    module = _load_cli_module()

    def fail_build() -> None:
        raise AssertionError("round 1 plan mode should not build the full candidate generation payload")

    monkeypatch.setattr(module, "build_candidate_generation_payload", fail_build)
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(module.sys, "argv", ["analyze_retrieval_v2_candidate_generation.py", "--recall-round-1"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["experiment_id"] == "retrieval_v2_candidate_recall_round_1"


def test_write_mode_reports_tracked_output_paths(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    fake_payload = {
        "analysis_version": "retrieval_v2_candidate_generation_analysis_v1",
        "diagnostic_only": True,
        "candidate_generation_ready": False,
        "rerank_required": False,
        "query_rewrite_required": True,
        "architecture_c_status": "blocked",
    }
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(module, "build_candidate_generation_payload", lambda: fake_payload)
    monkeypatch.setattr(module, "write_candidate_generation_outputs", lambda payload: calls.append(payload))
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(module.sys, "argv", ["analyze_retrieval_v2_candidate_generation.py", "--write"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert calls == [fake_payload]
    assert payload["mode"] == "write"
    assert payload["diagnostic_only"] is True
    assert payload["architecture_c_status"] == "blocked"


def test_recall_round_1_write_mode_reports_round_status(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    fake_payload = {
        "overall_metrics": {
            "candidate_recall_at_20": 0.96875,
            "full_recall_case_count_at_20": 14,
        },
        "round_status": "failed_frozen_move_to_round_2",
        "success_gate": {"passed": False},
        "next_step": "round_2_document_level_retrieval_plus_child_chunk_expansion",
    }
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(module, "build_recall_round_1_payload", lambda: fake_payload)
    monkeypatch.setattr(module, "write_recall_round_1_output", lambda payload: calls.append(payload))
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(
        module.sys,
        "argv",
        ["analyze_retrieval_v2_candidate_generation.py", "--recall-round-1", "--write"],
    )

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert calls == [fake_payload]
    assert payload["experiment"] == "recall_round_1"
    assert payload["round_status"] == "failed_frozen_move_to_round_2"
    assert payload["success_gate_passed"] is False


def test_recall_round_1_check_mode_reports_drift_status(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    monkeypatch.setattr(
        module,
        "check_recall_round_1_output",
        lambda: (False, ["recall_round_1.output.overall_metrics.candidate_recall_at_20"]),
    )
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(
        module.sys,
        "argv",
        ["analyze_retrieval_v2_candidate_generation.py", "--recall-round-1", "--check"],
    )

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "recall_round_1_output_drifted"
    assert payload["differences"] == ["recall_round_1.output.overall_metrics.candidate_recall_at_20"]


def test_recall_round_2_plan_mode_does_not_build_main_analysis(monkeypatch, capsys) -> None:
    module = _load_cli_module()

    def fail_build() -> None:
        raise AssertionError("round 2 plan mode should not build the full candidate generation payload")

    monkeypatch.setattr(module, "build_candidate_generation_payload", fail_build)
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(module.sys, "argv", ["analyze_retrieval_v2_candidate_generation.py", "--recall-round-2"])

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["experiment_id"] == "retrieval_v2_candidate_recall_round_2"


def test_recall_round_2_write_mode_reports_round_status(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    fake_payload = {
        "round_2_metrics": {
            "candidate_recall_at_20": 1.0,
            "full_recall_case_count_at_20": 16,
        },
        "round_status": "passed_pending_integration_review",
        "success_gate": {"passed": True},
        "retriever_v2_status": "pending_hierarchical_integration_review",
    }
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(module, "build_recall_round_2_payload", lambda: fake_payload)
    monkeypatch.setattr(module, "write_recall_round_2_output", lambda payload: calls.append(payload))
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(
        module.sys,
        "argv",
        ["analyze_retrieval_v2_candidate_generation.py", "--recall-round-2", "--write"],
    )

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert calls == [fake_payload]
    assert payload["experiment"] == "recall_round_2"
    assert payload["round_status"] == "passed_pending_integration_review"
    assert payload["success_gate_passed"] is True


def test_recall_round_2_check_mode_reports_drift_status(monkeypatch, capsys) -> None:
    module = _load_cli_module()
    monkeypatch.setattr(
        module,
        "check_recall_round_2_output",
        lambda: (False, ["recall_round_2.output.round_2_metrics.candidate_recall_at_20"]),
    )
    monkeypatch.setattr(module, "sys", module.sys)
    monkeypatch.setattr(
        module.sys,
        "argv",
        ["analyze_retrieval_v2_candidate_generation.py", "--recall-round-2", "--check"],
    )

    exit_code = module.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "recall_round_2_output_drifted"
    assert payload["differences"] == ["recall_round_2.output.round_2_metrics.candidate_recall_at_20"]
