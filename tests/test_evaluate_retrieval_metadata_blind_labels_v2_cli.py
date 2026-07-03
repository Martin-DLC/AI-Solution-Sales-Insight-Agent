from __future__ import annotations

import json

import scripts.evaluate_retrieval_metadata_blind_labels_v2 as cli
from evaluation.retrieval import metadata_blind_evaluation_v2 as module


def test_plan_mode_does_not_run_evaluation(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["evaluate_retrieval_metadata_blind_labels_v2.py"])

    def _unexpected() -> dict[str, object]:
        raise AssertionError("plan mode must not run evaluation")

    monkeypatch.setattr(cli, "run_blind_metadata_evaluation", _unexpected)

    exit_code = cli.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["mode"] == "plan"
    assert payload["writes_output_files"] is False
    assert payload["reads_gold_content"] is False


def test_plan_mode_supports_protocol_version_2_2(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "evaluate_retrieval_metadata_blind_labels_v2.py",
            "--protocol-version",
            "2.2",
            "--attempt-number",
            "2",
        ],
    )

    exit_code = cli.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["protocol_version"] == "2.2"
    assert payload["blind_attempt_number"] == 2
    assert payload["writes_output_files"] is False


def test_write_mode_writes_outputs(monkeypatch, tmp_path, capsys) -> None:
    json_path = tmp_path / "blind_eval.json"
    doc_path = tmp_path / "blind_eval.md"
    monkeypatch.setattr(module, "TRACKED_EVALUATION_OUTPUT_PATH", json_path)
    monkeypatch.setattr(module, "TRACKED_EVALUATION_DOC_PATH", doc_path)
    monkeypatch.setattr(cli.sys, "argv", ["evaluate_retrieval_metadata_blind_labels_v2.py", "--write"])

    exit_code = cli.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert json_path.exists()
    assert doc_path.exists()
    assert payload["mode"] == "write"
    assert payload["pair_count"] == 640
    assert payload["p0_validation_status"] == "failed"


def test_write_mode_supports_attempt_2(monkeypatch, tmp_path, capsys) -> None:
    json_path = tmp_path / "blind_eval_v2_2.json"
    doc_path = tmp_path / "blind_eval.md"
    monkeypatch.setattr(module, "TRACKED_EVALUATION_OUTPUT_PATH_V2_2", json_path)
    monkeypatch.setattr(module, "TRACKED_EVALUATION_DOC_PATH", doc_path)
    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "evaluate_retrieval_metadata_blind_labels_v2.py",
            "--protocol-version",
            "2.2",
            "--attempt-number",
            "2",
            "--write",
        ],
    )

    exit_code = cli.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert json_path.exists()
    assert doc_path.exists()
    assert payload["protocol_version"] == "2.2"
    assert payload["blind_attempt_number"] == 2
    assert payload["pair_count"] == 640
    assert payload["p0_validation_status"] == "failed"


def test_check_mode_is_stable_ignoring_generated_at(monkeypatch, tmp_path, capsys) -> None:
    json_path = tmp_path / "blind_eval.json"
    doc_path = tmp_path / "blind_eval.md"
    monkeypatch.setattr(module, "TRACKED_EVALUATION_OUTPUT_PATH", json_path)
    monkeypatch.setattr(module, "TRACKED_EVALUATION_DOC_PATH", doc_path)
    module.write_evaluation_outputs(module.run_blind_metadata_evaluation())
    monkeypatch.setattr(cli.sys, "argv", ["evaluate_retrieval_metadata_blind_labels_v2.py", "--check"])

    exit_code = cli.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["mode"] == "check"
    assert payload["status"] == "blind_label_evaluation_outputs_match"
    assert payload["differences"] == []


def test_attempt_2_check_mode_is_stable(monkeypatch, tmp_path, capsys) -> None:
    json_path = tmp_path / "blind_eval_v2_2.json"
    doc_path = tmp_path / "blind_eval.md"
    monkeypatch.setattr(module, "TRACKED_EVALUATION_OUTPUT_PATH_V2_2", json_path)
    monkeypatch.setattr(module, "TRACKED_EVALUATION_DOC_PATH", doc_path)
    module.write_evaluation_outputs(
        module.run_blind_metadata_evaluation(protocol_version="2.2", attempt_number=2)
    )
    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "evaluate_retrieval_metadata_blind_labels_v2.py",
            "--protocol-version",
            "2.2",
            "--attempt-number",
            "2",
            "--check",
        ],
    )

    exit_code = cli.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["mode"] == "check"
    assert payload["protocol_version"] == "2.2"
    assert payload["blind_attempt_number"] == 2
    assert payload["status"] == "blind_label_evaluation_outputs_match"
    assert payload["differences"] == []
