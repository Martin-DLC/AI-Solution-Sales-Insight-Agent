from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.models import (
    SolutionInsightEvidenceItem,
    SolutionInsightRequest,
    SolutionInsightResponse,
    SolutionInsightRetrievalDebug,
    SolutionInsightShadowDebug,
)
from evaluation.llm import (
    check_baseline,
    check_provider_comparison,
    load_eval_cases,
    run_evaluation,
    run_provider_comparison,
    write_baseline,
    write_provider_comparison,
)
from evaluation.llm.evaluator import evaluate_solution_insight_response
from evaluation.llm.models import SolutionInsightEvalCase
from scripts.run_solution_insight_llm_eval import main


class FakeService:
    def __init__(self, *, response: SolutionInsightResponse) -> None:
        self._response = response
        self.requests: list[SolutionInsightRequest] = []

    def generate_insight(self, request: SolutionInsightRequest) -> SolutionInsightResponse:
        self.requests.append(request)
        return self._response


class FakeLiveResponse:
    def __init__(self, *, parsed_json: dict[str, object], latency_ms: int = 123) -> None:
        self.parsed_json = parsed_json
        self.latency_ms = latency_ms
        self.usage = type(
            "Usage",
            (),
            {"model_dump": lambda self, mode="json": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}},
        )()


class FakeLiveClient:
    def __init__(self, *, parsed_json: dict[str, object]) -> None:
        self.parsed_json = parsed_json
        self.calls = 0

    def complete_json(self, messages):  # noqa: ANN001
        self.calls += 1
        return FakeLiveResponse(parsed_json=self.parsed_json)


def _build_case(**overrides: object) -> SolutionInsightEvalCase:
    payload = {
        "case_id": "CASE-001",
        "user_query": "一家中型 SaaS 公司想提升销售线索转化和客户成功效率。",
        "industry": "SaaS",
        "company_size": "中型",
        "current_systems": ["CRM"],
        "target_goal": "提升转化",
        "constraints": ["不改变现有CRM主流程"],
        "expected_focus_areas": ["销售转化"],
        "required_output_sections": [
            "requirement_summary",
            "pain_points",
            "ai_opportunity_points",
            "proposed_solution",
            "evidence_items",
            "fallback_recommended",
            "fallback_reasons",
            "human_confirmation_required",
            "retrieval_debug",
        ],
        "expected_fallback_behavior": True,
        "forbidden_claims": ["ROI提升40%", "保证ROI"],
        "notes": "test case",
    }
    payload.update(overrides)
    return SolutionInsightEvalCase.model_validate(payload)


def _build_response(*, proposed_solution: str = "建议优先围绕这些已命中的知识主题做方案收敛：Formal Doc。", fallback_recommended: bool = True) -> SolutionInsightResponse:
    return SolutionInsightResponse(
        request_id="insight-fixed",
        requirement_summary="一家中型 SaaS 公司想提升销售线索转化和客户成功效率。",
        pain_points=["销售线索识别与转化效率不稳定。"],
        ai_opportunity_points=["围绕销售场景做线索优先级判断和话术辅助。"],
        proposed_solution=proposed_solution,
        evidence_items=[
            SolutionInsightEvidenceItem(
                title="Formal Doc",
                candidate_type="chunk",
                document_id="DOC-001",
                chunk_id="DOC-001#chunk-1",
                citation_label="DOC-001 - Overview",
                content_excerpt="formal evidence",
                runtime_eligible=True,
                rejection_reasons=[],
            )
        ],
        evidence_completeness="insufficient",
        fallback_recommended=fallback_recommended,
        fallback_reasons=["boundary_status_blocked_or_unknown"],
        human_confirmation_required=fallback_recommended,
        llm_mode="deterministic",
        retrieval_debug=SolutionInsightRetrievalDebug(
            retrieval_method="lexical_v2_formal",
            formal_candidate_count=1,
            evidence_count=1,
            top_k=5,
            query_hash="fixedhash",
            blocked_retrieval_status="no_eligible_method",
            selected_method=None,
            selection_status="no_eligible_method",
        ),
        shadow_retrieval_debug=SolutionInsightShadowDebug(
            hierarchical_mode="shadow",
            candidate_count=3,
            document_candidate_count=1,
            chunk_candidate_count=2,
            runtime_eligible_count=3,
            runtime_rejected_count=0,
            rejection_reason_counts={},
            evidence_complete=True,
            fallback_recommended=False,
            fallback_reasons=[],
            shadow_error=None,
        ),
        response_note="当前证据不足，需要人工确认或补充资料。",
        log_record={"request_id": "insight-fixed", "llm_mode": "deterministic"},
    )


