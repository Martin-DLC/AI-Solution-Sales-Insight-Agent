from __future__ import annotations

import hashlib
import importlib
import importlib.util
import math
from pathlib import Path
from typing import Any, Protocol


DEFAULT_EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
DEFAULT_QUERY_PREFIX = "query: "
DEFAULT_DOCUMENT_PREFIX = "passage: "
DEFAULT_E5_SMALL_DIMENSION = 384


class EmbeddingProviderError(RuntimeError):
    """Base error for embedding provider failures."""


class EmbeddingDependencyError(EmbeddingProviderError):
    """Raised when an embedding provider dependency is unavailable."""


class EmbeddingModelUnavailableError(EmbeddingProviderError):
    """Raised when the local embedding model is unavailable."""


class EmbeddingProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def encode_queries(
        self,
        texts: list[str],
    ) -> list[list[float]]: ...

    def encode_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]: ...


class FakeEmbeddingProvider:
    def __init__(
        self,
        *,
        dimension: int = 8,
        provider_id: str = "fake_embedding_v1",
    ) -> None:
        if dimension <= 0:
            raise ValueError("Fake embedding provider dimension must be greater than 0.")
        self._dimension = dimension
        self._provider_id = provider_id
        self.query_calls = 0
        self.document_calls = 0

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode_queries(self, texts: list[str]) -> list[list[float]]:
        self.query_calls += 1
        return [self._encode_text(text=text, mode="query") for text in texts]

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_calls += 1
        return [self._encode_text(text=text, mode="document") for text in texts]

    def _encode_text(self, *, text: str, mode: str) -> list[float]:
        digest = hashlib.sha256(f"{mode}\x1f{text}".encode("utf-8")).digest()
        values: list[float] = []
        while len(values) < self._dimension:
            for byte in digest:
                values.append((byte / 255.0) * 2.0 - 1.0)
                if len(values) >= self._dimension:
                    break
            digest = hashlib.sha256(digest).digest()
        return _normalize_vector(values[: self._dimension])


