from __future__ import annotations

import json
import subprocess

import pytest

from agent.model_providers.base import ModelProviderResponse
from evaluation.multi_maas.recovery_summary import (
    RecoveryRecommendationSummary,
    build_recovery_recommendation_summary,
    classify_recovery_action,
)
from evaluation.multi_maas.report import render_markdown_report
from evaluation.multi_maas.runner import run_multi_maas_evaluation
from evaluation.multi_maas.selection import (
    ProviderSelectionRecommendation,
    build_provider_selection_recommendation,
    get_selection_policy,
    load_selection_policies,
)
from scripts import run_multi_maas_model_eval as cli


def test_selection_policies_load_as_evaluation_only() -> None:
    policies = load_selection_policies()

    assert {policy.policy_name for policy in policies} == {
        "conservative_eval_policy",
        "cost_sensitive_eval_policy",
        "reliability_sensitive_eval_policy",
    }
    assert all(policy.mode == "evaluation_only" for policy in policies)
    assert all(policy.not_production_routing is True for policy in policies)
    assert all(policy.recommendations_only is True for policy in policies)
    assert all(policy.metric_weights for policy in policies)


def test_unknown_selection_policy_raises() -> None:
    with pytest.raises(KeyError):
        get_selection_policy("missing_policy")


def test_all_dry_run_results_do_not_recommend_primary() -> None:
    report = run_multi_maas_evaluation(dry_run=True, policy_name="conservative_eval_policy")
    recommendation = ProviderSelectionRecommendation.model_validate(report.selection_recommendation)

    assert recommendation.recommendation_status == "skipped_all_targets"
    assert recommendation.primary_provider is None
    assert recommendation.fallback_provider is None
    assert recommendation.candidate_ranking
    assert "dry-run" in recommendation.selection_reason


def test_missing_api_key_results_do_not_recommend_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GENERIC_MAAS_API_KEY", raising=False)
    report = run_multi_maas_evaluation(
        provider_name="generic_openai_compatible",
        dry_run=False,
        policy_name="conservative_eval_policy",
    )
    recommendation = ProviderSelectionRecommendation.model_validate(report.selection_recommendation)

    assert recommendation.recommendation_status == "skipped_all_targets"
    assert recommendation.primary_provider is None
    assert {result.status for result in report.results} == {"skipped_missing_api_key"}


def test_successful_mock_results_can_recommend_primary_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProvider:
        def __init__(self, provider_name: str, model_name: str) -> None:
            self.provider_name = provider_name
            self.model_name = model_name

        def generate(self, prompt: str, **kwargs: object) -> ModelProviderResponse:
            output = json.dumps(
                {
                    "requirement_summary": "Summarize the sales insight need.",
                    "pain_points": ["Manual qualification"],
                    "ai_opportunity_points": ["Lead scoring"],
                    "solution_recommendation": "Use governed insight generation.",
                    "fallback_recommended": False,
                    "human_review_required": False,
                }
            )
            return ModelProviderResponse(
                provider_name=self.provider_name,
                model_name=self.model_name,
                content=output,
                parsed_json={
                    "status": "success",
                    "output_text": output,
                    "latency_ms": 10 if self.provider_name == "cubexai" else 20,
                    "usage_available": True,
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                },
            )

    def fake_builder(provider_name: str, **kwargs: object) -> FakeProvider:
        return FakeProvider(provider_name, str(kwargs.get("model_name") or "fake-model"))

    monkeypatch.setattr("evaluation.multi_maas.runner.build_openai_compatible_provider", fake_builder)
    report = run_multi_maas_evaluation(dry_run=False, policy_name="conservative_eval_policy")
    recommendation = ProviderSelectionRecommendation.model_validate(report.selection_recommendation)

    assert recommendation.recommendation_status == "recommended"
    assert recommendation.primary_provider is not None
    assert recommendation.fallback_provider is not None
    assert recommendation.primary_provider != recommendation.fallback_provider
    assert len(recommendation.candidate_ranking) == 5


