from __future__ import annotations

import json
from pathlib import Path

import pytest

from dataio.runtime_cases import load_runtime_cases
from evaluation.baselines.runner import BaselineARunner
from llm.config import LLMConfig
from llm.models import LLMResponse, LLMUsage


class FakeLLMClient:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.complete_text_calls = 0
        self.complete_json_calls = 0

    def list_model_ids(self) -> list[str]:
        return ["fake-model"]

    def complete_text(self, messages, *, temperature=None, max_tokens=None):
        self.complete_text_calls += 1
        if self.error:
            raise self.error
        return LLMResponse(
            content="普通文本分析结果",
            parsed_json=None,
            model="fake-model",
            response_id="resp_123",
            finish_reason="stop",
            usage=LLMUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            latency_ms=15,
        )

    def complete_json(self, messages, *, temperature=None, max_tokens=None):
        self.complete_json_calls += 1
        raise AssertionError("Baseline A must not call complete_json")


def make_config(api_key: str = "sk-test-secret") -> LLMConfig:
    return LLMConfig(api_key=api_key, base_url="https://api.example.com", model="fake-model")


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def run_success(tmp_path: Path, fake_client: FakeLLMClient | None = None):
    client = fake_client or FakeLLMClient()
    runner = BaselineARunner(client, make_config(), output_root=tmp_path)
    record = runner.run_case(dev_01_case())
    return record, client


def test_success_run_creates_independent_directory(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)

    assert Path(record.output_directory).is_dir()


def test_success_run_creates_input_case_json(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)

    assert Path(record.input_file).name == "input_case.json"
    assert Path(record.input_file).exists()


def test_success_run_creates_rendered_prompt(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)

    assert Path(record.prompt_file).name == "rendered_prompt.txt"
    assert Path(record.prompt_file).exists()


def test_success_run_creates_raw_response(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)

    assert record.raw_response_file is not None
    assert Path(record.raw_response_file).read_text(encoding="utf-8") == "普通文本分析结果"


def test_success_run_creates_metadata(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)

    metadata_path = Path(record.output_directory) / "run_metadata.json"
    assert metadata_path.exists()


def test_metadata_status_is_success(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)
    metadata = json.loads((Path(record.output_directory) / "run_metadata.json").read_text(encoding="utf-8"))

    assert metadata["status"] == "success"


def test_metadata_records_prompt_sha256(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)

    assert len(record.prompt_sha256) == 64


def test_metadata_records_token_usage(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)

    assert record.usage.total_tokens == 30


def test_metadata_does_not_contain_test_api_key(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)
    metadata = (Path(record.output_directory) / "run_metadata.json").read_text(encoding="utf-8")

    assert "sk-test-secret" not in metadata


def test_runner_calls_complete_text_once(tmp_path: Path) -> None:
    fake_client = FakeLLMClient()
    run_success(tmp_path, fake_client)

    assert fake_client.complete_text_calls == 1


def test_runner_does_not_call_complete_json(tmp_path: Path) -> None:
    fake_client = FakeLLMClient()
    run_success(tmp_path, fake_client)

    assert fake_client.complete_json_calls == 0


def test_runner_does_not_read_reference_pack() -> None:
    source = Path("evaluation/baselines/runner.py").read_text(encoding="utf-8")

    assert "load_reference_packs" not in source
    assert "development_reference" not in source


def test_two_runs_generate_different_run_ids(tmp_path: Path) -> None:
    first, _ = run_success(tmp_path)
    second, _ = run_success(tmp_path)

    assert first.run_id != second.run_id


def test_failure_saves_failed_metadata(tmp_path: Path) -> None:
    runner = BaselineARunner(
        FakeLLMClient(error=RuntimeError("request failed")),
        make_config(),
        output_root=tmp_path,
    )

    record = runner.run_case(dev_01_case())

    assert record.status.value == "failed"
    metadata = json.loads((Path(record.output_directory) / "run_metadata.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "failed"


def test_failure_does_not_create_fake_raw_response(tmp_path: Path) -> None:
    runner = BaselineARunner(
        FakeLLMClient(error=RuntimeError("request failed")),
        make_config(),
        output_root=tmp_path,
    )

    record = runner.run_case(dev_01_case())

    assert record.raw_response_file is None
    assert not (Path(record.output_directory) / "raw_response.txt").exists()


def test_git_commit_read_failure_does_not_stop_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("evaluation.baselines.runner._read_git_commit", lambda: None)

    record, _ = run_success(tmp_path)

    assert record.git_commit is None


def test_output_directory_can_be_customized(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path / "custom-root")

    assert "custom-root" in record.output_directory


def test_saved_files_are_utf8_readable(tmp_path: Path) -> None:
    record, _ = run_success(tmp_path)

    assert "DEV-01" in Path(record.input_file).read_text(encoding="utf-8")
    assert "客户资料" in Path(record.prompt_file).read_text(encoding="utf-8")
