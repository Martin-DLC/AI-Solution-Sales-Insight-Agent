from __future__ import annotations

import json

import pytest

from agent.workflow_c.executor import execute_node
from agent.workflow_c.nodes import SourceIndexingNode
from agent.workflow_c.prompt_loader import (
    render_ai_opportunity_messages,
    render_buying_intent_messages,
    load_node_prompt_templates,
    render_business_impact_messages,
    render_explicit_need_messages,
    render_fact_extraction_messages,
    render_information_gap_messages,
    render_next_best_action_messages,
    render_risk_messages,
    render_solution_recommendation_messages,
    render_stakeholder_messages,
    render_underlying_pain_messages,
)
from agent.workflow_c.fake_llm import (
    default_ai_opportunity_response,
    default_buying_intent_response,
    default_business_impact_response,
    default_explicit_need_response,
    default_fact_response,
    default_information_gap_response,
    default_stakeholder_response,
    default_underlying_pain_response,
)
from agent.workflow_c.solution_retrieval import retrieve_solution_candidates
from agent.workflow_c.state import ContextSufficiencyResult, FactExtractionResult, WorkflowNodeName
from dataio.runtime_cases import load_runtime_cases
from schemas.insight_models import (
    BusinessImpact,
    BuyingIntent,
    ExplicitNeed,
    InformationGap,
    Stakeholder,
    UnderlyingPain,
)
from schemas.solution_models import AIOpportunity
from agent.workflow_c import FakeWorkflowLLMClient, WorkflowServices, run_architecture_c_skeleton


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def source_index():
    case = dev_01_case()
    return execute_node(
        SourceIndexingNode(),
        {"validated_case": case},
        services=None,
    )["source_index"]


def test_fact_prompt_templates_load() -> None:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.fact_extraction,
        "fact_extraction_v1",
    )

    assert "{{OUTPUT_SCHEMA_JSON}}" in system_template
    assert "{{SOURCE_INDEX_JSON}}" in user_template


def test_fact_prompt_templates_load_v2() -> None:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.fact_extraction,
        "fact_extraction_v2",
    )

    assert "{{OUTPUT_SCHEMA_JSON}}" in system_template
    assert "{{SOURCE_INDEX_JSON}}" in user_template
    assert "{{ALLOWED_EVIDENCE_SOURCES_JSON}}" in user_template


def test_explicit_need_prompt_templates_load() -> None:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.explicit_need,
        "explicit_need_v1",
    )

    assert "{{OUTPUT_SCHEMA_JSON}}" in system_template
    assert "{{SOURCE_INDEX_JSON}}" in user_template
    assert "{{FACTS_JSON}}" in user_template


def test_underlying_pain_prompt_templates_load() -> None:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.underlying_pain,
        "underlying_pain_v1",
    )

    assert system_template.count("{{OUTPUT_SCHEMA_JSON}}") == 1
    assert user_template.count("{{SOURCE_INDEX_JSON}}") == 1
    assert user_template.count("{{FACTS_JSON}}") == 1
    assert user_template.count("{{EXPLICIT_NEEDS_JSON}}") == 1


def test_underlying_pain_prompt_templates_load_v2() -> None:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.underlying_pain,
        "underlying_pain_v2",
    )

    assert system_template.count("{{OUTPUT_SCHEMA_JSON}}") == 1
    assert user_template.count("{{SOURCE_INDEX_JSON}}") == 1
    assert user_template.count("{{ALLOWED_EVIDENCE_SOURCES_JSON}}") == 1
    assert user_template.count("{{FACTS_JSON}}") == 1
    assert user_template.count("{{EXPLICIT_NEEDS_JSON}}") == 1


def test_business_impact_prompt_templates_load() -> None:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.business_impact,
        "business_impact_v1",
    )

    assert system_template.count("{{OUTPUT_SCHEMA_JSON}}") == 1
    assert user_template.count("{{SOURCE_INDEX_JSON}}") == 1
    assert user_template.count("{{FACTS_JSON}}") == 1
    assert user_template.count("{{EXPLICIT_NEEDS_JSON}}") == 1
    assert user_template.count("{{UNDERLYING_PAINS_JSON}}") == 1


def test_buying_intent_prompt_templates_load() -> None:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.buying_intent,
        "buying_intent_v1",
    )

    assert system_template.count("{{OUTPUT_SCHEMA_JSON}}") == 1
    assert user_template.count("{{SOURCE_INDEX_JSON}}") == 1
    assert user_template.count("{{CONTEXT_SUFFICIENCY_JSON}}") == 1
    assert user_template.count("{{FACTS_JSON}}") == 1
    assert user_template.count("{{EXPLICIT_NEEDS_JSON}}") == 1
    assert user_template.count("{{UNDERLYING_PAINS_JSON}}") == 1
    assert user_template.count("{{BUSINESS_IMPACTS_JSON}}") == 1