class SentenceTransformerEmbeddingProvider:
    def __init__(
        self,
        *,
        model_name_or_path: str = DEFAULT_EMBEDDING_MODEL,
        batch_size: int = 16,
        device: str = "cpu",
        normalize_embeddings: bool = True,
        allow_model_download: bool = False,
        query_prefix: str = DEFAULT_QUERY_PREFIX,
        document_prefix: str = DEFAULT_DOCUMENT_PREFIX,
        expected_dimension: int = DEFAULT_E5_SMALL_DIMENSION,
    ) -> None:
        if not model_name_or_path.strip():
            raise ValueError("Embedding model_name_or_path cannot be empty.")
        if batch_size <= 0:
            raise ValueError("Embedding batch_size must be greater than 0.")
        if expected_dimension <= 0:
            raise ValueError("Embedding expected_dimension must be greater than 0.")
        self._model_name_or_path = model_name_or_path
        self._batch_size = batch_size
        self._device = device
        self._normalize_embeddings = normalize_embeddings
        self._allow_model_download = allow_model_download
        self._query_prefix = query_prefix
        self._document_prefix = document_prefix
        self._expected_dimension = expected_dimension
        self._model: Any | None = None
        self._loaded_dimension: int | None = None

    @property
    def provider_id(self) -> str:
        return f"sentence_transformers:{self._model_name_or_path}"

    @property
    def dimension(self) -> int:
        return self._loaded_dimension or self._expected_dimension

    @property
    def model_name(self) -> str:
        return self._model_name_or_path

    @property
    def allow_model_download(self) -> bool:
        return self._allow_model_download

    def encode_queries(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load_model()
        encoded = self._encode_with_model(
            model=model,
            texts=texts,
            mode="query",
        )
        return _validate_vectors(encoded, expected_dimension=self.dimension)

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load_model()
        encoded = self._encode_with_model(
            model=model,
            texts=texts,
            mode="document",
        )
        return _validate_vectors(encoded, expected_dimension=self.dimension)

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model

        sentence_transformers_module = _import_optional_dependency("sentence_transformers")
        if sentence_transformers_module is None:
            raise EmbeddingDependencyError(
                "sentence-transformers is not installed. Install the project requirements before running vector retrieval."
            )

        sentence_transformer_cls = getattr(sentence_transformers_module, "SentenceTransformer", None)
        if sentence_transformer_cls is None:
            raise EmbeddingDependencyError("sentence-transformers is installed but SentenceTransformer is unavailable.")

        try:
            model = sentence_transformer_cls(
                self._model_name_or_path,
                device=self._device,
                local_files_only=not self._allow_model_download,
            )
        except Exception as exc:
            if not self._allow_model_download:
                raise EmbeddingModelUnavailableError(
                    "Local embedding model is unavailable. Re-run with explicit model download permission if needed."
                ) from exc
            raise EmbeddingProviderError("Failed to load the sentence-transformers model.") from exc

        self._model = model
        model_dimension = getattr(model, "get_sentence_embedding_dimension", None)
        if callable(model_dimension):
            loaded_dimension = model_dimension()
            if isinstance(loaded_dimension, int) and loaded_dimension > 0:
                self._loaded_dimension = loaded_dimension
        return model

    def _encode_with_model(
        self,
        *,
        model: Any,
        texts: list[str],
        mode: str,
    ) -> list[list[float]]:
        if mode == "query" and hasattr(model, "encode_query"):
            raw_vectors = model.encode_query(
                texts,
                batch_size=self._batch_size,
                normalize_embeddings=self._normalize_embeddings,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        elif mode == "document" and hasattr(model, "encode_document"):
            raw_vectors = model.encode_document(
                texts,
                batch_size=self._batch_size,
                normalize_embeddings=self._normalize_embeddings,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        else:
            prefix = self._query_prefix if mode == "query" else self._document_prefix
            raw_vectors = model.encode(
                [prefix + text for text in texts],
                batch_size=self._batch_size,
                normalize_embeddings=self._normalize_embeddings,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        return _coerce_vectors(raw_vectors)


def get_embedding_dependency_report() -> dict[str, bool]:
    return {
        "sentence_transformers": importlib.util.find_spec("sentence_transformers") is not None,
        "torch": importlib.util.find_spec("torch") is not None,
        "transformers": importlib.util.find_spec("transformers") is not None,
        "numpy": importlib.util.find_spec("numpy") is not None,
    }


def is_local_sentence_transformer_model_available(model_name_or_path: str) -> bool:
    normalized = model_name_or_path.replace("/", "--")
    candidates = [
        Path.home() / ".cache/huggingface/hub" / f"models--{normalized}",
        Path.home() / "Library" / "Caches" / "huggingface" / "hub" / f"models--{normalized}",
    ]
    for candidate in candidates:
        if candidate.exists():
            return True
    return False


def _import_optional_dependency(module_name: str) -> Any | None:
    if importlib.util.find_spec(module_name) is None:
        return None
    return importlib.import_module(module_name)


def _coerce_vectors(raw_vectors: Any) -> list[list[float]]:
    if hasattr(raw_vectors, "tolist"):
        converted = raw_vectors.tolist()
    else:
        converted = raw_vectors
    if not isinstance(converted, list):
        raise EmbeddingProviderError("Embedding provider returned an unexpected vector container.")
    vectors: list[list[float]] = []
    for vector in converted:
        if not isinstance(vector, list):
            raise EmbeddingProviderError("Embedding provider returned a non-list vector.")
        vectors.append([float(value) for value in vector])
    return vectors


def _validate_vectors(
    vectors: list[list[float]],
    *,
    expected_dimension: int,
) -> list[list[float]]:
    for vector in vectors:
        if len(vector) != expected_dimension:
            raise EmbeddingProviderError("Embedding vector dimension does not match the provider configuration.")
        for value in vector:
            if not math.isfinite(value):
                raise EmbeddingProviderError("Embedding vectors must not contain NaN or infinity.")
    return vectors


def _normalize_vector(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        raise EmbeddingProviderError("Embedding vector norm must be greater than 0.")
    return [value / norm for value in values]
