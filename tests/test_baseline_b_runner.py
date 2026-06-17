from __future__ import annotations

import json
from pathlib import Path

import pytest

from dataio.runtime_cases import load_runtime_cases
from evaluation.baselines.b_runner import BaselineBRunner
from llm.config import LLMConfig
from llm.errors import LLMJSONDecodeError
from llm.models import LLMResponse, LLMUsage


class FakeStructuredLLMClient:
    def __init__(self, *, payload: dict | None = None, error: Exception | None = None) -> None:
        self.payload = payload if payload is not None else valid_report_payload()
        self.error = error
        self.complete_json_calls = 0
        self.complete_text_calls = 0

    def list_model_ids(self) -> list[str]:
        return ["fake-model"]

    def complete_json(self, messages, *, temperature=None, max_tokens=None):
        self.complete_json_calls += 1
        if self.error:
            raise self.error
        content = json.dumps(self.payload, ensure_ascii=False)
        return LLMResponse(
            content=content,
            parsed_json=self.payload,
            model="fake-model",
            response_id="resp_123",
            finish_reason="stop",
            usage=LLMUsage(prompt_tokens=11, completion_tokens=22, total_tokens=33),
            latency_ms=17,
        )

    def complete_text(self, messages, *, temperature=None, max_tokens=None):
        self.complete_text_calls += 1
        raise AssertionError("Baseline B must not call complete_text")


def valid_report_payload() -> dict:
    return json.loads(Path("tests/fixtures/dev_01_full_report.json").read_text(encoding="utf-8"))


def invalid_report_payload() -> dict:
    payload = valid_report_payload()
    payload["case_id"] = "DEV-1"
    return payload


def make_config(api_key: str = "sk-test-secret") -> LLMConfig:
    return LLMConfig(api_key=api_key, base_url="https://api.example.com", model="fake-model")


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def run_success(tmp_path: Path, fake_client: FakeStructuredLLMClient | None = None):
    client = fake_client or FakeStructuredLLMClient()
    runner = BaselineBRunner(client, make_config(), output_root=tmp_path)
    record = runner.run_case(dev_01_case())
    return record, client


def test_success_run_creates_independent_b_directory(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)

    assert Path(record.output_directory).is_dir()
    assert record.run_id.startswith("B-DEV-01-")


def test_success_run_saves_input_case_json(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)

    assert Path(record.input_file).exists()


def test_success_run_saves_system_prompt(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)

    assert Path(record.system_prompt_file).exists()


def test_success_run_saves_user_prompt(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)

    assert Path(record.user_prompt_file).exists()


def test_success_run_saves_raw_response_json(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)

    assert record.raw_response_file is not None
    assert Path(record.raw_response_file).exists()


def test_success_run_saves_parsed_report_json(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)

    assert record.parsed_report_file is not None
    assert Path(record.parsed_report_file).exists()


def test_success_run_saves_metadata(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)

    assert (Path(record.output_directory) / "run_metadata.json").exists()


def test_metadata_status_is_success(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)
    metadata = json.loads((Path(record.output_directory) / "run_metadata.json").read_text(encoding="utf-8"))

    assert metadata["status"] == "success"


def test_metadata_contains_schema_version(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)

    assert record.schema_version == "1.0"


def test_runner_calls_complete_json_once(tmp_path: Path) -> None:
    client = FakeStructuredLLMClient()
    run_success(tmp_path, client)

    assert client.complete_json_calls == 1


def test_runner_does_not_call_complete_text(tmp_path: Path) -> None:
    client = FakeStructuredLLMClient()
    run_success(tmp_path, client)

    assert client.complete_text_calls == 0


def test_valid_sales_insight_report_passes_validation(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)

    assert record.status.value == "success"


def test_parsed_report_json_comes_from_pydantic_dump(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)
    parsed = json.loads(Path(record.parsed_report_file).read_text(encoding="utf-8"))

    assert parsed["schema_version"] == "1.0"
    assert parsed["generated_at"] == "2026-06-16T10:30:00Z"


def test_two_runs_generate_different_run_ids(tmp_path: Path) -> None:
    first, _ = run_success(tmp_path)
    second, _ = run_success(tmp_path)

    assert first.run_id != second.run_id


def test_pydantic_failure_saves_validation_error_json(tmp_path: Path) -> None:
    runner = BaselineBRunner(
        FakeStructuredLLMClient(payload=invalid_report_payload()),
        make_config(),
        output_root=tmp_path,
    )

    record = runner.run_case(dev_01_case())

    assert record.validation_error_file is not None
    assert Path(record.validation_error_file).exists()


def test_pydantic_failure_does_not_save_parsed_report(tmp_path: Path) -> None:
    runner = BaselineBRunner(
        FakeStructuredLLMClient(payload=invalid_report_payload()),
        make_config(),
        output_root=tmp_path,
    )

    record = runner.run_case(dev_01_case())

    assert record.parsed_report_file is None
    assert not (Path(record.output_directory) / "parsed_report.json").exists()


def test_pydantic_failure_metadata_status_failed(tmp_path: Path) -> None:
    runner = BaselineBRunner(
        FakeStructuredLLMClient(payload=invalid_report_payload()),
        make_config(),
        output_root=tmp_path,
    )

    record = runner.run_case(dev_01_case())

    assert record.status.value == "failed"