def test_stakeholder_prompt_templates_load() -> None:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.stakeholder,
        "stakeholder_v1",
    )

    assert system_template.count("{{OUTPUT_SCHEMA_JSON}}") == 1
    assert user_template.count("{{SOURCE_INDEX_JSON}}") == 1
    assert user_template.count("{{FACTS_JSON}}") == 1
    assert user_template.count("{{BUYING_INTENT_JSON}}") == 1
    assert user_template.count("{{PARTICIPANTS_JSON}}") == 1


def test_information_gap_prompt_templates_load() -> None:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.information_gap,
        "information_gap_v1",
    )

    assert system_template.count("{{OUTPUT_SCHEMA_JSON}}") == 1
    assert user_template.count("{{SOURCE_INDEX_JSON}}") == 1
    assert user_template.count("{{CONTEXT_SUFFICIENCY_JSON}}") == 1
    assert user_template.count("{{FACTS_JSON}}") == 1
    assert user_template.count("{{OPTIONAL_ANALYSIS_JSON}}") == 1


def test_ai_opportunity_prompt_templates_load() -> None:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.ai_opportunity,
        "ai_opportunity_v1",
    )

    assert system_template.count("{{OUTPUT_SCHEMA_JSON}}") == 1
    assert user_template.count("{{SOURCE_INDEX_JSON}}") == 1
    assert user_template.count("{{CONTEXT_SUFFICIENCY_JSON}}") == 1
    assert user_template.count("{{EXPLICIT_NEEDS_JSON}}") == 1
    assert user_template.count("{{UNDERLYING_PAINS_JSON}}") == 1
    assert user_template.count("{{BUSINESS_IMPACTS_JSON}}") == 1
    assert user_template.count("{{INFORMATION_GAPS_JSON}}") == 1
    assert user_template.count("{{CONSTRAINTS_JSON}}") == 1


def test_solution_recommendation_prompt_templates_load() -> None:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.solution_recommendation,
        "solution_recommendation_v1",
    )

    assert system_template.count("{{OUTPUT_SCHEMA_JSON}}") == 1
    assert user_template.count("{{AI_OPPORTUNITIES_JSON}}") == 1
    assert user_template.count("{{INFORMATION_GAPS_JSON}}") == 1
    assert user_template.count("{{CONSTRAINTS_JSON}}") == 1
    assert user_template.count("{{RETRIEVED_SOLUTION_CANDIDATES_JSON}}") == 1


def test_risk_prompt_templates_load() -> None:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.risk,
        "risk_v1",
    )

    assert system_template.count("{{OUTPUT_SCHEMA_JSON}}") == 1
    assert user_template.count("{{CONSTRAINTS_JSON}}") == 1
    assert user_template.count("{{INFORMATION_GAPS_JSON}}") == 1
    assert user_template.count("{{BUYING_INTENT_JSON}}") == 1
    assert user_template.count("{{STAKEHOLDERS_JSON}}") == 1
    assert user_template.count("{{AI_OPPORTUNITIES_JSON}}") == 1
    assert user_template.count("{{SOLUTION_RECOMMENDATIONS_JSON}}") == 1
    assert user_template.count("{{DEAL_SCORE_JSON}}") == 1


def test_next_best_action_prompt_templates_load() -> None:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.next_best_action,
        "next_best_action_v1",
    )

    assert system_template.count("{{OUTPUT_SCHEMA_JSON}}") == 1
    assert user_template.count("{{BUYING_INTENT_JSON}}") == 1
    assert user_template.count("{{STAKEHOLDERS_JSON}}") == 1
    assert user_template.count("{{INFORMATION_GAPS_JSON}}") == 1
    assert user_template.count("{{DEAL_SCORE_JSON}}") == 1
    assert user_template.count("{{RISKS_JSON}}") == 1


def test_unknown_prompt_version_fails() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        load_node_prompt_templates(WorkflowNodeName.fact_extraction, "../bad")


def test_fact_prompt_renders_two_messages_without_placeholders() -> None:
    messages = render_fact_extraction_messages(source_index())

    assert len(messages) == 2
    assert "{{" not in messages[0].content
    assert "{{" not in messages[1].content
    assert "MTG-01" in messages[1].content


