from __future__ import annotations

import hashlib
import json
from pathlib import Path

from schemas import EvaluationCaseInput


PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
SUPPORTED_PROMPTS = {"baseline_a_v1": "baseline_a_v1.txt"}
CASE_JSON_PLACEHOLDER = "{{CASE_JSON}}"


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
