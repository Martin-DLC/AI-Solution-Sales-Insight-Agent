from __future__ import annotations

import hashlib
import json
from pathlib import Path

from llm import LLMMessage, LLMRole
from schemas import EvaluationCaseInput
from schemas.output_models import SalesInsightReport


PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
SUPPORTED_PROMPTS = {"baseline_a_v1": "baseline_a_v1.txt"}
SUPPORTED_BASELINE_B_PROMPTS = {
    "baseline_b_v1": ("baseline_b_system_v1.txt", "baseline_b_user_v1.txt"),
    "baseline_b_v2": ("baseline_b_system_v2.txt", "baseline_b_user_v2.txt"),
    "baseline_b_v3": ("baseline_b_system_v3.txt", "baseline_b_user_v3.txt"),
}
CASE_JSON_PLACEHOLDER = "{{CASE_JSON}}"
OUTPUT_SCHEMA_PLACEHOLDER = "{{OUTPUT_SCHEMA_JSON}}"


def load_prompt_template(version: str) -> str:
    filename = SUPPORTED_PROMPTS.get(version)
    if filename is None:
        raise ValueError(f"Unsupported baseline prompt version: {version}")
    template = (PROMPT_DIR / filename).read_text(encoding="utf-8")
    placeholder_count = template.count(CASE_JSON_PLACEHOLDER)
    if placeholder_count != 1:
        raise ValueError(
            f"Prompt template {version} must contain exactly one {CASE_JSON_PLACEHOLDER} placeholder."
        )
    return template


def render_baseline_a_prompt(
    case: EvaluationCaseInput,
    *,
    version: str = "baseline_a_v1",
) -> str:
    template = load_prompt_template(version)
    case_json = json.dumps(case.model_dump(mode="json"), ensure_ascii=False, indent=2)
    return template.replace(CASE_JSON_PLACEHOLDER, case_json)


def calculate_prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def load_baseline_b_templates(
    version: str = "baseline_b_v1",
) -> tuple[str, str]:
    filenames = SUPPORTED_BASELINE_B_PROMPTS.get(version)
    if filenames is None:
        raise ValueError(f"Unsupported baseline B prompt version: {version}")
    system_template = (PROMPT_DIR / filenames[0]).read_text(encoding="utf-8")
    user_template = (PROMPT_DIR / filenames[1]).read_text(encoding="utf-8")
    if system_template.count(OUTPUT_SCHEMA_PLACEHOLDER) != 1:
        raise ValueError(
            f"Baseline B system template must contain exactly one {OUTPUT_SCHEMA_PLACEHOLDER} placeholder."
        )
    if user_template.count(CASE_JSON_PLACEHOLDER) != 1:
        raise ValueError(
            f"Baseline B user template must contain exactly one {CASE_JSON_PLACEHOLDER} placeholder."
        )
    return system_template, user_template


def render_baseline_b_messages(
    case: EvaluationCaseInput,
    *,
    version: str = "baseline_b_v1",
) -> tuple[LLMMessage, LLMMessage]:
    system_template, user_template = load_baseline_b_templates(version)
    schema_json = json.dumps(
        SalesInsightReport.model_json_schema(),
        ensure_ascii=False,
        indent=2,
    )
    case_json = json.dumps(case.model_dump(mode="json"), ensure_ascii=False, indent=2)
    return (
        LLMMessage(
            role=LLMRole.system,
            content=system_template.replace(OUTPUT_SCHEMA_PLACEHOLDER, schema_json),
        ),
        LLMMessage(
            role=LLMRole.user,
            content=user_template.replace(CASE_JSON_PLACEHOLDER, case_json),
        ),
    )


def calculate_messages_sha256(
    messages: list[LLMMessage],
) -> str:
    payload = [
        {"role": message.role.value, "content": message.content}
        for message in messages
    ]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