def test_explicit_need_prompt_renders_source_index_and_facts() -> None:
    messages = render_explicit_need_messages(
        source_index(),
        fact_extraction=FactExtractionResult.model_validate(default_fact_response()),
    )

    assert len(messages) == 2
    assert "MTG-01" in messages[1].content
    assert "FACT-01" in messages[1].content


def test_underlying_pain_prompt_renders_dependencies() -> None:
    messages = render_underlying_pain_messages(
        source_index(),
        FactExtractionResult.model_validate(default_fact_response()),
        [
            ExplicitNeed.model_validate(item)
            for item in default_explicit_need_response()["explicit_needs"]
        ],
    )

    assert len(messages) == 2
    assert "FACT-01" in messages[1].content
    assert "NEED-01" in messages[1].content


def test_business_impact_prompt_renders_dependencies() -> None:
    messages = render_business_impact_messages(
        source_index(),
        FactExtractionResult.model_validate(default_fact_response()),
        [
            ExplicitNeed.model_validate(item)
            for item in default_explicit_need_response()["explicit_needs"]
        ],
        [
            UnderlyingPain.model_validate(item)
            for item in default_underlying_pain_response()["underlying_pains"]
        ],
    )

    assert len(messages) == 2
    assert "NEED-01" in messages[1].content
    assert "PAIN-01" in messages[1].content


def test_buying_intent_prompt_renders_dependencies() -> None:
    fact_extraction = FactExtractionResult.model_validate(default_fact_response())
    explicit_needs = [
        ExplicitNeed.model_validate(item)
        for item in default_explicit_need_response()["explicit_needs"]
    ]
    underlying_pains = [
        UnderlyingPain.model_validate(item)
        for item in default_underlying_pain_response()["underlying_pains"]
    ]
    business_impacts = [
        BusinessImpact.model_validate(item)
        for item in default_business_impact_response()["business_impacts"]
    ]
    messages = render_buying_intent_messages(
        source_index(),
        ContextSufficiencyResult.model_validate(
            {
                "context_quality": "partially_sufficient",
                "analysis_mode": "partial_analysis",
                "available_categories": ["business_goal"],
                "missing_categories": ["budget"],
                "blocking_gaps": [],
                "reasoning_summary": "已有业务目标，但预算和决策链仍需确认。",
            }
        ),
        fact_extraction,
        explicit_needs,
        underlying_pains,
        business_impacts,
    )

    assert len(messages) == 2
    assert "NEED-01" in messages[1].content
    assert "PAIN-01" in messages[1].content
    assert "IMPACT-01" in messages[1].content


def test_stakeholder_prompt_renders_dependencies() -> None:
    messages = render_stakeholder_messages(
        source_index(),
        FactExtractionResult.model_validate(default_fact_response()),
        BuyingIntent.model_validate(default_buying_intent_response()["buying_intent"]),
        dev_01_case().meeting.participants,
    )

    assert len(messages) == 2
    assert "FACT-03" in messages[1].content
    assert "medium_high" in messages[1].content
    assert dev_01_case().meeting.participants[0].name_or_role in messages[1].content


def test_information_gap_prompt_renders_optional_context() -> None:
    messages = render_information_gap_messages(
        source_index(),
        ContextSufficiencyResult.model_validate(
            {
                "context_quality": "partially_sufficient",
                "analysis_mode": "partial_analysis",
                "available_categories": ["business_goal"],
                "missing_categories": ["budget"],
                "blocking_gaps": [],
                "reasoning_summary": "已有业务目标，但预算和决策链仍需确认。",
            }
        ),
        FactExtractionResult.model_validate(default_fact_response()),
        explicit_needs=[
            ExplicitNeed.model_validate(item)
            for item in default_explicit_need_response()["explicit_needs"]
        ],
        underlying_pains=[
            UnderlyingPain.model_validate(item)
            for item in default_underlying_pain_response()["underlying_pains"]
        ],
        business_impacts=[
            BusinessImpact.model_validate(item)
            for item in default_business_impact_response()["business_impacts"]
        ],
        buying_intent=BuyingIntent.model_validate(
            default_buying_intent_response()["buying_intent"]
        ),
        stakeholder_map=[
            Stakeholder.model_validate(item)
            for item in default_stakeholder_response()["stakeholder_map"]
        ],
    )

    assert len(messages) == 2
    assert "NEED-01" in messages[1].content
    assert "PAIN-01" in messages[1].content
    assert "IMPACT-01" in messages[1].content
    assert "unknown_factors" in messages[1].content
    assert "STK-02" in messages[1].content


