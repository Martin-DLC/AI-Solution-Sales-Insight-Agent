from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from knowledge_base.retrieval.embeddings import (
    DEFAULT_DOCUMENT_PREFIX,
    DEFAULT_EMBEDDING_REVISION,
    DEFAULT_QUERY_PREFIX,
    EmbeddingDependencyError,
    EmbeddingModelUnavailableError,
    FakeEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
    huggingface_offline_environment,
    resolve_local_model_snapshot,
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
    assert captured["kwargs"]["trust_remote_code"] is False


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


def test_sentence_transformer_provider_uses_local_snapshot_path_for_formal_loading(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}
    local_snapshot = tmp_path / "snapshot"
    local_snapshot.mkdir()

    def fake_factory(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SimpleNamespace(encode=lambda texts, **encode_kwargs: [[1.0, 0.0, 0.0, 0.0]])

    monkeypatch.setattr(
        "knowledge_base.retrieval.embeddings._import_optional_dependency",
        lambda _: SimpleNamespace(SentenceTransformer=fake_factory),
    )

    provider = SentenceTransformerEmbeddingProvider(
        model_name_or_path="intfloat/multilingual-e5-small",
        local_snapshot_path=local_snapshot,
        expected_dimension=4,
        expected_revision=DEFAULT_EMBEDDING_REVISION,
    )
    provider.encode_documents(["doc"])

    assert captured["args"][0] == str(local_snapshot)
    assert provider.model_name == "intfloat/multilingual-e5-small"
    assert provider.resolved_revision == DEFAULT_EMBEDDING_REVISION


def test_resolve_local_model_snapshot_uses_local_files_only(monkeypatch, tmp_path) -> None:
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    for file_name in ("config.json", "modules.json", "tokenizer_config.json"):
        (snapshot_dir / file_name).write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_snapshot_download(**kwargs):
        captured.update(kwargs)
        return str(snapshot_dir)

    monkeypatch.setattr(
        "knowledge_base.retrieval.embeddings._import_optional_dependency",
        lambda _: SimpleNamespace(snapshot_download=fake_snapshot_download),
    )

    resolved = resolve_local_model_snapshot(
        repo_id="intfloat/multilingual-e5-small",
        revision=DEFAULT_EMBEDDING_REVISION,
    )

    assert resolved == snapshot_dir
    assert captured["local_files_only"] is True
    assert captured["revision"] == DEFAULT_EMBEDDING_REVISION


def test_resolve_local_model_snapshot_raises_safe_error_when_missing(monkeypatch) -> None:
    def fake_snapshot_download(**kwargs):
        raise RuntimeError("/Users/baba/.cache/huggingface/hub/private/path")

    monkeypatch.setattr(
        "knowledge_base.retrieval.embeddings._import_optional_dependency",
        lambda _: SimpleNamespace(snapshot_download=fake_snapshot_download),
    )

    with pytest.raises(EmbeddingModelUnavailableError) as exc_info:
        resolve_local_model_snapshot(
            repo_id="intfloat/multilingual-e5-small",
            revision=DEFAULT_EMBEDDING_REVISION,
        )

    assert "/Users/baba/" not in str(exc_info.value)


def test_huggingface_offline_environment_sets_and_restores_env() -> None:
    previous = {
        "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE"),
        "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE"),
        "HF_HUB_DISABLE_TELEMETRY": os.environ.get("HF_HUB_DISABLE_TELEMETRY"),
    }

    with huggingface_offline_environment():
        assert os.environ["HF_HUB_OFFLINE"] == "1"
        assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
        assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "1"

    for key, value in previous.items():
        if value is None:
            assert key not in os.environ
        else:
            assert os.environ[key] == value
