from __future__ import annotations

import math
import re
from typing import Iterable

from knowledge_base.models import KnowledgeChunk, KnowledgeDocument


_SECTION_PATTERN = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?;；.])")


def build_knowledge_chunks(
    documents: list[KnowledgeDocument],
    *,
    max_chars: int = 900,
    min_chars: int = 120,
) -> list[KnowledgeChunk]:
    if max_chars <= 0:
        raise ValueError("Chunk max_chars must be greater than 0.")
    if min_chars <= 0:
        raise ValueError("Chunk min_chars must be greater than 0.")
    if min_chars > max_chars:
        raise ValueError("Chunk min_chars must not be greater than max_chars.")

    chunks: list[KnowledgeChunk] = []
    for document in documents:
        section_chunks = _build_document_chunks(
            document,
            max_chars=max_chars,
            min_chars=min_chars,
        )
        chunks.extend(section_chunks)
    return chunks


def _build_document_chunks(
    document: KnowledgeDocument,
    *,
    max_chars: int,
    min_chars: int,
) -> list[KnowledgeChunk]:
    raw_sections = _split_markdown_sections(document.content)
    normalized_sections = [
        (title, _normalize_whitespace(body))
        for title, body in raw_sections
        if _normalize_whitespace(body)
    ]
    if not normalized_sections:
        normalized_sections = [("Overview", _normalize_whitespace(document.content))]

    chunk_bodies: list[tuple[str, str]] = []
    for section_title, section_body in normalized_sections:
        for piece in _split_section_body(section_body, max_chars=max_chars):
            chunk_bodies.append((section_title, piece))

    merged = _merge_short_chunks(chunk_bodies, min_chars=min_chars, max_chars=max_chars)
    results: list[KnowledgeChunk] = []
    for index, (section_title, content) in enumerate(merged):
        results.append(
            KnowledgeChunk(
                chunk_id=KnowledgeChunk.build_chunk_id(
                    document_id=document.document_id,
                    chunk_index=index,
                    content=content,
                ),
                document_id=document.document_id,
                document_type=document.document_type,
                chunk_index=index,
                content=content,
                token_estimate=_estimate_tokens(content),
                tags=list(document.tags),
                industries=list(document.industries),
                solution_ids=list(document.solution_ids),
                metadata={
                    "section_title": section_title,
                    "source_uri": document.source_uri,
                    "version": document.version,
                    "status": document.status.value,
                    "confidentiality": document.confidentiality.value,
                    "retrieval_eligible": document.is_retrieval_eligible(),
                    "synthetic_data": True,
                    "public_demo_data": True,
                },
                citation_label=f"{document.title} - {section_title}",
            )
        )
    return results


def _split_markdown_sections(content: str) -> list[tuple[str, str]]:
    matches = list(_SECTION_PATTERN.finditer(content))
    if not matches:
        return [("Overview", content)]

    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        title = match.group("title").strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        body = content[start:end].strip()
        sections.append((title, body))
    return sections


def _split_section_body(body: str, *, max_chars: int) -> list[str]:
    paragraphs = [_normalize_whitespace(part) for part in re.split(r"\n\s*\n", body) if _normalize_whitespace(part)]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_paragraph(paragraph, max_chars=max_chars))
            continue

        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = paragraph

    if current:
        chunks.append(current)
    return chunks


def _split_long_paragraph(paragraph: str, *, max_chars: int) -> list[str]:
    sentences = [part.strip() for part in _SENTENCE_BOUNDARY.split(paragraph) if part.strip()]
    if not sentences:
        return [_hard_split(paragraph, max_chars=max_chars)]

    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_hard_split_sentence(sentence, max_chars=max_chars))
            continue

        candidate = sentence if not current else f"{current} {sentence}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = sentence

    if current:
        chunks.append(current)
    return chunks


def _hard_split_sentence(sentence: str, *, max_chars: int) -> list[str]:
    parts: list[str] = []
    remaining = sentence
    while len(remaining) > max_chars:
        cut = remaining.rfind(" ", 0, max_chars)
        if cut < max_chars // 2:
            cut = max_chars
        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        parts.append(remaining)
    return parts


def _hard_split(value: str, *, max_chars: int) -> str:
    return value[:max_chars].strip()


def _merge_short_chunks(
    chunks: list[tuple[str, str]],
    *,
    min_chars: int,
    max_chars: int,
) -> list[tuple[str, str]]:
    if not chunks:
        return []

    merged: list[tuple[str, str]] = []
    for section_title, content in chunks:
        if not merged:
            merged.append((section_title, content))
            continue

        previous_title, previous_content = merged[-1]
        if (
            previous_title == section_title
            and len(content) < min_chars
            and len(previous_content) + 2 + len(content) <= max_chars
        ):
            merged[-1] = (previous_title, f"{previous_content}\n{content}")
        else:
            merged.append((section_title, content))
    return merged


def _normalize_whitespace(value: str) -> str:
    lines = [line.strip() for line in value.strip().splitlines()]
    return "\n".join(line for line in lines if line)


def _estimate_tokens(content: str) -> int:
    return max(1, math.ceil(len(content) / 4))
