from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import Field, ValidationError, field_validator, model_validator

from dataio.jsonl_loader import load_jsonl_models
from knowledge_base.models import (
    KnowledgeBaseManifest,
    KnowledgeDocument,
    KnowledgeDocumentType,
    KnowledgeChunk,
)
from schemas.common_models import StrictBaseModel


DEFAULT_DOCUMENTS_PATH = Path("data/knowledge_base/documents.v1.jsonl")
DEFAULT_CHUNKS_PATH = Path("data/knowledge_base/chunks.v1.jsonl")
DEFAULT_MANIFEST_PATH = Path("data/knowledge_base/manifest.v1.json")
DEFAULT_SCOPE_PATH = Path("data/knowledge_base/demo_solution_scope.v1.json")

_SECRET_PATTERNS = (
    "api_key",
    "authorization",
    "bearer",
    "secret",
    "sk-",
)
_ABSOLUTE_PATH_PREFIXES = ("/Users/", "/home/", "C:\\", "D:\\")
_RUNTIME_MARKERS = ("data/runtime/", ".env", "Hidden Reference Pack", "reference pack")


class DemoSolutionScope(StrictBaseModel):
    scope_version: str
    source_mode: str
    source_solution_id_count: int
    selected_solution_id_count: int
    selected_solution_ids: list[str] = Field(default_factory=list)
    selection_criteria: list[str] = Field(default_factory=list)
    selection_rationale_by_solution: dict[str, str] = Field(default_factory=dict)
    excluded_solution_ids: list[str] = Field(default_factory=list)
    synthetic_data: bool
    notes: list[str] = Field(default_factory=list)

    @field_validator("selected_solution_ids", "selection_criteria", "excluded_solution_ids", "notes")
    @classmethod
    def deduplicate_lists(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if not value:
                raise ValueError("Demo solution scope list fields cannot include empty values.")
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result

    @field_validator("source_solution_id_count", "selected_solution_id_count")
    @classmethod
    def counts_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Demo solution scope counts must be greater than 0.")
        return value

    @model_validator(mode="after")
    def validate_scope(self) -> "DemoSolutionScope":
        if self.source_solution_id_count != 63:
            raise ValueError("Demo solution scope source_solution_id_count must equal 63.")
        if self.selected_solution_id_count != 6:
            raise ValueError("Demo solution scope selected_solution_id_count must equal 6.")
        if len(self.selected_solution_ids) != self.selected_solution_id_count:
            raise ValueError("Demo solution scope selected_solution_ids must match selected_solution_id_count.")
        if self.synthetic_data is not True:
            raise ValueError("Demo solution scope synthetic_data must be true.")
        if "case-local" not in self.source_mode:
            raise ValueError("Demo solution scope source_mode must explain the case-local source boundary.")
        if set(self.selected_solution_ids) & set(self.excluded_solution_ids):
            raise ValueError("Demo solution scope selected and excluded solution IDs must not overlap.")
        if set(self.selection_rationale_by_solution) != set(self.selected_solution_ids):
            raise ValueError("Demo solution scope must provide rationale for each selected solution ID.")
        if len(self.excluded_solution_ids) + len(self.selected_solution_ids) != self.source_solution_id_count:
            raise ValueError("Demo solution scope selected and excluded solution IDs must add up to the source solution count.")
        return self


def load_demo_solution_scope(path: str | Path = DEFAULT_SCOPE_PATH) -> DemoSolutionScope:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Demo solution scope file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Demo solution scope file contains invalid JSON: {path}") from exc
    return DemoSolutionScope.model_validate(payload)


def load_knowledge_documents(path: str | Path = DEFAULT_DOCUMENTS_PATH) -> list[KnowledgeDocument]:
    return load_jsonl_models(path, KnowledgeDocument)


def load_knowledge_chunks(path: str | Path = DEFAULT_CHUNKS_PATH) -> list[KnowledgeChunk]:
    return load_jsonl_models(path, KnowledgeChunk)


def load_knowledge_manifest(path: str | Path = DEFAULT_MANIFEST_PATH) -> KnowledgeBaseManifest:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Knowledge manifest file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Knowledge manifest file contains invalid JSON: {path}") from exc
    return KnowledgeBaseManifest.model_validate(payload)


def validate_knowledge_base_dataset(
    *,
    documents: list[KnowledgeDocument],
    chunks: list[KnowledgeChunk],
    manifest: KnowledgeBaseManifest,
    demo_scope: DemoSolutionScope,
    allowed_solution_ids: set[str],
) -> None:
    if len(documents) != 20:
        raise ValueError(f"Knowledge base must contain exactly 20 documents; got {len(documents)}.")

    document_ids = [document.document_id for document in documents]
    if len(document_ids) != len(set(document_ids)):
        raise ValueError("Knowledge base document IDs must be unique.")

    document_types = {document.document_type for document in documents}
    expected_types = set(KnowledgeDocumentType)
    if document_types != expected_types:
        missing = sorted(value.value for value in expected_types - document_types)
        raise ValueError(f"Knowledge base must cover all 10 document types; missing: {missing}.")

    selected_solution_ids = set(demo_scope.selected_solution_ids)
    if len(selected_solution_ids) != 6:
        raise ValueError("Knowledge base demo scope must select exactly 6 solution IDs.")
    if not selected_solution_ids.issubset(allowed_solution_ids):
        raise ValueError("Knowledge base demo scope contains solution IDs outside the source 63-ID set.")

    for document in documents:
        _ensure_safe_values(document.document_id, document.source_uri, *document.solution_ids, *document.tags, *document.industries)
        for solution_id in document.solution_ids:
            if solution_id not in allowed_solution_ids:
                raise ValueError(f"Knowledge document {document.document_id} uses unknown solution_id.")
            if solution_id not in selected_solution_ids:
                raise ValueError(f"Knowledge document {document.document_id} references a solution outside the demo scope.")

    solution_documents = [document for document in documents if document.document_type is KnowledgeDocumentType.solution]
    if len(solution_documents) != 6:
        raise ValueError(f"Knowledge base must contain exactly 6 solution documents; got {len(solution_documents)}.")

    solution_document_ids = {document.solution_ids[0] for document in solution_documents}
    if solution_document_ids != selected_solution_ids:
        raise ValueError("Knowledge base solution documents must cover every selected solution exactly once.")

    for solution_id in demo_scope.selected_solution_ids:
        non_solution_refs = [
            document.document_id
            for document in documents
            if document.document_type is not KnowledgeDocumentType.solution and solution_id in document.solution_ids
        ]
        if len(non_solution_refs) < 2:
            raise ValueError(f"Selected solution {solution_id} must appear in at least 2 non-solution documents.")

    if not (40 <= len(chunks) <= 70):
        raise ValueError(f"Knowledge base must contain 40 to 70 chunks; got {len(chunks)}.")

    chunk_ids = [chunk.chunk_id for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("Knowledge chunk IDs must be unique.")

    documents_by_id = {document.document_id: document for document in documents}
    chunk_indexes_by_document: dict[str, list[int]] = {}
    for chunk in chunks:
        _ensure_safe_values(chunk.chunk_id, chunk.citation_label, chunk.document_id, *chunk.solution_ids)
        document = documents_by_id.get(chunk.document_id)
        if document is None:
            raise ValueError(f"Knowledge chunk {chunk.chunk_id} references an unknown document.")
        chunk_indexes_by_document.setdefault(chunk.document_id, []).append(chunk.chunk_index)
        if chunk.document_type is not document.document_type:
            raise ValueError(f"Knowledge chunk {chunk.chunk_id} has a document_type mismatch.")
        if chunk.tags != document.tags or chunk.industries != document.industries or chunk.solution_ids != document.solution_ids:
            raise ValueError(f"Knowledge chunk {chunk.chunk_id} metadata does not match its source document.")
        if chunk.metadata.get("status") != document.status.value:
            raise ValueError(f"Knowledge chunk {chunk.chunk_id} must inherit document status.")
        if chunk.metadata.get("retrieval_eligible") != document.is_retrieval_eligible():
            raise ValueError(f"Knowledge chunk {chunk.chunk_id} must inherit retrieval eligibility.")

    for document_id, indexes in chunk_indexes_by_document.items():
        expected = list(range(len(indexes)))
        if sorted(indexes) != expected:
            raise ValueError(f"Knowledge document {document_id} must have continuous chunk_index values from 0.")

    if manifest.document_count != len(documents):
        raise ValueError("Knowledge manifest document_count does not match the document file.")
    if manifest.chunk_count != len(chunks):
        raise ValueError("Knowledge manifest chunk_count does not match the chunk file.")
    if manifest.synthetic_data is not True:
        raise ValueError("Knowledge manifest synthetic_data must be true.")
    if manifest.source_mode.value != "local_static":
        raise ValueError("Knowledge manifest source_mode must be local_static.")
    if set(manifest.solution_ids) != selected_solution_ids:
        raise ValueError("Knowledge manifest solution_ids must match the selected demo solution set.")


def write_jsonl(path: str | Path, records: list[dict[str, Any]]) -> None:
    text = "\n".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) for record in records) + "\n"
    _atomic_write_text(Path(path), text)


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _atomic_write_text(Path(path), text)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def _ensure_safe_values(*values: str) -> None:
    for value in values:
        lowered = value.casefold()
        if any(marker in lowered for marker in _SECRET_PATTERNS):
            raise ValueError("Knowledge base dataset must not contain secret-like fields or values.")
        if any(value.startswith(prefix) for prefix in _ABSOLUTE_PATH_PREFIXES):
            raise ValueError("Knowledge base dataset must not contain absolute local paths.")
        if any(marker.casefold() in lowered for marker in _RUNTIME_MARKERS):
            raise ValueError("Knowledge base dataset must not contain runtime paths or hidden reference markers.")
