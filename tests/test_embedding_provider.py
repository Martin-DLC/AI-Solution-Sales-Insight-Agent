from __future__ import annotations

from types import SimpleNamespace

import pytest

from knowledge_base.retrieval.embeddings import (
    DEFAULT_DOCUMENT_PREFIX,
    DEFAULT_QUERY_PREFIX,
    EmbeddingDependencyError,
    FakeEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)


def test_fake_provider_is_deterministic() -> None:
    provider = FakeEmbeddingProvider(dimension=6)

    first = provider.encode_queries(["同一个查询"])[0]
    second = provider.encode_queries(["同一个查询"])[0]

    assert first == second


def test_fake_provider_distinguishes_query_and_document_modes() -> None:
    provider = FakeEmbeddingProvider(dimension=6)

    query_vector = provider.encode_queries(["客户主数据"])[0]
    document_vector = provider.encode_documents(["客户主数据"])[0]

    assert query_vector != document_vector


def test_fake_provider_dimension_is_stable() -> None:
    provider = FakeEmbeddingProvider(dimension=10)

    vectors = provider.encode_documents(["a", "b"])

    assert all(len(vector) == 10 for vector in vectors)


def test_sentence_transformer_provider_is_lazy(monkeypatch) -> None:
    provider = SentenceTransformerEmbeddingProvider()
    called = {"value": False}

    def fake_import(name: str):
        called["value"] = True
        raise AssertionError("should not import during initialization")

    monkeypatch.setattr("knowledge_base.retrieval.embeddings._import_optional_dependency", fake_import)

    assert provider.provider_id.startswith("sentence_transformers:")
    assert called["value"] is False


def test_sentence_transformer_provider_raises_clear_error_when_dependency_missing(monkeypatch) -> None:
    provider = SentenceTransformerEmbeddingProvider()
    monkeypatch.setattr("knowledge_base.retrieval.embeddings._import_optional_dependency", lambda _: None)

    with pytest.raises(EmbeddingDependencyError, match="sentence-transformers is not installed"):
        provider.encode_queries(["test"])


def test_sentence_transformer_provider_uses_query_prefix_fallback(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeModel:
        def encode(self, texts, **kwargs):
            captured["texts"] = list(texts)
            captured["kwargs"] = kwargs
            return [[1.0, 0.0, 0.0, 0.0]]

    monkeypatch.setattr(
        "knowledge_base.retrieval.embeddings._import_optional_dependency",
        lambda _: SimpleNamespace(SentenceTransformer=lambda *args, **kwargs: FakeModel()),
    )

    provider = SentenceTransformerEmbeddingProvider(expected_dimension=4)
    provider.encode_queries(["hello"])

    assert captured["texts"] == [DEFAULT_QUERY_PREFIX + "hello"]


def test_sentence_transformer_provider_uses_document_prefix_fallback(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeModel:
        def encode(self, texts, **kwargs):
            captured["texts"] = list(texts)
            captured["kwargs"] = kwargs
            return [[1.0, 0.0, 0.0, 0.0]]

    monkeypatch.setattr(
        "knowledge_base.retrieval.embeddings._import_optional_dependency",
        lambda _: SimpleNamespace(SentenceTransformer=lambda *args, **kwargs: FakeModel()),
    )

    provider = SentenceTransformerEmbeddingProvider(expected_dimension=4)
    provider.encode_documents(["hello"])

    assert captured["texts"] == [DEFAULT_DOCUMENT_PREFIX + "hello"]


def test_sentence_transformer_provider_prefers_native_query_api(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeModel:
        def encode_query(self, texts, **kwargs):
            captured["texts"] = list(texts)
            return [[1.0, 0.0, 0.0, 0.0]]

    monkeypatch.setattr(
        "knowledge_base.retrieval.embeddings._import_optional_dependency",
        lambda _: SimpleNamespace(SentenceTransformer=lambda *args, **kwargs: FakeModel()),
    )

    provider = SentenceTransformerEmbeddingProvider(expected_dimension=4)
    provider.encode_queries(["query"])

    assert captured["texts"] == ["query"]


def test_sentence_transformer_provider_defaults_to_local_files_only(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_factory(*args, **kwargs):
        captured["kwargs"] = kwargs
        return SimpleNamespace(encode=lambda texts, **encode_kwargs: [[1.0, 0.0, 0.0, 0.0]])

    monkeypatch.setattr(
        "knowledge_base.retrieval.embeddings._import_optional_dependency",
        lambda _: SimpleNamespace(SentenceTransformer=fake_factory),
    )

    provider = SentenceTransformerEmbeddingProvider(expected_dimension=4)
    provider.encode_documents(["doc"])

    assert captured["kwargs"]["local_files_only"] is True


def test_sentence_transformer_provider_allows_explicit_model_download(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_factory(*args, **kwargs):
        captured["kwargs"] = kwargs
        return SimpleNamespace(encode=lambda texts, **encode_kwargs: [[1.0, 0.0, 0.0, 0.0]])

    monkeypatch.setattr(
        "knowledge_base.retrieval.embeddings._import_optional_dependency",
        lambda _: SimpleNamespace(SentenceTransformer=fake_factory),
    )

    provider = SentenceTransformerEmbeddingProvider(expected_dimension=4, allow_model_download=True)
    provider.encode_documents(["doc"])

    assert captured["kwargs"]["local_files_only"] is False


def test_sentence_transformer_provider_rejects_non_finite_vectors(monkeypatch) -> None:
    class FakeModel:
        def encode(self, texts, **kwargs):
            return [[float("nan"), 0.0, 0.0, 0.0]]

    monkeypatch.setattr(
        "knowledge_base.retrieval.embeddings._import_optional_dependency",
        lambda _: SimpleNamespace(SentenceTransformer=lambda *args, **kwargs: FakeModel()),
    )

    provider = SentenceTransformerEmbeddingProvider(expected_dimension=4)
    with pytest.raises(Exception, match="NaN|infinity|non-finite"):
        provider.encode_documents(["doc"])
