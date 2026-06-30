from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, date, datetime
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from knowledge_base.dataset import load_demo_solution_scope
from knowledge_base.models import (
    KnowledgeChunk,
    KnowledgeConfidentiality,
    KnowledgeDocument,
    KnowledgeDocumentType,
    KnowledgeSourceStatus,
)
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


class SolutionScopeV2(StrictBaseModel):
    primary_solution_id: str | None = None
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

        if self.primary_solution_id is not None and self.primary_solution_id not in applicable:
            raise ValueError("primary_solution_id must belong to applicable_solution_ids.")
        if applicable & excluded:
            raise ValueError("applicable_solution_ids and excluded_solution_ids must not overlap.")
        if not applicable.issubset(demo_solution_ids):
            raise ValueError("All applicable_solution_ids must belong to the 6-solution demo scope.")
        if not excluded.issubset(demo_solution_ids):
            raise ValueError("All excluded_solution_ids must belong to the 6-solution demo scope.")

        if self.scope_type is SolutionScopeType.solution_specific:
            if len(self.applicable_solution_ids) != 1:
                raise ValueError("solution_specific scope must contain exactly 1 applicable solution.")
            if self.primary_solution_id is None:
                raise ValueError("solution_specific scope requires primary_solution_id.")
        if self.scope_type is SolutionScopeType.multi_solution:
            if len(self.applicable_solution_ids) < 2:
                raise ValueError("multi_solution scope must contain at least 2 applicable solutions.")
            if self.primary_solution_id is None:
                raise ValueError("multi_solution scope requires primary_solution_id.")
        if self.scope_type is SolutionScopeType.global_policy:
            if len(self.applicable_solution_ids) != len(demo_solution_ids):
                raise ValueError("global_policy scope must explicitly cover all demo solutions.")
        if self.scope_type is SolutionScopeType.cross_cutting_requirement:
            if len(self.applicable_solution_ids) < 1:
                raise ValueError("cross_cutting_requirement scope must declare at least 1 applicable solution.")
            if self.primary_solution_id is None:
                raise ValueError("cross_cutting_requirement scope requires primary_solution_id.")
        return self


class SolutionScopedRecordV2(StrictBaseModel):
    contract_version: Literal["v2"] = "v2"
    primary_solution_id: str | None = None
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
        SolutionScopeV2.model_validate(
            {
                "primary_solution_id": self.primary_solution_id,
                "applicable_solution_ids": self.applicable_solution_ids,
                "excluded_solution_ids": self.excluded_solution_ids,
                "scope_type": self.scope_type,
                "scope_notes": self.scope_notes,
            }
        )
        return self

    def to_scope(self) -> SolutionScopeV2:
        return SolutionScopeV2(
            primary_solution_id=self.primary_solution_id,
            applicable_solution_ids=list(self.applicable_solution_ids),
            excluded_solution_ids=list(self.excluded_solution_ids),
            scope_type=self.scope_type,
            scope_notes=self.scope_notes,
        )


