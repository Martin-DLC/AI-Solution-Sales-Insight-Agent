from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.models import (
    SolutionInsightEvidenceItem,
    SolutionInsightResponse,
    SolutionInsightRetrievalDebug,
    SolutionInsightShadowDebug,
)
from evaluation.llm.providers import create_provider_client, get_provider_spec, provider_is_available
from evaluation.llm.runner import run_provider_comparison
from llm.config import LLMConfig
from llm.errors import LLMJSONDecodeError


class FakeService:
    def __init__(self, *, response: SolutionInsightResponse) -> None:
        self._response = response

    def generate_insight(self, request):  # noqa: ANN001
        return self._response


class FakeLiveResponse:
    def __init__(self, *, parsed_json: dict[str, object] | None, latency_ms: int = 88) -> None:
        self.parsed_json = parsed_json
        self.latency_ms = latency_ms
        self.usage = type(
            "Usage",
            (),
            {"model_dump": lambda self, mode="json": {"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18}},
        )()


class FakeClient:
    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode

    def complete_json(self, messages):  # noqa: ANN001
        if self.mode == "invalid_json":
            raise LLMJSONDecodeError(
                raw_content="not-json",
                json_error_message="Expecting value",
                json_error_position=0,
            )
        if self.mode == "request_error":
            raise RuntimeError("provider boom")
        return FakeLiveResponse(
            parsed_json={
                "requirement_summary": "真实模型摘要",
                "pain_points": ["销售线索识别与转化效率不稳定。"],
                "ai_opportunity_points": ["围绕销售场景做线索优先级判断和话术辅助。"],
                "proposed_solution": "建议优先围绕这些已命中的知识主题做方案收敛：Formal Doc。",
                "response_note": "证据不足时仍需人工确认。",
            }
        )


def _build_response() -> SolutionInsightResponse:
    return SolutionInsightResponse(
        request_id="insight-fixed",
        requirement_summary="一家中型 SaaS 公司想提升销售线索转化和客户成功效率。",
        pain_points=["销售线索识别与转化效率不稳定。"],
        ai_opportunity_points=["围绕销售场景做线索优先级判断和话术辅助。"],
        proposed_solution="建议优先围绕这些已命中的知识主题做方案收敛：Formal Doc。",
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
        fallback_recommended=True,
        fallback_reasons=["boundary_status_blocked_or_unknown"],
        human_confirmation_required=True,
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


def _write_case(tmp_path: Path) -> Path:
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
    dataset_path = tmp_path / "cases.jsonl"
    dataset_path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    return dataset_path


def test_deterministic_provider_availability_is_local_only() -> None:
    spec = get_provider_spec("deterministic")

    assert spec.provider_name == "deterministic"
    assert provider_is_available("deterministic") is True


def test_missing_api_key_marks_provider_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    assert provider_is_available("deepseek") is False


def test_create_provider_client_uses_explicit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_factory(config: LLMConfig) -> object:
        captured["config"] = config
        return object()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-reasoner")

    create_provider_client("deepseek", client_factory=fake_factory)
    config = captured["config"]

    assert isinstance(config, LLMConfig)
    assert config.model == "deepseek-reasoner"
    assert config.base_url == "https://api.deepseek.com"


def test_non_json_provider_output_is_safely_scored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_path = _write_case(tmp_path)
    monkeypatch.setattr("evaluation.llm.runner.SolutionInsightService.from_defaults", lambda **kwargs: FakeService(response=_build_response()))
    monkeypatch.setattr("evaluation.llm.runner.create_provider_client", lambda provider_name: FakeClient(mode="invalid_json"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")

    report = run_provider_comparison(providers=["deepseek"], dataset_path=dataset_path)

    assert report.provider_statuses["deepseek"].provider_status == "completed_with_case_errors"
    assert report.schema_invalid_cases_by_provider["deepseek"] == ["CASE-001"]
    assert report.per_case_scores_by_provider["deepseek"][0].schema_is_valid is False


def test_provider_request_error_is_recorded_without_fake_score(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_path = _write_case(tmp_path)
    monkeypatch.setattr("evaluation.llm.runner.SolutionInsightService.from_defaults", lambda **kwargs: FakeService(response=_build_response()))
    monkeypatch.setattr("evaluation.llm.runner.create_provider_client", lambda provider_name: FakeClient(mode="request_error"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")

    report = run_provider_comparison(providers=["deepseek"], dataset_path=dataset_path)

    assert report.provider_statuses["deepseek"].provider_status == "failed"
    assert report.aggregate_scores_by_provider.get("deepseek") is None
    assert report.case_errors_by_provider["deepseek"][0].error_type == "RuntimeError"
