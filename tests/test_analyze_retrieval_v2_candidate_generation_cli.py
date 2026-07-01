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