def test_ai_opportunity_prompt_renders_dependencies() -> None:
    messages = render_ai_opportunity_messages(
        source_index(),
        ContextSufficiencyResult.model_validate(
            {
                "context_quality": "partially_sufficient",
                "analysis_mode": "partial_analysis",
                "available_categories": ["business_goal"],
                "missing_categories": ["budget"],
                "blocking_gaps": [],
                "reasoning_summary": "已有业务目标，但预算和决策链仍需确认。",
            }
        ),
        [
            ExplicitNeed.model_validate(item)
            for item in default_explicit_need_response()["explicit_needs"]
        ],
        [
            UnderlyingPain.model_validate(item)
            for item in default_underlying_pain_response()["underlying_pains"]
        ],
        [
            BusinessImpact.model_validate(item)
            for item in default_business_impact_response()["business_impacts"]
        ],
        [
            InformationGap.model_validate(item)
            for item in default_information_gap_response()["information_gaps"]
        ],
        dev_01_case().known_constraints,
    )

    assert len(messages) == 2
    assert "NODE: ai_opportunity" in messages[1].content
    assert "PAIN-01" in messages[1].content
    assert "GAP-01" in messages[1].content


def test_solution_recommendation_prompt_renders_retrieved_candidates() -> None:
    ai_opportunities = [
        AIOpportunity.model_validate(item)
        for item in default_ai_opportunity_response()["ai_opportunities"]
    ]
    retrieved_solutions = retrieve_solution_candidates(
        case=dev_01_case(),
        source_index=source_index(),
        ai_opportunities=ai_opportunities,
        underlying_pains=[
            UnderlyingPain.model_validate(item)
            for item in default_underlying_pain_response()["underlying_pains"]
        ],
        business_impacts=[
            BusinessImpact.model_validate(item)
            for item in default_business_impact_response()["business_impacts"]
        ],
    )
    messages = render_solution_recommendation_messages(
        ai_opportunities,
        [
            InformationGap.model_validate(item)
            for item in default_information_gap_response()["information_gaps"]
        ],
        dev_01_case().known_constraints,
        retrieved_solutions,
    )

    assert len(messages) == 2
    assert "NODE: solution_recommendation" in messages[1].content
    assert "retrieval_method" in messages[1].content
    assert retrieved_solutions.candidates[0].solution_id in messages[1].content
    assert "订单与物流查询Tool方案" not in messages[1].content


def test_prompts_do_not_include_reference_pack_terms() -> None:
    combined = "\n".join(
        load_node_prompt_templates(WorkflowNodeName.fact_extraction, "fact_extraction_v1")
        + load_node_prompt_templates(WorkflowNodeName.fact_extraction, "fact_extraction_v2")
        + load_node_prompt_templates(WorkflowNodeName.explicit_need, "explicit_need_v1")
        + load_node_prompt_templates(WorkflowNodeName.underlying_pain, "underlying_pain_v1")
        + load_node_prompt_templates(WorkflowNodeName.underlying_pain, "underlying_pain_v2")
        + load_node_prompt_templates(WorkflowNodeName.business_impact, "business_impact_v1")
        + load_node_prompt_templates(WorkflowNodeName.buying_intent, "buying_intent_v1")
        + load_node_prompt_templates(WorkflowNodeName.stakeholder, "stakeholder_v1")
        + load_node_prompt_templates(WorkflowNodeName.information_gap, "information_gap_v1")
        + load_node_prompt_templates(WorkflowNodeName.ai_opportunity, "ai_opportunity_v1")
        + load_node_prompt_templates(
            WorkflowNodeName.solution_recommendation,
            "solution_recommendation_v1",
        )
        + load_node_prompt_templates(WorkflowNodeName.risk, "risk_v1")
        + load_node_prompt_templates(
            WorkflowNodeName.next_best_action,
            "next_best_action_v1",
        )
    )

    assert "hard_failure_traps" not in combined
    assert "solution_blacklist" not in combined
    assert "scoring_notes" not in combined
    assert "Reference Pack" not in combined


def test_fact_prompt_forbids_downstream_outputs() -> None:
    system_template, _ = load_node_prompt_templates(
        WorkflowNodeName.fact_extraction,
        "fact_extraction_v2",
    )

    assert "Do not infer underlying pain" in system_template
    assert "business_rule" in system_template
    assert "evidence_summary" in system_template
    assert "8 characters" in system_template


