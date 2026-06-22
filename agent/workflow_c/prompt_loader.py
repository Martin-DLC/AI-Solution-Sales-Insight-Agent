from __future__ import annotations

import json
from pathlib import Path

from agent.workflow_c.node_outputs import (
    BusinessImpactNodeOutput,
    BuyingIntentNodeOutput,
    ExplicitNeedNodeOutput,
    FactExtractionNodeOutput,
    InformationGapNodeOutput,
    StakeholderNodeOutput,
    UnderlyingPainNodeOutput,
)
from agent.workflow_c.state import (
    ContextSufficiencyResult,
    FactExtractionResult,
    SourceIndexResult,
    WorkflowNodeName,
)
from schemas.input_models import Participant
from schemas.insight_models import BusinessImpact, BuyingIntent, ExplicitNeed, Stakeholder, UnderlyingPain
from llm.models import LLMMessage, LLMRole


PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

_PROMPT_REGISTRY: dict[tuple[WorkflowNodeName, str], tuple[str, str]] = {
    (
        WorkflowNodeName.fact_extraction,
        "fact_extraction_v1",
    ): ("fact_extraction_system_v1.txt", "fact_extraction_user_v1.txt"),
    (
        WorkflowNodeName.explicit_need,
        "explicit_need_v1",
    ): ("explicit_need_system_v1.txt", "explicit_need_user_v1.txt"),
    (
        WorkflowNodeName.underlying_pain,
        "underlying_pain_v1",
    ): ("underlying_pain_system_v1.txt", "underlying_pain_user_v1.txt"),
    (
        WorkflowNodeName.business_impact,
        "business_impact_v1",
    ): ("business_impact_system_v1.txt", "business_impact_user_v1.txt"),
    (
        WorkflowNodeName.buying_intent,
        "buying_intent_v1",
    ): ("buying_intent_system_v1.txt", "buying_intent_user_v1.txt"),
    (
        WorkflowNodeName.stakeholder,
        "stakeholder_v1",
    ): ("stakeholder_system_v1.txt", "stakeholder_user_v1.txt"),
    (
        WorkflowNodeName.information_gap,
        "information_gap_v1",
    ): ("information_gap_system_v1.txt", "information_gap_user_v1.txt"),
}

_REQUIRED_PLACEHOLDERS: dict[tuple[WorkflowNodeName, str], tuple[tuple[str, str], ...]] = {
    (
        WorkflowNodeName.fact_extraction,
        "fact_extraction_v1",
    ): (
        ("system", "{{OUTPUT_SCHEMA_JSON}}"),
        ("user", "{{SOURCE_INDEX_JSON}}"),
    ),
    (
        WorkflowNodeName.explicit_need,
        "explicit_need_v1",
    ): (
        ("system", "{{OUTPUT_SCHEMA_JSON}}"),
        ("user", "{{SOURCE_INDEX_JSON}}"),
        ("user", "{{FACTS_JSON}}"),
    ),
    (
        WorkflowNodeName.underlying_pain,
        "underlying_pain_v1",
    ): (
        ("system", "{{OUTPUT_SCHEMA_JSON}}"),
        ("user", "{{SOURCE_INDEX_JSON}}"),
        ("user", "{{FACTS_JSON}}"),
        ("user", "{{EXPLICIT_NEEDS_JSON}}"),
    ),
    (
        WorkflowNodeName.business_impact,
        "business_impact_v1",
    ): (
        ("system", "{{OUTPUT_SCHEMA_JSON}}"),
        ("user", "{{SOURCE_INDEX_JSON}}"),
        ("user", "{{FACTS_JSON}}"),
        ("user", "{{EXPLICIT_NEEDS_JSON}}"),
        ("user", "{{UNDERLYING_PAINS_JSON}}"),
    ),
    (
        WorkflowNodeName.buying_intent,
        "buying_intent_v1",
    ): (
        ("system", "{{OUTPUT_SCHEMA_JSON}}"),
        ("user", "{{SOURCE_INDEX_JSON}}"),
        ("user", "{{CONTEXT_SUFFICIENCY_JSON}}"),
        ("user", "{{FACTS_JSON}}"),
        ("user", "{{EXPLICIT_NEEDS_JSON}}"),
        ("user", "{{UNDERLYING_PAINS_JSON}}"),
        ("user", "{{BUSINESS_IMPACTS_JSON}}"),
    ),
    (
        WorkflowNodeName.stakeholder,
        "stakeholder_v1",
    ): (
        ("system", "{{OUTPUT_SCHEMA_JSON}}"),
        ("user", "{{SOURCE_INDEX_JSON}}"),
        ("user", "{{FACTS_JSON}}"),
        ("user", "{{BUYING_INTENT_JSON}}"),
        ("user", "{{PARTICIPANTS_JSON}}"),
    ),
    (
        WorkflowNodeName.information_gap,
        "information_gap_v1",
    ): (
        ("system", "{{OUTPUT_SCHEMA_JSON}}"),
        ("user", "{{SOURCE_INDEX_JSON}}"),
        ("user", "{{CONTEXT_SUFFICIENCY_JSON}}"),
        ("user", "{{FACTS_JSON}}"),
        ("user", "{{OPTIONAL_ANALYSIS_JSON}}"),
    ),
}


