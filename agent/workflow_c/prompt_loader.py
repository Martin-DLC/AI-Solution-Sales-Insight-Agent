from __future__ import annotations

import json
from pathlib import Path

from agent.workflow_c.node_outputs import ExplicitNeedNodeOutput, FactExtractionNodeOutput
from agent.workflow_c.state import FactExtractionResult, SourceIndexResult, WorkflowNodeName
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
