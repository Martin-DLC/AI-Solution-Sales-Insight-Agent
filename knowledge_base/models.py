from __future__ import annotations

import hashlib
import math
from collections import Counter
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from schemas.common_models import StrictBaseModel


class KnowledgeDocumentType(str, Enum):
    solution = "solution"
    capability = "capability"
    case_study = "case_study"
    implementation_playbook = "implementation_playbook"
    security_compliance = "security_compliance"
    delivery_constraint = "delivery_constraint"
    integration_requirement = "integration_requirement"
    commercial_rule = "commercial_rule"
    unsupported_scenario = "unsupported_scenario"
    readiness_requirement = "readiness_requirement"


class KnowledgeSourceStatus(str, Enum):
    approved = "approved"
    draft = "draft"
    deprecated = "deprecated"
    expired = "expired"


class KnowledgeConfidentiality(str, Enum):
    internal = "internal"
    restricted = "restricted"
    synthetic_demo = "synthetic_demo"


class KnowledgeSourceMode(str, Enum):
    local_static = "local_static"


class KnowledgeValidationStatus(str, Enum):
    valid = "valid"
    invalid = "invalid"
    draft = "draft"


def _deduplicate_text(values: list[str], field_label: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            raise ValueError(f"{field_label} cannot include empty values.")
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _json_safe(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, bool)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json_safe(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_safe(item) for key, item in value.items())
    return False


class KnowledgeDocument(StrictBaseModel):
    document_id: str
    title: str
    document_type: KnowledgeDocumentType
    status: KnowledgeSourceStatus
    version: str
    effective_from: date | None = None
    effective_until: date | None = None
    owner: str
    summary: str
    content: str
    tags: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    solution_ids: list[str] = Field(default_factory=list)
    source_uri: str
    confidentiality: KnowledgeConfidentiality
    created_at: datetime
    updated_at: datetime

    @field_validator("tags", "industries", "solution_ids")
    @classmethod
    def deduplicate_text_lists(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Knowledge document list field")

    @field_validator("summary")
    @classmethod
    def summary_must_be_useful(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Knowledge document summary must contain at least 8 characters.")
        return value

    @field_validator("source_uri")
    @classmethod
    def source_uri_must_be_local_or_synthetic(cls, value: str) -> str:
        lowered = value.casefold()
        if lowered.startswith(("http://", "https://")):
            raise ValueError("Knowledge document source_uri must be local or synthetic, not an HTTP URL.")
        if "://" in value and not lowered.startswith("synthetic://"):
            raise ValueError("Knowledge document source_uri must use a project-relative path or synthetic:// URI.")
        if value.startswith("/"):
            raise ValueError("Knowledge document source_uri must be a project-relative path, not an absolute path.")
        if ".." in value.split("/"):
            raise ValueError("Knowledge document source_uri must not escape the project root.")
        return value

    @model_validator(mode="after")
    def validate_document(self) -> Self:
        if self.effective_from and self.effective_until and self.effective_until < self.effective_from:
            raise ValueError("Knowledge document effective_until must not be earlier than effective_from.")
        normalized_title = " ".join(self.title.split()).casefold()
        normalized_content = " ".join(self.content.split()).casefold()
        if normalized_content == normalized_title:
            raise ValueError("Knowledge document content must contain more than the title alone.")
        if self.updated_at < self.created_at:
            raise ValueError("Knowledge document updated_at must not be earlier than created_at.")
        return self

    def is_expired(self, *, as_of: date | datetime | None = None) -> bool:
        if self.status is KnowledgeSourceStatus.expired:
            return True
        if self.effective_until is None:
            return False
        reference_date = _as_date(as_of)
        return self.effective_until < reference_date

    def is_retrieval_eligible(self, *, as_of: date | datetime | None = None) -> bool:
        if self.status in {KnowledgeSourceStatus.deprecated, KnowledgeSourceStatus.expired}:
            return False
        return not self.is_expired(as_of=as_of)


class KnowledgeChunk(StrictBaseModel):
    chunk_id: str
    document_id: str
    document_type: KnowledgeDocumentType
    chunk_index: int
    content: str
    token_estimate: int
    tags: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    solution_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    citation_label: str

    @field_validator("tags", "industries", "solution_ids")
    @classmethod
    def deduplicate_text_lists(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Knowledge chunk list field")

    @field_validator("chunk_index")
    @classmethod
    def chunk_index_must_be_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Knowledge chunk chunk_index must be greater than or equal to 0.")
        return value

    @field_validator("token_estimate")
    @classmethod
    def token_estimate_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Knowledge chunk token_estimate must be greater than 0.")
        return value

    @field_validator("metadata")
    @classmethod
    def metadata_must_be_json_safe(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not _json_safe(value):
            raise ValueError("Knowledge chunk metadata must contain only JSON-safe values.")
        return value

    @classmethod
    def build_chunk_id(
        cls,
        *,
        document_id: str,
        chunk_index: int,
        content: str,
    ) -> str:
        digest = hashlib.sha1(f"{document_id}:{chunk_index}:{content}".encode("utf-8")).hexdigest()[:12]
        return f"{document_id}#chunk-{chunk_index:03d}-{digest}"


class KnowledgeBaseManifest(StrictBaseModel):
    knowledge_base_version: str
    document_count: int
    chunk_count: int
    document_type_counts: dict[KnowledgeDocumentType, int]
    solution_ids: list[str] = Field(default_factory=list)
    generated_at: datetime
    source_mode: KnowledgeSourceMode = KnowledgeSourceMode.local_static
    synthetic_data: bool = True
    validation_status: KnowledgeValidationStatus

    @field_validator("document_count", "chunk_count")
    @classmethod
    def counts_must_be_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Knowledge base manifest counts must be zero or greater.")
        return value

    @field_validator("solution_ids")
    @classmethod
    def solution_ids_are_unique(cls, values: list[str]) -> list[str]:
        return _deduplicate_text(values, "Knowledge base manifest solution_ids")

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        if self.source_mode is not KnowledgeSourceMode.local_static:
            raise ValueError("Knowledge base manifest source_mode must be local_static in v1.2A.")
        if self.synthetic_data is not True:
            raise ValueError("Knowledge base manifest synthetic_data must be true in v1.2A.")
        if sum(self.document_type_counts.values()) != self.document_count:
            raise ValueError("Knowledge base manifest document_type_counts must sum to document_count.")
        return self


class KnowledgeBaseCorpus(StrictBaseModel):
    documents: list[KnowledgeDocument] = Field(default_factory=list)
    chunks: list[KnowledgeChunk] = Field(default_factory=list)
    manifest: KnowledgeBaseManifest

    @model_validator(mode="after")
    def validate_corpus(self) -> Self:
        document_ids = [document.document_id for document in self.documents]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("Knowledge document IDs must be unique within the corpus.")

        chunk_ids = [chunk.chunk_id for chunk in self.chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("Knowledge chunk IDs must be unique within the corpus.")

        known_document_ids = set(document_ids)
        for chunk in self.chunks:
            if chunk.document_id not in known_document_ids:
                raise ValueError("Knowledge chunk document_id must reference a document in the corpus.")

        if self.manifest.document_count != len(self.documents):
            raise ValueError("Knowledge base manifest document_count must match the number of documents.")
        if self.manifest.chunk_count != len(self.chunks):
            raise ValueError("Knowledge base manifest chunk_count must match the number of chunks.")

        actual_counts = Counter(document.document_type for document in self.documents)
        if dict(actual_counts) != dict(self.manifest.document_type_counts):
            raise ValueError("Knowledge base manifest document_type_counts must match the corpus documents.")

        corpus_solution_ids = _deduplicate_text(
            [solution_id for document in self.documents for solution_id in document.solution_ids],
            "Knowledge corpus solution_ids",
        )
        if corpus_solution_ids != self.manifest.solution_ids:
            raise ValueError("Knowledge base manifest solution_ids must match the corpus solution IDs.")
        return self


def build_manifest(
    *,
    knowledge_base_version: str,
    documents: list[KnowledgeDocument],
    chunks: list[KnowledgeChunk],
    generated_at: datetime | None = None,
    validation_status: KnowledgeValidationStatus = KnowledgeValidationStatus.valid,
) -> KnowledgeBaseManifest:
    document_type_counts = Counter(document.document_type for document in documents)
    solution_ids = _deduplicate_text(
        [solution_id for document in documents for solution_id in document.solution_ids],
        "Knowledge manifest solution_ids",
    )
    return KnowledgeBaseManifest(
        knowledge_base_version=knowledge_base_version,
        document_count=len(documents),
        chunk_count=len(chunks),
        document_type_counts=dict(document_type_counts),
        solution_ids=solution_ids,
        generated_at=generated_at or datetime.now(UTC),
        source_mode=KnowledgeSourceMode.local_static,
        synthetic_data=True,
        validation_status=validation_status,
    )


def _as_date(value: date | datetime | None) -> date:
    if value is None:
        return datetime.now(UTC).date()
    if isinstance(value, datetime):
        return value.date()
    return value
