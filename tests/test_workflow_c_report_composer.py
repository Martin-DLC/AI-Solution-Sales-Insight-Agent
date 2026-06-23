from __future__ import annotations

from datetime import UTC, datetime

from agent.workflow_c import (
    FakeWorkflowLLMClient,
    WorkflowServices,
    build_analysis_id,
    compose_sales_insight_report,
    run_architecture_c_skeleton,
)
from dataio.runtime_cases import load_runtime_cases
from schemas.output_models import SalesInsightReport


FIXED_TIME = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def complete_snapshot():
    return run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )


def compose_from_snapshot(solution_recommendations_marker: object = ...):
    snapshot = complete_snapshot()
    solution_recommendations = (
        snapshot.solution_recommendations
        if solution_recommendations_marker is ...
        else solution_recommendations_marker
    )
    report = compose_sales_insight_report(
        analysis_id=build_analysis_id(run_id=snapshot.run_id, case_id=snapshot.validated_case.case_id),
        generated_at=FIXED_TIME,
        validated_case=snapshot.validated_case,
        fact_extraction=snapshot.fact_extraction,
        context_sufficiency=snapshot.context_sufficiency,
        explicit_needs=snapshot.explicit_needs,
        underlying_pains=snapshot.underlying_pains,
        business_impacts=snapshot.business_impacts,
        buying_intent=snapshot.buying_intent,
        stakeholder_map=snapshot.stakeholder_map,
        information_gaps=snapshot.information_gaps,
        ai_opportunities=snapshot.ai_opportunities,
        solution_recommendations=solution_recommendations,
        deal_score=snapshot.deal_score,
        risks_and_objections=snapshot.risks_and_objections,
        next_best_actions=snapshot.next_best_actions,
    )
    return snapshot, report


def test_valid_complete_input_generates_sales_insight_report() -> None:
    _snapshot, report = compose_from_snapshot()

    assert isinstance(report, SalesInsightReport)
    assert report.case_id == "DEV-01"
    assert report.generated_at == FIXED_TIME


def test_analysis_id_is_stable_and_uses_case_id() -> None:
    assert build_analysis_id(run_id="run-1", case_id="DEV-01") == build_analysis_id(
        run_id="run-1",
        case_id="DEV-01",
    )
    assert build_analysis_id(run_id="run-1", case_id="DEV-01").startswith("analysis-DEV-01-")


def test_report_preserves_all_validated_node_outputs() -> None:
    snapshot, report = compose_from_snapshot()

    assert report.customer_context == snapshot.fact_extraction.customer_context_draft
    assert report.explicit_needs == snapshot.explicit_needs
    assert report.underlying_pains == snapshot.underlying_pains
    assert report.business_impacts == snapshot.business_impacts
    assert report.buying_intent == snapshot.buying_intent
    assert report.stakeholder_map == snapshot.stakeholder_map
    assert report.information_gaps == snapshot.information_gaps
    assert report.ai_opportunities == snapshot.ai_opportunities
    assert report.solution_recommendations == snapshot.solution_recommendations
    assert report.deal_score == snapshot.deal_score
    assert report.risks_and_objections == snapshot.risks_and_objections
    assert report.next_best_actions == snapshot.next_best_actions


def test_solution_recommendations_none_becomes_empty_list() -> None:
    _snapshot, report = compose_from_snapshot(solution_recommendations_marker=None)

    assert report.solution_recommendations == []
    assert "未形成可推荐候选" in report.executive_summary.primary_opportunity
    assert "已匹配解决方案" not in report.executive_summary.primary_opportunity


def test_executive_summary_is_deterministic_and_constrained() -> None:
    _snapshot, report = compose_from_snapshot()

    summary = report.executive_summary.model_dump(mode="json")
    combined = " ".join(str(value) for value in summary.values())
    assert "商机成熟度" in combined
    assert "不等于成交概率" in combined
    assert "预算已批准" not in combined
    assert "决策人已确认" not in combined


def test_customer_followup_uses_gaps_and_actions_without_sending() -> None:
    snapshot, report = compose_from_snapshot()

    assert snapshot.information_gaps[0].question_to_ask in report.customer_followup.next_meeting_agenda
    assert snapshot.next_best_actions[0].objective in report.customer_followup.next_meeting_agenda
    dumped = report.customer_followup.model_dump_json()
    assert "发送成功" not in dumped
    assert "CRM已更新" not in dumped


def test_reliability_summary_and_evaluation_flags_are_state_based() -> None:
    _snapshot, report = compose_from_snapshot()

    assert report.reliability_summary.human_review_required is True
    assert report.reliability_summary.human_review_reasons
    assert report.evaluation_flags
    assert {flag.flag.value for flag in report.evaluation_flags} <= {
        "human_review_required",
        "unknown_budget",
        "unknown_decision_maker",
        "unknown_timeline",
        "solution_without_knowledge_reference",
        "low_context_quality",
    }


def test_report_does_not_include_internal_trace_or_runtime_fields() -> None:
    _snapshot, report = compose_from_snapshot()
    dumped = report.model_dump_json()

    for forbidden in (
        "risk_trace",
        "risk_traces",
        "action_trace",
        "action_traces",
        "node_records",
        "failures",
        "matched_terms",
        "artifact_paths",
        "prompt_version",
        "api_key",
    ):
        assert forbidden not in dumped


def test_composer_does_not_modify_inputs_and_is_deterministic() -> None:
    snapshot = complete_snapshot()
    before = snapshot.model_dump(mode="json")
    kwargs = dict(
        analysis_id="analysis-DEV-01-fixed",
        generated_at=FIXED_TIME,
        validated_case=snapshot.validated_case,
        fact_extraction=snapshot.fact_extraction,
        context_sufficiency=snapshot.context_sufficiency,
        explicit_needs=snapshot.explicit_needs,
        underlying_pains=snapshot.underlying_pains,
        business_impacts=snapshot.business_impacts,
        buying_intent=snapshot.buying_intent,
        stakeholder_map=snapshot.stakeholder_map,
        information_gaps=snapshot.information_gaps,
        ai_opportunities=snapshot.ai_opportunities,
        solution_recommendations=snapshot.solution_recommendations,
        deal_score=snapshot.deal_score,
        risks_and_objections=snapshot.risks_and_objections,
        next_best_actions=snapshot.next_best_actions,
    )

    first = compose_sales_insight_report(**kwargs)
    second = compose_sales_insight_report(**kwargs)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert snapshot.model_dump(mode="json") == before
