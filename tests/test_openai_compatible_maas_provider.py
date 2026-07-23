from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agent.model_providers import OpenAICompatibleModelProvider, build_openai_compatible_provider
from agent.model_providers.openai_compatible import (
    MaaSProviderResult,
    get_maas_provider_config,
    load_maas_provider_configs,
)
from scripts import run_maas_provider_smoke_test as smoke_script


def test_can_build_openai_compatible_provider_from_config() -> None:
    provider = build_openai_compatible_provider("cubexai")

    assert isinstance(provider, OpenAICompatibleModelProvider)
    assert provider.provider_name == "cubexai"
    assert provider.model_name == "to_be_configured"
    assert provider.api_key_env == "CUBEXAI_API_KEY"
    assert provider.supports_structured_output is True


def test_missing_api_key_returns_skipped_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GENERIC_MAAS_API_KEY", raising=False)
    provider = build_openai_compatible_provider("generic_openai_compatible")

    result = provider.smoke_test(dry_run=False)

    assert result.status == "skipped_missing_api_key"
    assert result.error_type == "model_unavailable"
    assert result.should_retry is False
    assert result.should_fallback is True
    assert result.recommended_recovery_action == "fallback"


def test_dry_run_does_not_access_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GENERIC_MAAS_API_KEY", "unit-test-token")

    def fail_if_called(_: dict[str, object]) -> dict[str, object]:
        raise AssertionError("HTTP client should not be called in dry-run mode.")

    provider = build_openai_compatible_provider("generic_openai_compatible", http_client=fail_if_called)

    result = provider.smoke_test(dry_run=True)

    assert result.status == "skipped_dry_run"
    assert result.dry_run is True


def test_timeout_error_maps_to_model_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GENERIC_MAAS_API_KEY", "unit-test-token")

    def timeout(_: dict[str, object]) -> dict[str, object]:
        raise TimeoutError("request timed out")

    result = build_openai_compatible_provider("generic_openai_compatible", http_client=timeout).smoke_test(dry_run=False)

    assert result.status == "failed"
    assert result.error_type == "model_timeout"
    assert result.recommended_recovery_action == "retry"


def test_schema_invalid_maps_to_model_schema_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GENERIC_MAAS_API_KEY", "unit-test-token")

    def invalid_schema(_: dict[str, object]) -> dict[str, object]:
        return {"output_text": "not-json", "parsed_json": {}}

    result = build_openai_compatible_provider("generic_openai_compatible", http_client=invalid_schema).smoke_test(
        dry_run=False
    )

    assert result.status == "failed"
    assert result.error_type == "model_schema_invalid"
    assert result.schema_parse_status == "invalid"


def test_provider_unavailable_maps_to_model_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GENERIC_MAAS_API_KEY", "unit-test-token")

    def unavailable(_: dict[str, object]) -> dict[str, object]:
        raise ConnectionError("503 provider unavailable")

    result = build_openai_compatible_provider("generic_openai_compatible", http_client=unavailable).smoke_test(
        dry_run=False
    )

    assert result.status == "failed"
    assert result.error_type == "model_unavailable"


def test_unknown_exception_maps_to_unknown_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GENERIC_MAAS_API_KEY", "unit-test-token")

    def unknown(_: dict[str, object]) -> dict[str, object]:
        raise ValueError("unexpected local test failure")

    result = build_openai_compatible_provider("generic_openai_compatible", http_client=unknown).smoke_test(
        dry_run=False
    )

    assert result.status == "failed"
    assert result.error_type == "unknown_error"


def test_smoke_test_result_is_serializable() -> None:
    result = build_openai_compatible_provider("cubexai").smoke_test(dry_run=True)
    payload = result.model_dump(mode="json")

    assert json.loads(json.dumps(payload))["provider_name"] == "cubexai"
    MaaSProviderResult.model_validate(payload)


def test_smoke_test_report_json_can_be_generated() -> None:
    result = build_openai_compatible_provider("cubexai").smoke_test(dry_run=True)
    report = smoke_script.build_report(result)
    payload = report.model_dump(mode="json")

    assert payload["provider_name"] == "cubexai"
    assert payload["status"] == "skipped_dry_run"
    json.dumps(payload, ensure_ascii=False)


def test_smoke_test_markdown_can_be_generated() -> None:
    report = smoke_script.build_report(build_openai_compatible_provider("cubexai").smoke_test(dry_run=True))
    markdown = smoke_script.render_markdown_report(report)

    assert "# MaaS Provider Smoke Test Report" in markdown
    assert "not_verified" in markdown
    assert "not real billing" in markdown


def test_check_does_not_require_real_api_key(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("CUBEXAI_API_KEY", raising=False)

    exit_code = smoke_script.main(["--provider", "cubexai", "--dry-run", "--check"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "maas_provider_smoke_test_check_passed" in captured.out
    assert "skipped_dry_run" in captured.out


def test_all_maas_providers_are_not_verified() -> None:
    configs = load_maas_provider_configs()

    assert {config.provider_name for config in configs} == {
        "cubexai",
        "siliconflow",
        "aliyun_bailian",
        "openrouter",
        "generic_openai_compatible",
    }
    assert all(config.verification_status == "not_verified" for config in configs)


def test_cubexai_does_not_hardcode_verified_v1_base_url() -> None:
    config = get_maas_provider_config("cubexai")

    assert config.base_url is None
    assert config.base_url_candidate == "https://ai.lifangyun.com"
    assert not str(config.base_url_candidate).rstrip("/").endswith("/v1")
    assert config.verification_status == "not_verified"


def test_no_real_api_key_string_in_maas_provider_files() -> None:
    checked_paths = [
        Path("config/maas_providers.yaml"),
        Path("agent/model_providers/openai_compatible.py"),
        Path("scripts/run_maas_provider_smoke_test.py"),
        Path("docs/MAAS_PROVIDER_ONBOARDING.md"),
    ]

    for path in checked_paths:
        content = path.read_text(encoding="utf-8")
        assert "sk-" not in content
        assert "AIza" not in content


def test_generate_can_return_structured_skipped_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GENERIC_MAAS_API_KEY", raising=False)
    provider = build_openai_compatible_provider("generic_openai_compatible")

    response = provider.generate("hello", dry_run=False)

    assert response.parsed_json["status"] == "skipped_missing_api_key"
    assert response.parsed_json["error_type"] == "model_unavailable"
    assert response.provider_name == "generic_openai_compatible"


def test_deterministic_baseline_is_not_modified() -> None:
    changed = _git_changed_paths()

    assert "data/evaluation/llm/solution_insight_deterministic_baseline.v1.json" not in changed
    assert "data/evaluation/llm/solution_insight_model_comparison.v1.json" not in changed


def test_formal_retrieval_artifacts_are_not_modified() -> None:
    changed = _git_changed_paths()

    assert not any(path.startswith("data/evaluation/retrieval/") for path in changed)


def test_human_eval_artifacts_are_not_modified() -> None:
    changed = _git_changed_paths()

    assert not any(path.startswith("data/evaluation/human/") for path in changed)


def _git_changed_paths() -> set[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only"],
        check=True,
        capture_output=True,
        text=True,
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}