def test_pydantic_failure_metadata_uses_schema_validation_error_type(tmp_path: Path) -> None:
    runner = BaselineBRunner(
        FakeStructuredLLMClient(payload=invalid_report_payload()),
        make_config(),
        output_root=tmp_path,
    )

    record = runner.run_case(dev_01_case())
    metadata = json.loads((Path(record.output_directory) / "run_metadata.json").read_text(encoding="utf-8"))

    assert metadata["error_type"] == "schema_validation"
    assert metadata["validation_error_file"].endswith("validation_error.json")
    assert metadata["json_parse_error_file"] is None


def test_api_failure_saves_failed_metadata(tmp_path: Path) -> None:
    runner = BaselineBRunner(
        FakeStructuredLLMClient(error=RuntimeError("request failed")),
        make_config(),
        output_root=tmp_path,
    )

    record = runner.run_case(dev_01_case())

    assert record.status.value == "failed"
    assert (Path(record.output_directory) / "run_metadata.json").exists()


def test_json_failure_saves_raw_response_txt(tmp_path: Path) -> None:
    raw_content = "```json\nnot valid\n```"
    runner = BaselineBRunner(
        FakeStructuredLLMClient(
            error=LLMJSONDecodeError(
                raw_content=raw_content,
                json_error_message="Expecting value",
                json_error_position=0,
            )
        ),
        make_config(),
        output_root=tmp_path,
    )

    record = runner.run_case(dev_01_case())

    assert record.raw_response_file is not None
    assert Path(record.raw_response_file).name == "raw_response.txt"
    assert Path(record.raw_response_file).read_text(encoding="utf-8") == raw_content


def test_json_failure_saves_json_parse_error_json(tmp_path: Path) -> None:
    runner = BaselineBRunner(
        FakeStructuredLLMClient(
            error=LLMJSONDecodeError(
                raw_content="not json",
                json_error_message="Expecting value",
                json_error_position=0,
            )
        ),
        make_config(),
        output_root=tmp_path,
    )

    record = runner.run_case(dev_01_case())
    payload = json.loads(Path(record.json_parse_error_file).read_text(encoding="utf-8"))

    assert payload == {
        "error_type": "invalid_json",
        "content_length": 8,
        "json_error_message": "Expecting value",
        "json_error_position": 0,
        "case_id": "DEV-01",
        "schema_version": "1.0",
    }


def test_empty_json_failure_saves_zero_length_diagnostic(tmp_path: Path) -> None:
    runner = BaselineBRunner(
        FakeStructuredLLMClient(
            error=LLMJSONDecodeError(
                raw_content="",
                json_error_message="Expecting value",
                json_error_position=0,
            )
        ),
        make_config(),
        output_root=tmp_path,
    )

    record = runner.run_case(dev_01_case())
    payload = json.loads(Path(record.json_parse_error_file).read_text(encoding="utf-8"))

    assert payload["content_length"] == 0
    assert Path(record.raw_response_file).read_text(encoding="utf-8") == ""


def test_json_failure_does_not_save_parsed_report_or_validation_error(tmp_path: Path) -> None:
    runner = BaselineBRunner(
        FakeStructuredLLMClient(
            error=LLMJSONDecodeError(
                raw_content="not json",
                json_error_message="Expecting value",
                json_error_position=0,
            )
        ),
        make_config(),
        output_root=tmp_path,
    )

    record = runner.run_case(dev_01_case())

    assert record.parsed_report_file is None
    assert record.validation_error_file is None
    assert not (Path(record.output_directory) / "parsed_report.json").exists()
    assert not (Path(record.output_directory) / "validation_error.json").exists()


def test_json_failure_metadata_is_distinct_from_schema_validation(tmp_path: Path) -> None:
    runner = BaselineBRunner(
        FakeStructuredLLMClient(
            error=LLMJSONDecodeError(
                raw_content="not json",
                json_error_message="Expecting value",
                json_error_position=0,
            )
        ),
        make_config(),
        output_root=tmp_path,
    )

    record = runner.run_case(dev_01_case())
    metadata = json.loads((Path(record.output_directory) / "run_metadata.json").read_text(encoding="utf-8"))

    assert metadata["status"] == "failed"
    assert metadata["error_type"] == "invalid_json"
    assert metadata["json_parse_error_file"].endswith("json_parse_error.json")
    assert metadata["validation_error_file"] is None


def test_api_failure_without_content_does_not_save_raw_response(tmp_path: Path) -> None:
    runner = BaselineBRunner(
        FakeStructuredLLMClient(error=RuntimeError("request failed")),
        make_config(),
        output_root=tmp_path,
    )

    record = runner.run_case(dev_01_case())

    assert record.raw_response_file is None
    assert not (Path(record.output_directory) / "raw_response.txt").exists()
    assert not (Path(record.output_directory) / "raw_response.json").exists()


def test_runner_does_not_read_reference_pack() -> None:
    source = Path("evaluation/baselines/b_runner.py").read_text(encoding="utf-8")

    assert "load_reference_packs" not in source
    assert "development_reference" not in source


def test_metadata_and_error_files_do_not_contain_test_api_key(tmp_path: Path) -> None:
    runner = BaselineBRunner(
        FakeStructuredLLMClient(error=RuntimeError("sk-test-secret request failed")),
        make_config("sk-test-secret"),
        output_root=tmp_path,
    )

    record = runner.run_case(dev_01_case())
    metadata = (Path(record.output_directory) / "run_metadata.json").read_text(encoding="utf-8")

    assert "sk-test-secret" not in metadata


def test_git_commit_read_failure_does_not_stop_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("evaluation.baselines.b_runner._read_git_commit", lambda: None)

    record, _ = run_success(tmp_path)

    assert record.git_commit is None


def test_custom_output_root_is_used(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path / "custom-root")

    assert "custom-root" in record.output_directory
