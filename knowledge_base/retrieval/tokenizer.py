from __future__ import annotations

import re
import unicodedata


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*|[\u4e00-\u9fff]+")


def normalize_lexical_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(normalized.split())


def tokenize_lexical_text(text: str) -> list[str]:
    normalized = normalize_lexical_text(text)
    if not normalized:
        return []

    tokens: list[str] = []
    for match in _TOKEN_PATTERN.finditer(normalized):
        value = match.group(0)
        if not value:
            continue
        if _is_cjk(value):
            tokens.extend(_tokenize_cjk(value))
        else:
            tokens.append(value)
    return tokens


def _tokenize_cjk(value: str) -> list[str]:
    if len(value) == 1:
        return [value]
    return [value[index : index + 2] for index in range(len(value) - 1)]


def _is_cjk(value: str) -> bool:
    return all("\u4e00" <= char <= "\u9fff" for char in value)
