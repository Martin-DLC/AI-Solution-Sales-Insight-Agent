from __future__ import annotations

from pathlib import Path

from dataio.errors import DatasetBoundaryError
from dataio.jsonl_loader import load_jsonl_models
from schemas import EvaluationCaseInput


def load_runtime_cases(path: str | Path) -> list[EvaluationCaseInput]:
    """Load runtime Evaluation Case inputs for Agent execution.

    This module may be used by Agent runtime code. It must not load Hidden
    Reference Pack files or answer data.
    """

    dataset_path = Path(path)
    lowered_path = str(dataset_path).casefold()
    forbidden_keywords = ("reference", "answer", "hidden")
    if any(keyword in lowered_path for keyword in forbidden_keywords):
        raise DatasetBoundaryError(str(dataset_path))
    return load_jsonl_models(dataset_path, EvaluationCaseInput)