def test_single_successful_provider_has_no_fallback_available(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProvider:
        def generate(self, prompt: str, **kwargs: object) -> ModelProviderResponse:
            output = json.dumps({"requirement_summary": "Need", "pain_points": [], "ai_opportunity_points": []})
            return ModelProviderResponse(
                provider_name="cubexai",
                model_name="fake-model",
                content=output,
                parsed_json={"status": "success", "output_text": output, "latency_ms": 1, "usage_available": False},
            )

    monkeypatch.setattr("evaluation.multi_maas.runner.build_openai_compatible_provider", lambda *_, **__: FakeProvider())
    report = run_multi_maas_evaluation(provider_name="cubexai", model_name="fake-model", dry_run=False)
    recommendation = ProviderSelectionRecommendation.model_validate(report.selection_recommendation)

    assert recommendation.recommendation_status == "no_fallback_available"
    assert recommendation.primary_provider == "cubexai"
    assert recommendation.fallback_provider is None


def test_recovery_summary_counts_dry_run_fallback_recommendations() -> None:
    report = run_multi_maas_evaluation(provider_name="cubexai", dry_run=True)
    summary = RecoveryRecommendationSummary.model_validate(report.recovery_summary)

    assert summary.total_results == 7
    assert summary.fallback_recommended_count == 7
    assert summary.retry_recommended_count == 0
    assert summary.per_provider_recovery_summary[0].provider_name == "cubexai"


def test_recovery_summary_counts_timeout_and_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    class TimeoutProvider:
        def generate(self, prompt: str, **kwargs: object) -> ModelProviderResponse:
            return ModelProviderResponse(
                provider_name="cubexai",
                model_name="fake-model",
                content="timeout",
                parsed_json={
                    "status": "failed",
                    "error_type": "model_timeout",
                    "recommended_recovery_action": "retry",
                },
            )

    monkeypatch.setattr("evaluation.multi_maas.runner.build_openai_compatible_provider", lambda *_, **__: TimeoutProvider())
    report = run_multi_maas_evaluation(provider_name="cubexai", dry_run=False)
    summary = build_recovery_recommendation_summary(report.results)

    assert summary.timeout_count == 7
    assert summary.retry_recommended_count == 7
    assert classify_recovery_action(report.results[0]) == "retry"


def test_markdown_report_includes_selection_and_recovery_sections() -> None:
    report = run_multi_maas_evaluation(provider_name="cubexai", dry_run=True)
    markdown = render_markdown_report(report)

    assert "## Provider Selection Recommendation" in markdown
    assert "## Candidate Ranking" in markdown
    assert "## Recovery Recommendation Summary" in markdown
    assert "evaluation-only recommendation" in markdown
    assert "Fallback provider recommendation is not production routing" in markdown
    assert "missing_api_key is not a model quality failure" in markdown


def test_cli_accepts_conservative_selection_policy(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(["--dry-run", "--check", "--selection-policy", "conservative_eval_policy"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "multi_maas_model_eval_check_passed" in captured.out
    assert "selection_recommendation" in captured.out


def test_cli_accepts_provider_and_reliability_policy(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(
        [
            "--provider",
            "generic_openai_compatible",
            "--dry-run",
            "--check",
            "--selection-policy",
            "reliability_sensitive_eval_policy",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "reliability_sensitive_eval_policy" in captured.out


def test_selection_recommendation_is_json_serializable() -> None:
    report = run_multi_maas_evaluation(provider_name="cubexai", dry_run=True)
    payload = ProviderSelectionRecommendation.model_validate(report.selection_recommendation).model_dump(mode="json")

    assert json.loads(json.dumps(payload))["recommendation_status"] == "skipped_all_targets"


def test_recovery_summary_is_json_serializable() -> None:
    report = run_multi_maas_evaluation(provider_name="cubexai", dry_run=True)
    payload = RecoveryRecommendationSummary.model_validate(report.recovery_summary).model_dump(mode="json")

    assert json.loads(json.dumps(payload))["fallback_recommended_count"] == 7


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
