from __future__ import annotations

from pathlib import Path

from dataio.jsonl_loader import load_jsonl_models
from schemas import HiddenReferencePack


def load_reference_packs(path: str | Path) -> list[HiddenReferencePack]:
    """Load Hidden Reference Pack data for offline Evaluation Pipeline only.

    This module must not be called by Agent runtime code.
    """

    return load_jsonl_models(path, HiddenReferencePack)
