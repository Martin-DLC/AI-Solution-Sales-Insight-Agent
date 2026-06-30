from __future__ import annotations

from datetime import UTC, date, datetime
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, field_validator, model_validator

from knowledge_base.dataset import load_demo_solution_scope
from knowledge_base.models import KnowledgeDocumentType, KnowledgeSourceStatus
from schemas.common_models import StrictBaseModel

DEMO_SCOPE_PATH = Path("data/knowledge_base/demo_solution_scope.v1.json")


class SolutionScopeType(str, Enum):
    solution_specific = "solution_specific"
    multi_solution = "multi_solution"
    global_policy = "global_policy"
    cross_cutting_requirement = "cross_cutting_requirement"


@lru_cache(maxsize=1)
def load_demo_solution_ids_v2() -> tuple[str, ...]:
    scope = load_demo_solution_scope(DEMO_SCOPE_PATH)
    return tuple(scope.selected_solution_ids)


def _deduplicate(values: list[str], field_label: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            raise ValueError(f"{field_label} cannot include empty values.")
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


class SolutionScopedRecordV2(StrictBaseModel):
    primary_solution_id: str
    applicable_solution_ids: list[str] = Field(default_factory=list)
    excluded_solution_ids: list[str] = Field(default_factory=list)
    scope_type: SolutionScopeType
    scope_notes: str

    @field_validator("applicable_solution_ids", "excluded_solution_ids")
    @classmethod
    def deduplicate_solution_ids(cls, values: list[str]) -> list[str]:
        return _deduplicate(values, "Solution scope IDs")

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        demo_solution_ids = set(load_demo_solution_ids_v2())
        applicable = set(self.applicable_solution_ids)
        excluded = set(self.excluded_solution_ids)

        if self.primary_solution_id not in applicable:
            raise ValueError("primary_solution_id must belong to applicable_solution_ids.")
        if applicable & excluded:
            raise ValueError("applicable_solution_ids and excluded_solution_ids must not overlap.")
        if not applicable.issubset(demo_solution_ids):
            raise ValueError("All applicable_solution_ids must belong to the 6-solution demo scope.")
        if not excluded.issubset(demo_solution_ids):
            raise ValueError("All excluded_solution_ids must belong to the 6-solution demo scope.")

        if self.scope_type is SolutionScopeType.solution_specific and len(self.applicable_solution_ids) != 1:
            raise ValueError("solution_specific scope must contain exactly 1 applicable solution.")
        if self.scope_type is SolutionScopeType.multi_solution and len(self.applicable_solution_ids) < 2:
            raise ValueError("multi_solution scope must contain at least 2 applicable solutions.")
        if self.scope_type is SolutionScopeType.global_policy and len(self.applicable_solution_ids) != len(demo_solution_ids):
            raise ValueError("global_policy scope must explicitly cover all demo solutions.")
        if self.scope_type is SolutionScopeType.cross_cutting_requirement and len(self.applicable_solution_ids) < 1:
            raise ValueError("cross_cutting_requirement scope must declare at least 1 applicable solution.")
        return self


class KnowledgeDocumentV2(SolutionScopedRecordV2):
    document_id: str
    document_type: KnowledgeDocumentType
    status: KnowledgeSourceStatus
    effective_from: date | None = None
    effective_until: date | None = None
    tags: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)

    @field_validator("tags", "industries")
    @classmethod
    def deduplicate_text_lists(cls, values: list[str]) -> list[str]:
        return _deduplicate(values, "Knowledge document v2 list field")

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if self.effective_from and self.effective_until and self.effective_until < self.effective_from:
            raise ValueError("effective_until must not be earlier than effective_from.")
        return self

    def is_active(self, *, as_of: date | None = None) -> bool:
        reference_date = as_of or datetime.now(UTC).date()
        if self.status in {KnowledgeSourceStatus.deprecated, KnowledgeSourceStatus.expired}:
            return False
        if self.effective_from and reference_date < self.effective_from:
            return False
        if self.effective_until and reference_date > self.effective_until:
            return False
        return True


class KnowledgeChunkV2(SolutionScopedRecordV2):
    chunk_id: str
    document_id: str
    document_type: KnowledgeDocumentType
    tags: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)

    @field_validator("tags", "industries")
    @classmethod
    def deduplicate_text_lists(cls, values: list[str]) -> list[str]:
        return _deduplicate(values, "Knowledge chunk v2 list field")


def validate_chunk_scope_against_document_v2(
    *,
    chunk: KnowledgeChunkV2,
    document: KnowledgeDocumentV2,
) -> None:
    if chunk.document_id != document.document_id:
        raise ValueError("Chunk document_id must match its parent document.")
    if chunk.document_type is not document.document_type:
        raise ValueError("Chunk document_type must match its parent document.")
    if not set(chunk.applicable_solution_ids).issubset(set(document.applicable_solution_ids)):
        raise ValueError("Chunk applicable_solution_ids must not expand beyond the parent document scope.")
    if not set(document.excluded_solution_ids).issubset(set(chunk.excluded_solution_ids)):
        raise ValueError("Chunk excluded_solution_ids must preserve parent document exclusions.")