def test_eval_cases_jsonl_can_be_parsed() -> None:
    cases = load_eval_cases()

    assert len(cases) == 12


def test_eval_case_ids_are_unique() -> None:
    cases = load_eval_cases()

    assert len({case.case_id for case in cases}) == len(cases)


def test_eval_case_fields_are_complete() -> None:
    case = load_eval_cases()[0]

    assert case.user_query
    assert case.required_output_sections
    assert isinstance(case.expected_fallback_behavior, bool)
    assert case.forbidden_claims


def test_schema_validity_scoring_for_invalid_payload() -> None:
    case = _build_case()
    invalid_payload = {"requirement_summary": "only one field"}

    result = evaluate_solution_insight_response(case, invalid_payload, provider="local_template", model_mode="deterministic")

    assert result.schema_is_valid is False
    assert result.scores.schema_validity < 20


def test_forbidden_claims_trigger_hallucination_risk() -> None:
    case = _build_case()
    response = _build_response(proposed_solution="建议优先推进，保证ROI提升40%。")

    result = evaluate_solution_insight_response(case, response, provider="local_template", model_mode="deterministic")

    assert result.hallucination_risk_detected is True
    assert result.scores.hallucination_risk == 0


def test_expected_fallback_behavior_checks_alignment() -> None:
    case = _build_case(expected_fallback_behavior=True)
    response = _build_response(fallback_recommended=False)

    result = evaluate_solution_insight_response(case, response, provider="local_template", model_mode="deterministic")

    assert result.fallback_alignment_ok is False
    assert result.scores.fallback_alignment < 15


def test_shadow_evidence_is_not_counted_as_formal_evidence() -> None:
    case = _build_case()
    response = _build_response()

    result = evaluate_solution_insight_response(case, response, provider="local_template", model_mode="deterministic")

    assert result.response_snapshot["evidence_count"] == 1
    assert result.response_snapshot["formal_candidate_count"] == 1
    assert result.response_snapshot["shadow_debug_present"] is True


