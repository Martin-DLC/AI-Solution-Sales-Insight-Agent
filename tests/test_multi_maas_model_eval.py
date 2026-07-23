from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agent.model_providers.base import ModelProviderResponse
from agent.model_providers.openai_compatible import MaaSProviderUsage
from evaluation.multi_maas.models import MultiMaaSEvaluationReport, MultiMaaSEvaluationResult
from evaluation.multi_maas.report import render_markdown_report
from evaluation.multi_maas.runner import MultiMaaSEvaluationRunner, load_cases, run_multi_maas_evaluation
from evaluation.multi_maas.scoring import score_output
from scripts import run_multi_maas_model_eval as cli


def test_seed_cases_load_and_cover_required_categories() -> None:
    cases = load_cases()

    assert len(cases) == 7
    assert {case.category for case in cases} >= {
        "requirement_summary",
        "pain_point_extraction",
        "ai_opportunity_identification",
        "solution_recommendation",
        "risk_and_fallback",
        "governance_sensitive_case",
    }
    assert all("benchmark gold" not in case.input_text.casefold() for case in cases)


def test_default_run_is_dry_run_and_does_not_create_quality_scores() -> None:
    report = run_multi_maas_evaluation(provider_name="cubexai", dry_run=True)

    assert report.dry_run is True
    assert report.summary.total_cases == 7
    assert report.summary.total_targets == 1
    assert report.summary.total_runs == 7
    assert report.summary.success_count == 0
    assert report.summary.skipped_count == 7
    assert {result.status for result in report.results} == {"skipped_dry_run"}
    assert all(result.answer_quality_score is None for result in report.results)
    assert all(result.evidence_grounding_score is None for result in report.results)


def test_missing_api_key_is_skipped_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GENERIC_MAAS_API_KEY", raising=False)
    report = run_multi_maas_evaluation(provider_name="generic_openai_compatible", dry_run=False)

    assert {result.status for result in report.results} == {"skipped_missing_api_key"}
    assert {result.error_type for result in report.results} == {"model_unavailable"}
    assert all(result.recommended_recovery_action == "fallback" for result in report.results)


def test_all_configured_targets_can_run_in_dry_run() -> None:
    report = run_multi_maas_evaluation(dry_run=True)

    assert report.summary.total_targets == 5
    assert report.summary.total_runs == 35
    assert report.summary.skipped_count == 35
    assert {target.verification_status for target in report.targets} == {"not_verified"}


def test_scoring_is_deterministic_and_heuristic() -> None:
    case = load_cases()[0]
    output = json.dumps(
        {
            "requirement_summary": "Improve conversion and handoff quality.",
            "pain_points": ["Manual qualification", "Slow customer success handoff"],
            "ai_opportunity_points": ["Lead scoring", "Account insight generation"],
        }
    )

    score = score_output(case, output)

    assert score.schema_valid is True
    assert all(score.expected_fields_present.values())
    assert score.answer_quality_score is not None
    assert "heuristic" in score.boundary_note


def test_success_path_scores_mocked_provider_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProvider:
        def generate(self, prompt: str, **kwargs: object) -> ModelProviderResponse:
            output = json.dumps(
                {
                    "requirement_summary": "Summarize AI sales insight need.",
                    "pain_points": ["Limited visibility"],
                    "ai_opportunity_points": ["Insight automation"],
                }
            )
            return ModelProviderResponse(
                provider_name="cubexai",
                model_name="fake-model",
                content=output,
                parsed_json={
                    "status": "success",
                    "output_text": output,
                    "latency_ms": 12,
                    "usage_available": True,
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                },
            )

    monkeypatch.setattr("evaluation.multi_maas.runner.build_openai_compatible_provider", lambda *_, **__: FakeProvider())
    report = run_multi_maas_evaluation(provider_name="cubexai", model_name="fake-model", dry_run=False)

    assert {result.status for result in report.results} == {"success"}
    assert report.summary.success_count == 7
    assert report.summary.skipped_count == 0
    assert report.summary.usage_available_rate == 1.0
    assert any(result.answer_quality_score is not None for result in report.results)


def test_timeout_status_gets_retry_recommendation(monkeypatch: pytest.MonkeyPatch) -> None:
    class TimeoutProvider:
        def generate(self, prompt: str, **kwargs: object) -> ModelProviderResponse:
            return ModelProviderResponse(
                provider_name="cubexai",
                model_name="fake-model",
                content="timeout",
                parsed_json={
                    "status": "failed",
                    "error_type": "model_timeout",
                    "error_message": "timeout",
                    "recommended_recovery_action": "retry",
                },
            )

    monkeypatch.setattr("evaluation.multi_maas.runner.build_openai_compatible_provider", lambda *_, **__: TimeoutProvider())
    report = run_multi_maas_evaluation(provider_name="cubexai", dry_run=False)

    assert {result.status for result in report.results} == {"timeout"}
    assert report.summary.retry_recommended_count == 7


def test_report_json_is_serializable() -> None:
    report = run_multi_maas_evaluation(provider_name="cubexai", dry_run=True)
    payload = report.model_dump(mode="json")

    assert json.loads(json.dumps(payload))["summary"]["skipped_count"] == 7
    MultiMaaSEvaluationReport.model_validate(payload)


def test_result_model_is_serializable() -> None:
    result = run_multi_maas_evaluation(provider_name="cubexai", dry_run=True).results[0]
    payload = result.model_dump(mode="json")

    assert payload["status"] == "skipped_dry_run"
    MultiMaaSEvaluationResult.model_validate(payload)


def test_markdown_report_contains_required_boundary_notes() -> None:
    markdown = render_markdown_report(run_multi_maas_evaluation(provider_name="cubexai", dry_run=True))

    assert "# Multi-MaaS Model Evaluation Report" in markdown
    assert "skipped_missing_api_key is not a model quality failure conclusion" in markdown
    assert "skipped_dry_run is not a model quality result" in markdown
    assert "estimated cost is not real billing" in markdown
    assert "production routing" in markdown


def test_cli_check_for_cubexai(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(["--provider", "cubexai", "--dry-run", "--check"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "multi_maas_model_eval_check_passed" in captured.out
    assert "skipped_dry_run" in captured.out


def test_cli_check_for_generic_provider(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(["--provider", "generic_openai_compatible", "--dry-run", "--check"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "multi_maas_model_eval_check_passed" in captured.out


def test_cli_check_all_targets(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(["--dry-run", "--check"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"total_targets": 5' in captured.out


def test_usage_model_is_reused_from_adapter() -> None:
    result = run_multi_maas_evaluation(provider_name="cubexai", dry_run=True).results[0]

    assert isinstance(result.usage, MaaSProviderUsage)


def test_multi_maas_write_paths_are_separate_from_frozen_artifacts() -> None:
    from evaluation.multi_maas import report as report_module

    assert str(report_module.JSON_REPORT_PATH) == "reports/multi_maas_model_eval.latest.json"
    assert str(report_module.MARKDOWN_REPORT_PATH) == "reports/multi_maas_model_eval.latest.md"


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
