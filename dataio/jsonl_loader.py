from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from dataio.errors import DatasetLoadError, DuplicateCaseIdError


ModelT = TypeVar("ModelT", bound=BaseModel)


def _field_summary(error: ValidationError) -> str:
    fields: list[str] = []
    for item in error.errors():
        location = ".".join(str(part) for part in item.get("loc", ()))
        message = item.get("msg", "validation error")
        fields.append(f"{location}: {message}" if location else message)
    return "; ".join(fields)


def load_jsonl_models(path: str | Path, model_type: type[ModelT]) -> list[ModelT]:
    dataset_path = Path(path)
    records: list[ModelT] = []
    seen_case_ids: dict[str, int] = {}

    try:
        lines = dataset_path.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError as exc:
        raise DatasetLoadError(
            f"Failed to load dataset file {dataset_path}: line unknown: file does not exist."
        ) from exc
    except OSError as exc:
        raise DatasetLoadError(
            f"Failed to load dataset file {dataset_path}: line unknown: {exc}"
        ) from exc

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue

        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetLoadError(
                f"Failed to load dataset file {dataset_path}: line {line_number}: JSON error: {exc.msg}."
            ) from exc

        if not isinstance(payload, dict):
            raise DatasetLoadError(
                f"Failed to load dataset file {dataset_path}: line {line_number}: each JSONL record must be a JSON object."
            )

        try:
            model = model_type.model_validate(payload)
        except ValidationError as exc:
            raise DatasetLoadError(
                f"Failed to load dataset file {dataset_path}: line {line_number}: validation error: {_field_summary(exc)}."
            ) from exc

        case_id = getattr(model, "case_id", None)
        if isinstance(case_id, str):
            if case_id in seen_case_ids:
                raise DuplicateCaseIdError(case_id, seen_case_ids[case_id], line_number)
            seen_case_ids[case_id] = line_number

        records.append(model)

    if not records:
        raise DatasetLoadError(
            f"Failed to load dataset file {dataset_path}: line unknown: file contains no valid records."
        )

    return records