def test_deterministic_baseline_can_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    dataset_path.write_text(
        json.dumps(_build_case().model_dump(mode="json"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    fake_service = FakeService(response=_build_response())
    monkeypatch.setattr("evaluation.llm.runner.build_service_for_provider", lambda provider: fake_service)

    report = run_evaluation(dataset_path=dataset_path)

    assert report.case_count == 1
    assert report.model_mode == "deterministic"
    assert fake_service.requests


def test_write_generates_artifact_and_check_matches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    output_path = tmp_path / "baseline.json"
    dataset_path.write_text(
        json.dumps(_build_case().model_dump(mode="json"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("evaluation.llm.runner.build_service_for_provider", lambda provider: FakeService(response=_build_response()))

    report = write_baseline(dataset_path=dataset_path, output_path=output_path)
    matches, details = check_baseline(dataset_path=dataset_path, output_path=output_path)

    assert report.case_count == 1
    assert output_path.exists()
    assert matches is True
    assert details["reason"] == "outputs_match"


def test_non_deterministic_provider_does_not_access_network_by_default() -> None:
    with pytest.raises(NotImplementedError):
        run_evaluation(provider="deepseek")


def test_script_write_and_check_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    output_path = tmp_path / "baseline.json"
    dataset_path.write_text(
        json.dumps(_build_case().model_dump(mode="json"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("evaluation.llm.runner.DATASET_PATH", dataset_path)
    monkeypatch.setattr("evaluation.llm.runner.BASELINE_OUTPUT_PATH", output_path)
    monkeypatch.setattr("evaluation.llm.runner.build_service_for_provider", lambda provider: FakeService(response=_build_response()))

    assert main(["--write"]) == 0
    assert main(["--check"]) == 0


def test_provider_plan_with_missing_api_keys_reports_skipped(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.delenv("GLM_API_KEY", raising=False)

    assert main(["--providers", "deterministic,deepseek,qwen,glm"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["mode"] == "provider_plan"
    assert payload["provider_statuses"]["deepseek"]["provider_status"] == "skipped_missing_api_key"
    assert payload["provider_statuses"]["qwen"]["provider_status"] == "skipped_missing_api_key"
    assert payload["provider_statuses"]["glm"]["provider_status"] == "skipped_missing_api_key"


def test_provider_comparison_write_does_not_overwrite_deterministic_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    baseline_path = tmp_path / "baseline.json"
    comparison_path = tmp_path / "comparison.json"
    dataset_path.write_text(
        json.dumps(_build_case().model_dump(mode="json"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    fake_service = FakeService(response=_build_response())
    monkeypatch.setattr("evaluation.llm.runner.DATASET_PATH", dataset_path)
    monkeypatch.setattr("evaluation.llm.runner.BASELINE_OUTPUT_PATH", baseline_path)
    monkeypatch.setattr("evaluation.llm.runner.COMPARISON_OUTPUT_PATH", comparison_path)
    monkeypatch.setattr("evaluation.llm.runner.build_service_for_provider", lambda provider: fake_service)
    monkeypatch.setattr("evaluation.llm.runner.SolutionInsightService.from_defaults", lambda **kwargs: fake_service)
    monkeypatch.setattr(
        "evaluation.llm.runner.create_provider_client",
        lambda provider_name: FakeLiveClient(
            parsed_json={
                "requirement_summary": "真实模型摘要",
                "pain_points": ["销售线索识别与转化效率不稳定。"],
                "ai_opportunity_points": ["围绕销售场景做线索优先级判断和话术辅助。"],
                "proposed_solution": "建议优先围绕这些已命中的知识主题做方案收敛：Formal Doc。",
                "response_note": "证据不足时仍需人工复核。",
            }
        ),
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    write_baseline(dataset_path=dataset_path, output_path=baseline_path)
    frozen_before = baseline_path.read_text(encoding="utf-8")
    write_provider_comparison(
        providers=["deterministic", "deepseek"],
        dataset_path=dataset_path,
        output_path=comparison_path,
    )

    assert baseline_path.read_text(encoding="utf-8") == frozen_before
    assert comparison_path.exists()


def test_comparison_check_parses_schema_without_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    comparison_path = tmp_path / "comparison.json"
    dataset_path.write_text(
        json.dumps(_build_case().model_dump(mode="json"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    fake_service = FakeService(response=_build_response())
    monkeypatch.setattr("evaluation.llm.runner.DATASET_PATH", dataset_path)
    monkeypatch.setattr("evaluation.llm.runner.COMPARISON_OUTPUT_PATH", comparison_path)
    monkeypatch.setattr("evaluation.llm.runner.SolutionInsightService.from_defaults", lambda **kwargs: fake_service)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.delenv("GLM_API_KEY", raising=False)

    report = write_provider_comparison(
        providers=["deterministic", "deepseek", "qwen", "glm"],
        dataset_path=dataset_path,
        output_path=comparison_path,
    )
    matches, details = check_provider_comparison(output_path=comparison_path)

    assert report.providers_skipped == ["deepseek", "qwen", "glm"]
    assert matches is True
    assert details["reason"] == "comparison_outputs_parseable"


def test_provider_failure_does_not_break_deterministic_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    dataset_path.write_text(
        json.dumps(_build_case().model_dump(mode="json"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    fake_service = FakeService(response=_build_response())
    monkeypatch.setattr("evaluation.llm.runner.SolutionInsightService.from_defaults", lambda **kwargs: fake_service)
    monkeypatch.setattr("evaluation.llm.runner.build_service_for_provider", lambda provider: fake_service)
    monkeypatch.setattr("evaluation.llm.runner.create_provider_client", lambda provider_name: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    report = run_provider_comparison(providers=["deterministic", "deepseek"], dataset_path=dataset_path)

    assert report.provider_statuses["deterministic"].provider_status == "completed"
    assert report.provider_statuses["deepseek"].provider_status == "failed"
    assert report.aggregate_scores_by_provider["deterministic"] is not None
