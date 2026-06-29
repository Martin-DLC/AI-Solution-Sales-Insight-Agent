from __future__ import annotations

from knowledge_base.retrieval.tokenizer import normalize_lexical_text, tokenize_lexical_text


def test_normalize_lexical_text_nfkc_lowercases_and_collapses_spaces() -> None:
    assert normalize_lexical_text("ＡＰＩ   / CRM 集成") == "api / crm 集成"


def test_tokenize_lexical_text_preserves_identifiers_and_cjk_bigrams() -> None:
    tokens = tokenize_lexical_text("solution-ai-ops API / CRM 集成要求")

    assert "solution-ai-ops" in tokens
    assert "api" in tokens
    assert "crm" in tokens
    assert "集成" in tokens
    assert "成要" in tokens


def test_tokenize_lexical_text_preserves_single_cjk_character() -> None:
    assert tokenize_lexical_text("A 类") == ["a", "类"]


def test_tokenize_lexical_text_returns_empty_for_blank_text() -> None:
    assert tokenize_lexical_text("   ") == []
