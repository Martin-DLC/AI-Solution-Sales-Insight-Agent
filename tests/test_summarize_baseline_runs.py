from __future__ import annotations

import json
from pathlib import Path

from scripts.summarize_baseline_runs import main, summarize_runs


def write_run(
    root: Path,
    name: str,
    *,
    architecture: str,
    status: str,
    started_at: str,
    case_id: str = "DEV-01",
    prompt_version: str = "baseline_a_v1",
    error_type: str | None = None,
    validation_error_count: int | None = None,
    invalid_json: bool = False,
    parsed_report: bool = False,
    secret: str | None = None,
) -> Path:
    run_dir = root / name
    run_dir.mkdir(parents=True)
    metadata = {
        "run_id": name,
        "architecture": architecture,
        "case_id": case_id,
        "prompt_version": prompt_version,
        "model": "fake-model",
        "status": status,
        "started_at": started_at,
        "latency_ms": 123,
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        "error_type": error_type,
        "error_message": secret,
        "output_directory": str(run_dir),
    }
    (run_dir / "run_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    if validation_error_count is not None:
        errors = [{"loc": ["field", index], "msg": "failed"} for index in range(validation_error_count)]
        (run_dir / "validation_error.json").write_text(
            json.dumps({"error_count": validation_error_count, "errors": errors}),
            encoding="utf-8",
        )
    if invalid_json:
        (run_dir / "json_parse_error.json").write_text(
            json.dumps(
                {
                    "error_type": "invalid_json",
                    "content_length": 10,
                    "json_error_message": "Expecting value",
                    "json_error_position": 0,
                }
            ),
            encoding="utf-8",
        )
    if parsed_report:
        (run_dir / "parsed_report.json").write_text("{}", encoding="utf-8")
    return run_dir


def test_summarizes_architecture_a_success_record(tmp_path: Path) -> None:
    write_run(tmp_path, "run-a", architecture="A", status="success", started_at="2026-01-01T00:00:00Z")

    records = summarize_runs(tmp_path)["records"]

    assert records[0]["architecture"] == "A"
    assert records[0]["status"] == "success"


def test_summarizes_invalid_json_record(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        "run-json",
        architecture="B",
        status="failed",
        started_at="2026-01-01T00:00:00Z",
        prompt_version="baseline_b_v1",
        error_type="invalid_json",
        invalid_json=True,
    )

    record = summarize_runs(tmp_path)["records"][0]

    assert record["error_type"] == "invalid_json"


def test_summarizes_schema_validation_record(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        "run-schema",
        architecture="B",
        status="failed",
        started_at="2026-01-01T00:00:00Z",
        prompt_version="baseline_b_v2",
        error_type="schema_validation",
        validation_error_count=2,
    )

    record = summarize_runs(tmp_path)["records"][0]

    assert record["error_type"] == "schema_validation"


def test_summarizes_schema_success_record(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        "run-success",
        architecture="B",
        status="success",
        started_at="2026-01-01T00:00:00Z",
        prompt_version="baseline_b_v3",
        parsed_report=True,
    )

    record = summarize_runs(tmp_path)["records"][0]

    assert record["schema_success"] is True


def test_invalid_json_is_marked_json_success_false(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        "run-json",
        architecture="B",
        status="failed",
        started_at="2026-01-01T00:00:00Z",
        error_type="invalid_json",
        invalid_json=True,
    )

    record = summarize_runs(tmp_path)["records"][0]

    assert record["json_success"] is False


def test_schema_validation_marks_json_true_schema_false(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        "run-schema",
        architecture="B",
        status="failed",
        started_at="2026-01-01T00:00:00Z",
        error_type="schema_validation",
        validation_error_count=1,
    )

    record = summarize_runs(tmp_path)["records"][0]

    assert record["json_success"] is True
    assert record["schema_success"] is False


def test_success_report_is_marked_schema_success_true(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        "run-success",
        architecture="B",
        status="success",
        started_at="2026-01-01T00:00:00Z",
        parsed_report=True,
    )

    record = summarize_runs(tmp_path)["records"][0]

    assert record["json_success"] is True
    assert record["schema_success"] is True


def test_architecture_a_json_and_schema_results_are_null(tmp_path: Path) -> None:
    write_run(tmp_path, "run-a", architecture="A", status="success", started_at="2026-01-01T00:00:00Z")

    record = summarize_runs(tmp_path)["records"][0]

    assert record["json_success"] is None
    assert record["schema_success"] is None


def test_extracts_validation_error_count(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        "run-schema",
        architecture="B",
        status="failed",
        started_at="2026-01-01T00:00:00Z",
        error_type="schema_validation",
        validation_error_count=3,
    )

    record = summarize_runs(tmp_path)["records"][0]

    assert record["validation_error_count"] == 3


def test_records_are_sorted_by_started_at(tmp_path: Path) -> None:
    write_run(tmp_path, "late", architecture="A", status="success", started_at="2026-01-02T00:00:00Z")
    write_run(tmp_path, "early", architecture="A", status="success", started_at="2026-01-01T00:00:00Z")

    records = summarize_runs(tmp_path)["records"]

    assert [record["run_id"] for record in records] == ["early", "late"]


def test_broken_metadata_does_not_stop_all_summary(tmp_path: Path) -> None:
    write_run(tmp_path, "good", architecture="A", status="success", started_at="2026-01-01T00:00:00Z")
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "run_metadata.json").write_text("{not-json", encoding="utf-8")

    summary = summarize_runs(tmp_path)

    assert len(summary["records"]) == 1
    assert summary["warnings"]