def load_node_prompt_templates(
    node_name: WorkflowNodeName,
    version: str,
) -> tuple[str, str]:
    key = (node_name, version)
    filenames = _PROMPT_REGISTRY.get(key)
    if filenames is None:
        raise ValueError(f"Unsupported prompt version for {node_name.value}: {version}.")

    system_template = _read_prompt_file(filenames[0])
    user_template = _read_prompt_file(filenames[1])
    _validate_placeholders(key, system_template, user_template)
    return system_template, user_template


def render_fact_extraction_messages(
    source_index: SourceIndexResult,
    version: str = "fact_extraction_v1",
) -> list[LLMMessage]:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.fact_extraction,
        version,
    )
    schema_json = _dump_json(FactExtractionNodeOutput.model_json_schema())
    source_index_json = _dump_json(source_index.model_dump(mode="json"))
    return [
        LLMMessage(
            role=LLMRole.system,
            content=system_template.replace("{{OUTPUT_SCHEMA_JSON}}", schema_json),
        ),
        LLMMessage(
            role=LLMRole.user,
            content=user_template.replace("{{SOURCE_INDEX_JSON}}", source_index_json),
        ),
    ]


def render_explicit_need_messages(
    source_index: SourceIndexResult,
    fact_extraction: FactExtractionResult,
    version: str = "explicit_need_v1",
) -> list[LLMMessage]:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.explicit_need,
        version,
    )
    schema_json = _dump_json(ExplicitNeedNodeOutput.model_json_schema())
    source_index_json = _dump_json(source_index.model_dump(mode="json"))
    facts_json = _dump_json(fact_extraction.model_dump(mode="json"))
    return [
        LLMMessage(
            role=LLMRole.system,
            content=system_template.replace("{{OUTPUT_SCHEMA_JSON}}", schema_json),
        ),
        LLMMessage(
            role=LLMRole.user,
            content=(
                user_template
                .replace("{{SOURCE_INDEX_JSON}}", source_index_json)
                .replace("{{FACTS_JSON}}", facts_json)
            ),
        ),
    ]


def render_underlying_pain_messages(
    source_index: SourceIndexResult,
    fact_extraction: FactExtractionResult,
    explicit_needs: list[ExplicitNeed],
    *,
    version: str = "underlying_pain_v1",
) -> list[LLMMessage]:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.underlying_pain,
        version,
    )
    schema_json = _dump_json(UnderlyingPainNodeOutput.model_json_schema())
    source_index_json = _dump_json(source_index.model_dump(mode="json"))
    facts_json = _dump_json(fact_extraction.model_dump(mode="json"))
    explicit_needs_json = _dump_json(
        [need.model_dump(mode="json") for need in explicit_needs]
    )
    return [
        LLMMessage(
            role=LLMRole.system,
            content=system_template.replace("{{OUTPUT_SCHEMA_JSON}}", schema_json),
        ),
        LLMMessage(
            role=LLMRole.user,
            content=(
                user_template
                .replace("{{SOURCE_INDEX_JSON}}", source_index_json)
                .replace("{{FACTS_JSON}}", facts_json)
                .replace("{{EXPLICIT_NEEDS_JSON}}", explicit_needs_json)
            ),
        ),
    ]


def render_business_impact_messages(
    source_index: SourceIndexResult,
    fact_extraction: FactExtractionResult,
    explicit_needs: list[ExplicitNeed],
    underlying_pains: list[UnderlyingPain],
    *,
    version: str = "business_impact_v1",
) -> list[LLMMessage]:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.business_impact,
        version,
    )
    schema_json = _dump_json(BusinessImpactNodeOutput.model_json_schema())
    source_index_json = _dump_json(source_index.model_dump(mode="json"))
    facts_json = _dump_json(fact_extraction.model_dump(mode="json"))
    explicit_needs_json = _dump_json(
        [need.model_dump(mode="json") for need in explicit_needs]
    )
    underlying_pains_json = _dump_json(
        [pain.model_dump(mode="json") for pain in underlying_pains]
    )
    return [
        LLMMessage(
            role=LLMRole.system,
            content=system_template.replace("{{OUTPUT_SCHEMA_JSON}}", schema_json),
        ),
        LLMMessage(
            role=LLMRole.user,
            content=(
                user_template
                .replace("{{SOURCE_INDEX_JSON}}", source_index_json)
                .replace("{{FACTS_JSON}}", facts_json)
                .replace("{{EXPLICIT_NEEDS_JSON}}", explicit_needs_json)
                .replace("{{UNDERLYING_PAINS_JSON}}", underlying_pains_json)
            ),
        ),
    ]


