from __future__ import annotations

import json
from typing import Any

from schemas.common_models import StrictBaseModel

from evaluation.multi_maas.models import MULTI_MAAS_BOUNDARY_NOTE, MultiMaaSEvaluationCase


class MultiMaaSScore(StrictBaseModel):
    schema_valid: bool | None
    expected_fields_present: dict[str, bool]
    answer_quality_score: float | None = None
    evidence_grounding_score: float | None = None
    boundary_note: str = MULTI_MAAS_BOUNDARY_NOTE


def score_output(case: MultiMaaSEvaluationCase, output_text: str | None) -> MultiMaaSScore:
    if output_text is None or not output_text.strip():
        return MultiMaaSScore(
            schema_valid=None,
            expected_fields_present={field: False for field in case.expected_output_fields},
            answer_quality_score=None,
            evidence_grounding_score=None,
        )

    parsed = _try_parse_json(output_text)
    normalized = output_text.casefold()
    expected_fields_present = {
        field: _field_present(field, normalized, parsed) for field in case.expected_output_fields
    }
    schema_valid = bool(parsed) if case.requires_structured_output else True
    field_rate = sum(1 for present in expected_fields_present.values() if present) / len(expected_fields_present)
    length_score = 1.0 if 80 <= len(output_text) <= 3000 else 0.5
    risk_score = 1.0
    if case.risk_level == "high":
        risk_score = 1.0 if any(token in normalized for token in ("risk", "human_review", "fallback", "review")) else 0.5
    answer_quality_score = round((field_rate * 0.7 + length_score * 0.2 + risk_score * 0.1) * 100, 4)
    evidence_grounding_score = None if case.requires_evidence else 0.0
    return MultiMaaSScore(
        schema_valid=schema_valid,
        expected_fields_present=expected_fields_present,
        answer_quality_score=answer_quality_score,
        evidence_grounding_score=evidence_grounding_score,
    )


def _try_parse_json(output_text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _field_present(field: str, normalized_output: str, parsed: dict[str, Any]) -> bool:
    if field in parsed:
        return True
    normalized_field = field.casefold()
    return normalized_field in normalized_output or normalized_field.replace("_", " ") in normalized_output