def test_output_does_not_include_raw_response_content(tmp_path: Path, capsys) -> None:
    run_dir = write_run(tmp_path, "run-a", architecture="A", status="success", started_at="2026-01-01T00:00:00Z")
    (run_dir / "raw_response.txt").write_text("RAW CUSTOMER RESPONSE", encoding="utf-8")

    main(["--runs-root", str(tmp_path)])

    assert "RAW CUSTOMER RESPONSE" not in capsys.readouterr().out


def test_output_does_not_include_prompt_content(tmp_path: Path, capsys) -> None:
    run_dir = write_run(tmp_path, "run-a", architecture="A", status="success", started_at="2026-01-01T00:00:00Z")
    (run_dir / "system_prompt.txt").write_text("PROMPT SECRET CONTENT", encoding="utf-8")

    main(["--runs-root", str(tmp_path)])

    assert "PROMPT SECRET CONTENT" not in capsys.readouterr().out


def test_output_does_not_include_test_api_key(tmp_path: Path, capsys) -> None:
    write_run(
        tmp_path,
        "run-a",
        architecture="A",
        status="failed",
        started_at="2026-01-01T00:00:00Z",
        error_type="LLMRequestError",
        secret="sk-test-secret",
    )

    main(["--runs-root", str(tmp_path)])

    output = capsys.readouterr()
    assert "sk-test-secret" not in output.out


def test_case_filter_works(tmp_path: Path) -> None:
    write_run(tmp_path, "dev-01", architecture="A", status="success", started_at="2026-01-01T00:00:00Z")
    write_run(
        tmp_path,
        "dev-04",
        architecture="A",
        status="success",
        started_at="2026-01-02T00:00:00Z",
        case_id="DEV-04",
    )

    records = summarize_runs(tmp_path, case_id="DEV-04")["records"]

    assert [record["case_id"] for record in records] == ["DEV-04"]


def test_architecture_filter_works(tmp_path: Path) -> None:
    write_run(tmp_path, "run-a", architecture="A", status="success", started_at="2026-01-01T00:00:00Z")
    write_run(tmp_path, "run-b", architecture="B", status="success", started_at="2026-01-02T00:00:00Z")

    records = summarize_runs(tmp_path, architecture="B")["records"]

    assert [record["architecture"] for record in records] == ["B"]


def test_output_json_writes_valid_json(tmp_path: Path) -> None:
    output_path = tmp_path / "summary.json"
    write_run(tmp_path / "runs", "run-a", architecture="A", status="success", started_at="2026-01-01T00:00:00Z")

    result = main(["--runs-root", str(tmp_path / "runs"), "--output-json", str(output_path)])

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert result == 0
    assert payload["records"][0]["run_id"] == "run-a"
