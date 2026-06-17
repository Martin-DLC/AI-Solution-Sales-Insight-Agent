from __future__ import annotations

from pathlib import Path

import pytest

from llm.config import LLMConfig
from llm.models import LLMResponse, LLMUsage
from scripts import run_baseline


class FakeClient:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error

    def list_model_ids(self) -> list[str]:
        return ["fake-model"]

    def complete_text(self, messages, *, temperature=None, max_tokens=None):
        if self.error:
            raise self.error
        return LLMResponse(
            content="普通文本分析结果",
            parsed_json=None,
            model="fake-model",
            response_id="resp_123",
            finish_reason="stop",
            usage=LLMUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
            latency_ms=9,
        )

    def complete_json(self, messages, *, temperature=None, max_tokens=None):
        raise AssertionError("Baseline A CLI must not call complete_json")


def make_config(api_key: str = "sk-test-secret") -> LLMConfig:
    return LLMConfig(api_key=api_key, base_url="https://api.example.com", model="fake-model")


def test_dry_run_returns_zero() -> None:
    assert run_baseline.main(["--case", "DEV-01", "--architecture", "A"]) == 0


def test_dry_run_does_not_create_llm_client(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_create_llm_client(config):
        nonlocal called
        called = True
        return FakeClient()

    monkeypatch.setattr(run_baseline, "create_llm_client", fake_create_llm_client)

    run_baseline.main(["--case", "DEV-01", "--architecture", "A"])

    assert called is False


def test_dry_run_does_not_create_run_directory(tmp_path: Path) -> None:
    output_root = tmp_path / "runs"

    result = run_baseline.main(
        ["--case", "DEV-01", "--architecture", "A", "--output-root", str(output_root)]
    )

    assert result == 0
    assert not output_root.exists()


def test_dry_run_outputs_prompt_sha256(capsys) -> None:
    run_baseline.main(["--case", "DEV-01", "--architecture", "A"])

    assert "Prompt SHA256:" in capsys.readouterr().out


def test_missing_case_returns_nonzero() -> None:
    assert run_baseline.main(["--case", "DEV-99", "--architecture", "A"]) == 1


def test_unsupported_architecture_returns_nonzero() -> None:
    assert run_baseline.main(["--case", "DEV-01", "--architecture", "Z"]) == 1


def test_live_success_path_uses_fake_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_baseline.LLMConfig, "from_env", lambda: make_config())
    monkeypatch.setattr(run_baseline, "create_llm_client", lambda config: FakeClient())

    result = run_baseline.main(
        [
            "--case",
            "DEV-01",
            "--architecture",
            "A",
            "--live",
            "--output-root",
            str(tmp_path),
        ]
    )

    assert result == 0
    assert any(tmp_path.iterdir())


def test_live_failure_path_returns_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_baseline.LLMConfig, "from_env", lambda: make_config("sk-test-secret"))
    monkeypatch.setattr(
        run_baseline,
        "create_llm_client",
        lambda config: FakeClient(error=RuntimeError("sk-test-secret request failed")),
    )

    result = run_baseline.main(
        [
            "--case",
            "DEV-01",
            "--architecture",
            "A",
            "--live",
            "--output-root",
            str(tmp_path),
        ]
    )

    assert result == 1


def test_output_does_not_contain_test_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setattr(run_baseline.LLMConfig, "from_env", lambda: make_config("sk-test-secret"))
    monkeypatch.setattr(
        run_baseline,
        "create_llm_client",
        lambda config: FakeClient(error=RuntimeError("sk-test-secret request failed")),
    )

    run_baseline.main(
        [
            "--case",
            "DEV-01",
            "--architecture",
            "A",
            "--live",
            "--output-root",
            str(tmp_path),
        ]
    )
    output = capsys.readouterr()

    assert "sk-test-secret" not in output.out
    assert "sk-test-secret" not in output.err


def test_cli_does_not_import_or_read_reference_pack() -> None:
    source = Path("scripts/run_baseline.py").read_text(encoding="utf-8")

    assert "load_reference_packs" not in source
    assert "development_reference" not in source


def test_architecture_b_dry_run_returns_zero() -> None:
    assert run_baseline.main(["--case", "DEV-01", "--architecture", "B"]) == 0


