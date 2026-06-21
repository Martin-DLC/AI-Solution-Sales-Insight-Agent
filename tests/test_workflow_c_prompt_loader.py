from __future__ import annotations

import pytest

from agent.workflow_c.executor import execute_node
from agent.workflow_c.nodes import SourceIndexingNode
from agent.workflow_c.prompt_loader import (
    load_node_prompt_templates,
    render_business_impact_messages,
    render_explicit_need_messages,
    render_fact_extraction_messages,
    render_underlying_pain_messages,
)
from agent.workflow_c.fake_llm import (
    default_explicit_need_response,
    default_fact_response,
    default_underlying_pain_response,
)
from agent.workflow_c.state import FactExtractionResult, WorkflowNodeName
from dataio.runtime_cases import load_runtime_cases
from schemas.insight_models import ExplicitNeed, UnderlyingPain


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


def test_prompts_do_not_include_reference_pack_terms() -> None:
    combined = "\n".join(
        load_node_prompt_templates(WorkflowNodeName.fact_extraction, "fact_extraction_v1")
        + load_node_prompt_templates(WorkflowNodeName.explicit_need, "explicit_need_v1")
        + load_node_prompt_templates(WorkflowNodeName.underlying_pain, "underlying_pain_v1")
        + load_node_prompt_templates(WorkflowNodeName.business_impact, "business_impact_v1")
    )

    assert "hard_failure_traps" not in combined
    assert "solution_blacklist" not in combined
    assert "scoring_notes" not in combined
    assert "Reference Pack" not in combined


def test_fact_prompt_forbids_downstream_outputs() -> None:
    system_template, _ = load_node_prompt_templates(
        WorkflowNodeName.fact_extraction,
        "fact_extraction_v1",
    )

    assert "Do not infer underlying pain" in system_template
    assert "recommendations" in system_template
    assert "next actions" in system_template


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


def test_new_prompt_rendering_is_stable() -> None:
    explicit_needs = [
        ExplicitNeed.model_validate(item)
        for item in default_explicit_need_response()["explicit_needs"]
    ]
    fact_extraction = FactExtractionResult.model_validate(default_fact_response())
    first = render_underlying_pain_messages(source_index(), fact_extraction, explicit_needs)
    second = render_underlying_pain_messages(source_index(), fact_extraction, explicit_needs)

    assert [message.content for message in first] == [message.content for message in second]