def render_buying_intent_messages(
    source_index: SourceIndexResult,
    context_sufficiency: ContextSufficiencyResult,
    fact_extraction: FactExtractionResult,
    explicit_needs: list[ExplicitNeed],
    underlying_pains: list[UnderlyingPain],
    business_impacts: list[BusinessImpact],
    *,
    version: str = "buying_intent_v1",
) -> list[LLMMessage]:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.buying_intent,
        version,
    )
    schema_json = _dump_json(BuyingIntentNodeOutput.model_json_schema())
    return [
        LLMMessage(
            role=LLMRole.system,
            content=system_template.replace("{{OUTPUT_SCHEMA_JSON}}", schema_json),
        ),
        LLMMessage(
            role=LLMRole.user,
            content=(
                user_template
                .replace("{{SOURCE_INDEX_JSON}}", _dump_json(source_index.model_dump(mode="json")))
                .replace("{{CONTEXT_SUFFICIENCY_JSON}}", _dump_json(context_sufficiency.model_dump(mode="json")))
                .replace("{{FACTS_JSON}}", _dump_json(fact_extraction.model_dump(mode="json")))
                .replace("{{EXPLICIT_NEEDS_JSON}}", _dump_json([need.model_dump(mode="json") for need in explicit_needs]))
                .replace("{{UNDERLYING_PAINS_JSON}}", _dump_json([pain.model_dump(mode="json") for pain in underlying_pains]))
                .replace("{{BUSINESS_IMPACTS_JSON}}", _dump_json([impact.model_dump(mode="json") for impact in business_impacts]))
            ),
        ),
    ]


def render_stakeholder_messages(
    source_index: SourceIndexResult,
    fact_extraction: FactExtractionResult,
    buying_intent: BuyingIntent,
    participants: list[Participant],
    *,
    version: str = "stakeholder_v1",
) -> list[LLMMessage]:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.stakeholder,
        version,
    )
    schema_json = _dump_json(StakeholderNodeOutput.model_json_schema())
    return [
        LLMMessage(
            role=LLMRole.system,
            content=system_template.replace("{{OUTPUT_SCHEMA_JSON}}", schema_json),
        ),
        LLMMessage(
            role=LLMRole.user,
            content=(
                user_template
                .replace("{{SOURCE_INDEX_JSON}}", _dump_json(source_index.model_dump(mode="json")))
                .replace("{{FACTS_JSON}}", _dump_json(fact_extraction.model_dump(mode="json")))
                .replace("{{BUYING_INTENT_JSON}}", _dump_json(buying_intent.model_dump(mode="json")))
                .replace("{{PARTICIPANTS_JSON}}", _dump_json([participant.model_dump(mode="json") for participant in participants]))
            ),
        ),
    ]


def render_information_gap_messages(
    source_index: SourceIndexResult,
    context_sufficiency: ContextSufficiencyResult,
    fact_extraction: FactExtractionResult,
    *,
    explicit_needs: list[ExplicitNeed] | None = None,
    underlying_pains: list[UnderlyingPain] | None = None,
    business_impacts: list[BusinessImpact] | None = None,
    buying_intent: BuyingIntent | None = None,
    stakeholder_map: list[Stakeholder] | None = None,
    version: str = "information_gap_v1",
) -> list[LLMMessage]:
    system_template, user_template = load_node_prompt_templates(
        WorkflowNodeName.information_gap,
        version,
    )
    optional_analysis = {
        "explicit_needs": [
            need.model_dump(mode="json") for need in explicit_needs or []
        ],
        "underlying_pains": [
            pain.model_dump(mode="json") for pain in underlying_pains or []
        ],
        "business_impacts": [
            impact.model_dump(mode="json") for impact in business_impacts or []
        ],
        "buying_intent": (
            buying_intent.model_dump(mode="json")
            if buying_intent is not None
            else None
        ),
        "stakeholder_map": [
            stakeholder.model_dump(mode="json")
            for stakeholder in stakeholder_map or []
        ],
    }
    return [
        LLMMessage(
            role=LLMRole.system,
            content=system_template.replace(
                "{{OUTPUT_SCHEMA_JSON}}",
                _dump_json(InformationGapNodeOutput.model_json_schema()),
            ),
        ),
        LLMMessage(
            role=LLMRole.user,
            content=(
                user_template
                .replace("{{SOURCE_INDEX_JSON}}", _dump_json(source_index.model_dump(mode="json")))
                .replace("{{CONTEXT_SUFFICIENCY_JSON}}", _dump_json(context_sufficiency.model_dump(mode="json")))
                .replace("{{FACTS_JSON}}", _dump_json(fact_extraction.model_dump(mode="json")))
                .replace("{{OPTIONAL_ANALYSIS_JSON}}", _dump_json(optional_analysis))
            ),
        ),
    ]


def _read_prompt_file(filename: str) -> str:
    path = PROMPT_DIR / filename
    if path.parent != PROMPT_DIR:
        raise ValueError("Prompt path must stay inside the Workflow C prompt directory.")
    return path.read_text(encoding="utf-8")


def _validate_placeholders(
    key: tuple[WorkflowNodeName, str],
    system_template: str,
    user_template: str,
) -> None:
    templates = {"system": system_template, "user": user_template}
    for template_name, placeholder in _REQUIRED_PLACEHOLDERS[key]:
        count = templates[template_name].count(placeholder)
        if count != 1:
            raise ValueError(
                f"Prompt {key[1]} {template_name} template must contain "
                f"{placeholder} exactly once."
            )


def _dump_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