def test_b_dry_run_does_not_create_llm_client(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_create_llm_client(config):
        nonlocal called
        called = True
        return FakeClient()

    monkeypatch.setattr(run_baseline, "create_llm_client", fake_create_llm_client)

    run_baseline.main(["--case", "DEV-01", "--architecture", "B"])

    assert called is False


def test_b_dry_run_does_not_create_run_directory(tmp_path: Path) -> None:
    output_root = tmp_path / "runs"

    result = run_baseline.main(
        ["--case", "DEV-01", "--architecture", "B", "--output-root", str(output_root)]
    )

    assert result == 0
    assert not output_root.exists()


def test_b_dry_run_outputs_schema_version(capsys) -> None:
    run_baseline.main(["--case", "DEV-01", "--architecture", "B"])

    assert "JSON Schema version: 1.0" in capsys.readouterr().out


def test_b_v2_dry_run_returns_zero(capsys) -> None:
    result = run_baseline.main(
        ["--case", "DEV-01", "--architecture", "B", "--prompt-version", "baseline_b_v2"]
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "Prompt version: baseline_b_v2" in output


def test_b_v2_dry_run_does_not_create_llm_client(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_create_llm_client(config):
        nonlocal called
        called = True
        return FakeClient()

    monkeypatch.setattr(run_baseline, "create_llm_client", fake_create_llm_client)

    result = run_baseline.main(
        ["--case", "DEV-01", "--architecture", "B", "--prompt-version", "baseline_b_v2"]
    )

    assert result == 0
    assert called is False


def test_b_v2_dry_run_does_not_create_run_directory(tmp_path: Path) -> None:
    output_root = tmp_path / "runs"

    result = run_baseline.main(
        [
            "--case",
            "DEV-01",
            "--architecture",
            "B",
            "--prompt-version",
            "baseline_b_v2",
            "--output-root",
            str(output_root),
        ]
    )

    assert result == 0
    assert not output_root.exists()


def test_b_v3_dry_run_returns_zero(capsys) -> None:
    result = run_baseline.main(
        ["--case", "DEV-01", "--architecture", "B", "--prompt-version", "baseline_b_v3"]
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "Prompt version: baseline_b_v3" in output


def test_b_v3_dry_run_does_not_create_llm_client(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_create_llm_client(config):
        nonlocal called
        called = True
        return FakeClient()

    monkeypatch.setattr(run_baseline, "create_llm_client", fake_create_llm_client)

    result = run_baseline.main(
        ["--case", "DEV-01", "--architecture", "B", "--prompt-version", "baseline_b_v3"]
    )

    assert result == 0
    assert called is False


def test_b_v3_dry_run_does_not_create_run_directory(tmp_path: Path) -> None:
    output_root = tmp_path / "runs"

    result = run_baseline.main(
        [
            "--case",
            "DEV-01",
            "--architecture",
            "B",
            "--prompt-version",
            "baseline_b_v3",
            "--output-root",
            str(output_root),
        ]
    )

    assert result == 0
    assert not output_root.exists()


def test_unknown_prompt_version_returns_nonzero() -> None:
    assert (
        run_baseline.main(
            ["--case", "DEV-01", "--architecture", "B", "--prompt-version", "baseline_b_unknown"]
        )
        == 1
    )


def test_b_v1_dry_run_still_works(capsys) -> None:
    result = run_baseline.main(
        ["--case", "DEV-01", "--architecture", "B", "--prompt-version", "baseline_b_v1"]
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "Prompt version: baseline_b_v1" in output


def test_b_v2_dry_run_still_works(capsys) -> None:
    result = run_baseline.main(
        ["--case", "DEV-01", "--architecture", "B", "--prompt-version", "baseline_b_v2"]
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "Prompt version: baseline_b_v2" in output


def test_b_live_success_path_uses_fake_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_baseline_b_runner import FakeStructuredLLMClient

    monkeypatch.setattr(run_baseline.LLMConfig, "from_env", lambda: make_config())
    monkeypatch.setattr(run_baseline, "create_llm_client", lambda config: FakeStructuredLLMClient())

    result = run_baseline.main(
        [
            "--case",
            "DEV-01",
            "--architecture",
            "B",
            "--live",
            "--output-root",
            str(tmp_path),
        ]
    )

    assert result == 0


def test_b_schema_failure_returns_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_baseline_b_runner import FakeStructuredLLMClient, invalid_report_payload

    monkeypatch.setattr(run_baseline.LLMConfig, "from_env", lambda: make_config())
    monkeypatch.setattr(
        run_baseline,
        "create_llm_client",
        lambda config: FakeStructuredLLMClient(payload=invalid_report_payload()),
    )

    result = run_baseline.main(
        [
            "--case",
            "DEV-01",
            "--architecture",
            "B",
            "--live",
            "--output-root",
            str(tmp_path),
        ]
    )

    assert result == 1


def test_a_dry_run_still_works() -> None:
    assert run_baseline.main(["--case", "DEV-01", "--architecture", "A"]) == 0


def test_unsupported_architecture_still_returns_nonzero() -> None:
    assert run_baseline.main(["--case", "DEV-01", "--architecture", "Z"]) == 1


def test_cli_still_does_not_read_reference_pack() -> None:
    source = Path("scripts/run_baseline.py").read_text(encoding="utf-8")

    assert "load_reference_packs" not in source
    assert "development_reference" not in source


def test_b_output_does_not_contain_test_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    from tests.test_baseline_b_runner import FakeStructuredLLMClient

    monkeypatch.setattr(run_baseline.LLMConfig, "from_env", lambda: make_config("sk-test-secret"))
    monkeypatch.setattr(
        run_baseline,
        "create_llm_client",
        lambda config: FakeStructuredLLMClient(error=RuntimeError("sk-test-secret request failed")),
    )

    run_baseline.main(
        [
            "--case",
            "DEV-01",
            "--architecture",
            "B",
            "--live",
            "--output-root",
            str(tmp_path),
        ]
    )
    output = capsys.readouterr()

    assert "sk-test-secret" not in output.out
    assert "sk-test-secret" not in output.err
