from __future__ import annotations

from pathlib import Path

from agent.models import SolutionInsightRequest
from agent.observability import build_observation_snapshot, render_observation_report
from agent.solution_insight_service import SolutionInsightService
from scripts import run_solution_insight_observability_demo as demo_script


def _response(*, shadow: bool, company_id: str | None) -> object:
    service = SolutionInsightService.from_defaults(
        enable_shadow_retrieval=shadow,
        llm_mode="deterministic",
    )
    return service.generate_insight(
        SolutionInsightRequest(
            user_query="一家中型 SaaS 公司想提升销售线索转化和客户成功效率",
            company_id=company_id,
            industry="SaaS",
            enable_shadow_retrieval=shadow,
            llm_mode="deterministic",
        )
    )


def test_build_observation_snapshot_with_full_response() -> None:
    snapshot = build_observation_snapshot(_response(shadow=True, company_id="demo_saas_001"))

    assert snapshot.formal_path.evidence_titles
    assert snapshot.shadow_path.shadow_enabled is True
    assert snapshot.providers.provider_success_count == 4
    assert snapshot.skills.skill_count >= 1
    assert snapshot.fallback.fallback_recommended is True


def test_build_observation_snapshot_without_shadow_is_supported() -> None:
    snapshot = build_observation_snapshot(_response(shadow=False, company_id="demo_saas_001"))

    assert snapshot.shadow_path.shadow_enabled is False
    assert snapshot.shadow_path.shadow_candidate_count == 0


def test_build_observation_snapshot_without_enterprise_context_is_supported() -> None:
    snapshot = build_observation_snapshot(_response(shadow=True, company_id=None))

    assert snapshot.providers.provider_success_count == 0
    assert snapshot.input_summary.enterprise_context_present is False


def test_build_observation_snapshot_without_skill_trace_is_supported() -> None:
    response = _response(shadow=True, company_id="demo_saas_001")
    cloned = response.model_copy(update={"skill_trace": None})
    snapshot = build_observation_snapshot(cloned)

    assert snapshot.skills.skill_count == 0
    assert snapshot.skills.executed_skills == []


def test_snapshot_does_not_include_traceback_or_gold_or_case_id() -> None:
    snapshot = build_observation_snapshot(_response(shadow=True, company_id="demo_saas_001"))
    dumped = snapshot.model_dump_json()

    assert "traceback" not in dumped.casefold()
    assert "api_key" not in dumped.casefold()
    assert "gold" not in dumped.casefold()
    assert "case_id" not in dumped.casefold()


def test_markdown_report_contains_main_sections() -> None:
    report = render_observation_report(build_observation_snapshot(_response(shadow=True, company_id="demo_saas_001")))

    assert "# Solution Insight Observability Report" in report
    assert "## Formal Retrieval Path" in report
    assert "## Shadow Retrieval Path" in report
    assert "## Skill Execution Trace" in report
    assert "## Enterprise Context Providers" in report
    assert "## Fallback Assessment" in report
    assert "shadow_does_not_affect_formal_answer" in report


def test_demo_script_write_and_check(tmp_path: Path, monkeypatch) -> None:
    snapshot_path = tmp_path / "latest_solution_insight_snapshot.json"
    report_path = tmp_path / "latest_solution_insight_report.md"
    monkeypatch.setattr(demo_script, "SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(demo_script, "REPORT_PATH", report_path)

    assert demo_script.main(["--write"]) == 0
    assert snapshot_path.exists()
    assert report_path.exists()
    assert demo_script.main(["--check"]) == 0