class KnowledgeDocumentV2(SolutionScopedRecordV2):
    document_id: str
    title: str = "Synthetic V2 Document"
    document_type: KnowledgeDocumentType
    status: KnowledgeSourceStatus
    version: str = "v1"
    effective_from: date | None = None
    effective_until: date | None = None
    owner: str = "demo-owner"
    summary: str = "这是一个足够长的默认摘要文本。"
    content: str = "这是一个足够长的默认正文内容，不只是标题。"
    tags: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    source_uri: str = "synthetic://v2/default-document"
    confidentiality: KnowledgeConfidentiality = KnowledgeConfidentiality.synthetic_demo
    created_at: datetime = datetime(2026, 6, 29, 0, 0, 0, tzinfo=UTC)
    updated_at: datetime = datetime(2026, 6, 29, 0, 0, 0, tzinfo=UTC)

    @field_validator("tags", "industries")
    @classmethod
    def deduplicate_text_lists(cls, values: list[str]) -> list[str]:
        return _deduplicate(values, "Knowledge document v2 list field")

    @model_validator(mode="after")
    def validate_payload_with_v1_rules(self) -> Self:
        KnowledgeDocument.model_validate(
            {
                "document_id": self.document_id,
                "title": self.title,
                "document_type": self.document_type,
                "status": self.status,
                "version": self.version,
                "effective_from": self.effective_from,
                "effective_until": self.effective_until,
                "owner": self.owner,
                "summary": self.summary,
                "content": self.content,
                "tags": list(self.tags),
                "industries": list(self.industries),
                "solution_ids": list(self.applicable_solution_ids),
                "source_uri": self.source_uri,
                "confidentiality": self.confidentiality,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }
        )
        return self

    @classmethod
    def from_v1(
        cls,
        source: KnowledgeDocument,
        *,
        scope: SolutionScopeV2,
    ) -> "KnowledgeDocumentV2":
        return cls(
            document_id=source.document_id,
            title=source.title,
            document_type=source.document_type,
            status=source.status,
            version=source.version,
            effective_from=source.effective_from,
            effective_until=source.effective_until,
            owner=source.owner,
            summary=source.summary,
            content=source.content,
            tags=list(source.tags),
            industries=list(source.industries),
            source_uri=source.source_uri,
            confidentiality=source.confidentiality,
            created_at=source.created_at,
            updated_at=source.updated_at,
            primary_solution_id=scope.primary_solution_id,
            applicable_solution_ids=list(scope.applicable_solution_ids),
            excluded_solution_ids=list(scope.excluded_solution_ids),
            scope_type=scope.scope_type,
            scope_notes=scope.scope_notes,
        )

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
    chunk_index: int = 0
    content: str = "这是一个用于兼容旧测试的默认 chunk 正文。"
    token_estimate: int = 10
    tags: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    citation_label: str = "Synthetic V2 Chunk"

    @field_validator("tags", "industries")
    @classmethod
    def deduplicate_text_lists(cls, values: list[str]) -> list[str]:
        return _deduplicate(values, "Knowledge chunk v2 list field")

    @model_validator(mode="after")
    def validate_payload_with_v1_rules(self) -> Self:
        KnowledgeChunk.model_validate(
            {
                "chunk_id": self.chunk_id,
                "document_id": self.document_id,
                "document_type": self.document_type,
                "chunk_index": self.chunk_index,
                "content": self.content,
                "token_estimate": self.token_estimate,
                "tags": list(self.tags),
                "industries": list(self.industries),
                "solution_ids": list(self.applicable_solution_ids),
                "metadata": deepcopy(self.metadata),
                "citation_label": self.citation_label,
            }
        )
        return self

    @classmethod
    def from_v1(
        cls,
        source: KnowledgeChunk,
        *,
        scope: SolutionScopeV2,
    ) -> "KnowledgeChunkV2":
        return cls(
            chunk_id=source.chunk_id,
            document_id=source.document_id,
            document_type=source.document_type,
            chunk_index=source.chunk_index,
            content=source.content,
            token_estimate=source.token_estimate,
            tags=list(source.tags),
            industries=list(source.industries),
            metadata=deepcopy(source.metadata),
            citation_label=source.citation_label,
            primary_solution_id=scope.primary_solution_id,
            applicable_solution_ids=list(scope.applicable_solution_ids),
            excluded_solution_ids=list(scope.excluded_solution_ids),
            scope_type=scope.scope_type,
            scope_notes=scope.scope_notes,
        )


def document_content_projection_v1(
    document: KnowledgeDocument | KnowledgeDocumentV2,
) -> dict[str, object]:
    return {
        "document_id": document.document_id,
        "title": document.title,
        "document_type": document.document_type.value,
        "status": document.status.value,
        "version": document.version,
        "effective_from": _serialize_date(getattr(document, "effective_from", None)),
        "effective_until": _serialize_date(getattr(document, "effective_until", None)),
        "owner": document.owner,
        "summary": document.summary,
        "content": document.content,
        "tags": list(document.tags),
        "industries": list(document.industries),
        "source_uri": document.source_uri,
        "confidentiality": document.confidentiality.value,
        "created_at": _serialize_datetime(document.created_at),
        "updated_at": _serialize_datetime(document.updated_at),
    }


def chunk_content_projection_v1(
    chunk: KnowledgeChunk | KnowledgeChunkV2,
) -> dict[str, object]:
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "document_type": chunk.document_type.value,
        "chunk_index": chunk.chunk_index,
        "content": chunk.content,
        "token_estimate": chunk.token_estimate,
        "tags": list(chunk.tags),
        "industries": list(chunk.industries),
        "metadata": deepcopy(chunk.metadata),
        "citation_label": chunk.citation_label,
    }


def content_projection_hash(payload: dict[str, object]) -> str:
    normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


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


def _serialize_date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _serialize_datetime(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
