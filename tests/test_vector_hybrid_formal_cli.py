from __future__ import annotations

import json
from pathlib import Path

import scripts.run_vector_hybrid_retrieval as cli


def test_check_cannot_be_combined(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--check", "--validate"])

    exit_code = cli.main()

    assert exit_code == 2
    assert "Choose only one of" in capsys.readouterr().err


def test_run_without_write_does_not_create_files(tmp_path: Path, monkeypatch, capsys) -> None:
    class StubProvider:
        def __init__(self, **kwargs):
            self.model_name = "intfloat/multilingual-e5-small"
            self.resolved_revision = "unresolved"
            self.dimension = 8
            self.provider_id = "sentence_transformers:intfloat/multilingual-e5-small"

        def encode_documents(self, texts):
            return [[1.0] + [0.0] * 7 for _ in texts]

        def encode_queries(self, texts):
            return [[1.0] + [0.0] * 7 for _ in texts]

    monkeypatch.setattr(cli, "SentenceTransformerEmbeddingProvider", lambda **kwargs: StubProvider())
    monkeypatch.setattr(cli, "is_local_sentence_transformer_model_available", lambda *args, **kwargs: True)
    monkeypatch.setattr(cli, "get_embedding_dependency_versions", lambda: {"torch": "2.2.2"})
    monkeypatch.setattr(
        cli, "_resolve_frozen_local_snapshot", lambda **kwargs: tmp_path / "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    )
    monkeypatch.setattr(
        cli,
        "_load_model_manifest",
        lambda: {
            "repo_id": "intfloat/multilingual-e5-small",
            "resolved_revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
            "embedding_dimension": 384,
            "local_snapshot_available": True,
        },
    )
    monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cli, "VECTOR_RESULTS_PATH", tmp_path / "vector.jsonl")
    monkeypatch.setattr(cli, "VECTOR_SUMMARY_PATH", tmp_path / "vector.json")
    monkeypatch.setattr(cli, "HYBRID_RESULTS_PATH", tmp_path / "hybrid.jsonl")
    monkeypatch.setattr(cli, "HYBRID_SUMMARY_PATH", tmp_path / "hybrid.json")
    monkeypatch.setattr(cli, "COMPARISON_PATH", tmp_path / "comparison.json")
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--run"])
    original_load_context = cli._load_context  # noqa: SLF001

    def isolated_context():
        context = original_load_context()
        context["vector_config"] = context["vector_config"].model_copy(
            update={"cache_enabled": False, "cache_directory": "data/runtime/test-formal-cache"}
        )
        return context

    monkeypatch.setattr(cli, "_load_context", isolated_context)

    exit_code = cli.main()

    assert exit_code == 0
    assert not (tmp_path / "vector.jsonl").exists()


def test_formal_outputs_do_not_include_embeddings(tmp_path: Path, monkeypatch) -> None:
    class StubProvider:
        def __init__(self, **kwargs):
            self.model_name = "intfloat/multilingual-e5-small"
            self.resolved_revision = "unresolved"
            self.dimension = 8

        def encode_documents(self, texts):
            return [[1.0] + [0.0] * 7 for _ in texts]

        def encode_queries(self, texts):
            return [[1.0] + [0.0] * 7 for _ in texts]

    monkeypatch.setattr(cli, "SentenceTransformerEmbeddingProvider", lambda **kwargs: StubProvider())
    monkeypatch.setattr(cli, "get_embedding_dependency_versions", lambda: {"torch": "2.2.2"})
    monkeypatch.setattr(
        cli, "_resolve_frozen_local_snapshot", lambda **kwargs: tmp_path / "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    )
    monkeypatch.setattr(
        cli,
        "_load_model_manifest",
        lambda: {
            "repo_id": "intfloat/multilingual-e5-small",
            "resolved_revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
            "embedding_dimension": 384,
            "local_snapshot_available": True,
        },
    )
    monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    context = cli._load_context()  # noqa: SLF001
    context["vector_config"] = context["vector_config"].model_copy(
        update={"cache_enabled": False, "cache_directory": "data/runtime/test-formal-cache"}
    )

    payload = cli._run_formal(context=context, write=False)  # noqa: SLF001

    serialized = json.dumps(payload, ensure_ascii=False)
    assert '"vector":' not in serialized.casefold()
    assert '"embedding":' not in serialized.casefold()


def test_prepare_model_does_not_write_formal_outputs(tmp_path: Path, monkeypatch, capsys) -> None:
    class StubProvider:
        def __init__(self, **kwargs):
            pass

        def prepare_model(self):
            return {
                "configured_model_name": "intfloat/multilingual-e5-small",
                "resolved_model_revision": "unresolved",
                "embedding_dimension": 384,
                "device": "cpu",
                "query_prefix": "query: ",
                "document_prefix": "passage: ",
                "normalization": True,
            }

    monkeypatch.setattr(cli, "SentenceTransformerEmbeddingProvider", StubProvider)
    monkeypatch.setattr(cli, "is_local_sentence_transformer_model_available", lambda *args, **kwargs: True)
    monkeypatch.setenv("RETRIEVAL_MODEL_MANIFEST_PATH", str(tmp_path / "model_manifest.v1.json"))
    monkeypatch.setattr(cli, "VECTOR_RESULTS_PATH", tmp_path / "vector.jsonl")
    monkeypatch.setattr(cli, "VECTOR_SUMMARY_PATH", tmp_path / "vector.json")
    monkeypatch.setattr(cli, "HYBRID_RESULTS_PATH", tmp_path / "hybrid.jsonl")
    monkeypatch.setattr(cli, "HYBRID_SUMMARY_PATH", tmp_path / "hybrid.json")
    monkeypatch.setattr(cli, "COMPARISON_PATH", tmp_path / "comparison.json")
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--prepare-model"])

    exit_code = cli.main()

    assert exit_code == 0
    assert not (tmp_path / "vector.jsonl").exists()


def test_formal_run_passes_local_snapshot_path_to_provider(tmp_path: Path, monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    class StubProvider:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.model_name = "intfloat/multilingual-e5-small"
            self.resolved_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
            self.dimension = 384
            self.provider_id = "sentence_transformers:intfloat/multilingual-e5-small"

        def encode_documents(self, texts):
            return [[1.0] + [0.0] * 383 for _ in texts]

        def encode_queries(self, texts):
            return [[1.0] + [0.0] * 383 for _ in texts]

    snapshot_path = tmp_path / "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    monkeypatch.setattr(cli, "SentenceTransformerEmbeddingProvider", StubProvider)
    monkeypatch.setattr(cli, "is_local_sentence_transformer_model_available", lambda *args, **kwargs: True)
    monkeypatch.setattr(cli, "_resolve_frozen_local_snapshot", lambda **kwargs: snapshot_path)
    monkeypatch.setattr(
        cli,
        "_load_model_manifest",
        lambda: {
            "repo_id": "intfloat/multilingual-e5-small",
            "resolved_revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
            "embedding_dimension": 384,
            "local_snapshot_available": True,
        },
    )
    monkeypatch.setattr(cli, "get_embedding_dependency_versions", lambda: {"torch": "2.2.2"})
    monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--run"])
    original_load_context = cli._load_context  # noqa: SLF001

    def isolated_context():
        context = original_load_context()
        context["vector_config"] = context["vector_config"].model_copy(
            update={"cache_enabled": False, "cache_directory": "data/runtime/test-formal-cache"}
        )
        return context

    monkeypatch.setattr(cli, "_load_context", isolated_context)

    exit_code = cli.main()

    assert exit_code == 0
    assert captured["local_snapshot_path"] == snapshot_path
    assert captured["model_name_or_path"] == "intfloat/multilingual-e5-small"