def test_fact_prompt_includes_allowed_evidence_sources_list() -> None:
    messages = render_fact_extraction_messages(source_index(), version="fact_extraction_v2")
    user_content = messages[1].content
    marker = "ALLOWED EVIDENCE SOURCES\n"
    allowed_json = user_content.split(marker, 1)[1].split("\n\n", 1)[0]
    allowed_sources = json.loads(allowed_json)

    assert allowed_sources
    assert set(allowed_sources[0]) == {"source_id", "source_type"}
    assert allowed_sources[0]["source_id"] == "PROFILE-01"
    assert allowed_sources[0]["source_type"] == "customer_profile"


def test_explicit_need_prompt_requires_fact_claim_type() -> None:
    system_template, _ = load_node_prompt_templates(
        WorkflowNodeName.explicit_need,
        "explicit_need_v1",
    )

    assert 'claim_type "fact"' in system_template


def test_explicit_need_prompt_mentions_unverified_notes() -> None:
    system_template, _ = load_node_prompt_templates(
        WorkflowNodeName.explicit_need,
        "explicit_need_v1",
    )

    assert "verified=false" in system_template


def test_underlying_pain_prompt_mentions_allowed_evidence_sources() -> None:
    messages = render_underlying_pain_messages(
        source_index(),
        FactExtractionResult.model_validate(default_fact_response()),
        [
            ExplicitNeed.model_validate(item)
            for item in default_explicit_need_response()["explicit_needs"]
        ],
        version="underlying_pain_v2",
    )
    user_content = messages[1].content
    marker = "ALLOWED EVIDENCE SOURCES\n"
    allowed_json = user_content.split(marker, 1)[1].split("\n\n", 1)[0]
    allowed_sources = json.loads(allowed_json)

    assert allowed_sources
    assert set(allowed_sources[0]) == {"source_id", "source_type"}
    assert "business_rule" in messages[0].content
    assert "evidence_summary" in messages[0].content
    assert "8 characters" in messages[0].content


def test_new_prompt_rendering_is_stable() -> None:
    explicit_needs = [
        ExplicitNeed.model_validate(item)
        for item in default_explicit_need_response()["explicit_needs"]
    ]
    fact_extraction = FactExtractionResult.model_validate(default_fact_response())
    first = render_underlying_pain_messages(source_index(), fact_extraction, explicit_needs)
    second = render_underlying_pain_messages(source_index(), fact_extraction, explicit_needs)

    assert [message.content for message in first] == [message.content for message in second]


def test_solution_recommendation_rendering_is_stable() -> None:
    ai_opportunities = [
        AIOpportunity.model_validate(item)
        for item in default_ai_opportunity_response()["ai_opportunities"]
    ]
    retrieved_solutions = retrieve_solution_candidates(
        case=dev_01_case(),
        source_index=source_index(),
        ai_opportunities=ai_opportunities,
        underlying_pains=[
            UnderlyingPain.model_validate(item)
            for item in default_underlying_pain_response()["underlying_pains"]
        ],
        business_impacts=[
            BusinessImpact.model_validate(item)
            for item in default_business_impact_response()["business_impacts"]
        ],
    )
    information_gaps = [
        InformationGap.model_validate(item)
        for item in default_information_gap_response()["information_gaps"]
    ]

    first = render_solution_recommendation_messages(
        ai_opportunities,
        information_gaps,
        dev_01_case().known_constraints,
        retrieved_solutions,
    )
    second = render_solution_recommendation_messages(
        ai_opportunities,
        information_gaps,
        dev_01_case().known_constraints,
        retrieved_solutions,
    )

    assert [message.content for message in first] == [message.content for message in second]


def test_risk_prompt_renders_dependencies() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )
    messages = render_risk_messages(
        dev_01_case().known_constraints,
        snapshot.information_gaps,
        snapshot.buying_intent,
        snapshot.stakeholder_map,
        snapshot.ai_opportunities,
        snapshot.solution_recommendations or [],
        snapshot.deal_score,
    )

    assert "NODE: risk" in messages[1].content
    assert "BEGIN_INFORMATION_GAPS_JSON" in messages[1].content
    assert "GAP-01" in messages[1].content


def test_next_best_action_prompt_renders_dependencies() -> None:
    snapshot = run_architecture_c_skeleton(
        dev_01_case(),
        WorkflowServices(llm=FakeWorkflowLLMClient.with_default_batch4b_responses()),
    )
    messages = render_next_best_action_messages(
        snapshot.buying_intent,
        snapshot.stakeholder_map,
        snapshot.information_gaps,
        snapshot.deal_score,
        snapshot.risks_and_objections,
    )

    assert "NODE: next_best_action" in messages[1].content
    assert "BEGIN_RISKS_JSON" in messages[1].content
    assert "RISK-01" in messages[1].content
