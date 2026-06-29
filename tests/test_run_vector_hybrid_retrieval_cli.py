from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

import scripts.run_vector_hybrid_retrieval as cli


def test_cli_plan_mode_does_not_load_model(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "get_embedding_dependency_report", lambda: {"sentence_transformers": False})
    monkeypatch.setattr(cli, "is_local_sentence_transformer_model_available", lambda *args, **kwargs: False)
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py"])

    exit_code = cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "plan"


def test_cli_validate_mode_reports_dependency_status(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "get_embedding_dependency_report", lambda: {"sentence_transformers": False})
    monkeypatch.setattr(cli, "is_local_sentence_transformer_model_available", lambda *args, **kwargs: False)
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--validate"])

    exit_code = cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "validate"
    assert payload["local_model_available"] is False


def test_cli_fake_smoke_succeeds(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "get_embedding_dependency_report", lambda: {"sentence_transformers": False})
    monkeypatch.setattr(cli, "is_local_sentence_transformer_model_available", lambda *args, **kwargs: False)
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--fake-smoke"])

    exit_code = cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "fake_smoke"


def test_cli_prepare_model_without_download_permission_fails_when_model_missing(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "is_local_sentence_transformer_model_available", lambda *args, **kwargs: False)
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--prepare-model"])

    exit_code = cli.main()

    assert exit_code == 1
    assert "Local embedding model is unavailable" in capsys.readouterr().err


def test_cli_prepare_model_uses_provider_prepare_only(monkeypatch, capsys) -> None:
    called = {"prepare": 0}

    class StubProvider:
        def __init__(self, **kwargs):
            pass

        def prepare_model(self):
            called["prepare"] += 1
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
    monkeypatch.setattr(cli, "get_embedding_dependency_versions", lambda: {"torch": "2.2.2"})
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--prepare-model"])

    exit_code = cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert called["prepare"] == 1
    assert payload["configured_model_name"] == "intfloat/multilingual-e5-small"


def test_cli_write_requires_run(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--write"])

    exit_code = cli.main()

    assert exit_code == 2
    assert "--write must be used together with --run." in capsys.readouterr().err


def test_cli_allow_download_requires_run(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--allow-model-download"])

    exit_code = cli.main()

    assert exit_code == 2
    assert "--allow-model-download can only be used together with --prepare-model." in capsys.readouterr().err


def test_cli_run_refuses_missing_local_model(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "is_local_sentence_transformer_model_available", lambda *args, **kwargs: False)
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--run"])

    exit_code = cli.main()

    assert exit_code == 1
    assert "Local embedding model is unavailable" in capsys.readouterr().err


def test_cli_run_write_uses_real_provider_interface_and_writes_files(tmp_path: Path, monkeypatch, capsys) -> None:
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

    def fake_provider(*args, **kwargs):
        return StubProvider()

    def fake_provider_guard(*args, **kwargs):
        raise AssertionError("Fake provider must not be used in formal run")

    monkeypatch.setattr(cli, "SentenceTransformerEmbeddingProvider", fake_provider)
    monkeypatch.setattr(cli, "FakeEmbeddingProvider", fake_provider_guard)
    monkeypatch.setattr(cli, "is_local_sentence_transformer_model_available", lambda *args, **kwargs: True)
    monkeypatch.setattr(cli, "get_embedding_dependency_versions", lambda: {"torch": "2.2.2", "numpy": "1.26.4"})
    monkeypatch.setattr(cli, "_resolve_frozen_local_snapshot", lambda **kwargs: tmp_path / "snapshot")
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
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--run", "--write"])

    original_load_context = cli._load_context  # noqa: SLF001

    def isolated_context():
        context = original_load_context()
        context["vector_config"] = context["vector_config"].model_copy(
            update={"cache_enabled": False, "cache_directory": "data/runtime/test-cli-cache"}
        )
        return context

    monkeypatch.setattr(cli, "_load_context", isolated_context)
    exit_code = cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "run"
    assert (tmp_path / "vector.jsonl").exists()
    assert (tmp_path / "comparison.json").exists()


def test_cli_check_ignores_latency_but_not_score(tmp_path: Path, monkeypatch, capsys) -> None:
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
    monkeypatch.setattr(cli, "get_embedding_dependency_versions", lambda: {"torch": "2.2.2", "numpy": "1.26.4"})
    monkeypatch.setattr(cli, "_resolve_frozen_local_snapshot", lambda **kwargs: tmp_path / "snapshot")
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
    context = cli._load_context()  # noqa: SLF001
    context["vector_config"] = context["vector_config"].model_copy(
        update={"cache_enabled": False, "cache_directory": "data/runtime/test-cli-cache"}
    )
    payload = cli._run_formal(context=context, write=True)  # noqa: SLF001
    first_vector = payload["vector_results"][0]
    first_vector["latency_ms"] += 99
    (tmp_path / "vector.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for item in payload["vector_results"]) + "\n",
        encoding="utf-8",
    )
    for file_name, key in [("vector.json", "vector_summary"), ("hybrid.jsonl", "hybrid_results"), ("hybrid.json", "hybrid_summary"), ("comparison.json", "comparison")]:
        path = tmp_path / file_name
        value = payload[key]
        if isinstance(value, list):
            path.write_text("\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for item in value) + "\n", encoding="utf-8")
        else:
            path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--check"])
    exit_code = cli.main()

    assert exit_code == 0


def test_cli_check_ignores_cache_hit_and_miss_counts(tmp_path: Path, monkeypatch, capsys) -> None:
    class StubProvider:
        def __init__(self, **kwargs):
            self.model_name = "intfloat/multilingual-e5-small"
            self.resolved_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
            self.dimension = 384
            self.provider_id = "sentence_transformers:intfloat/multilingual-e5-small"

        def encode_documents(self, texts):
            return [[1.0] + [0.0] * 383 for _ in texts]

        def encode_queries(self, texts):
            return [[1.0] + [0.0] * 383 for _ in texts]

    monkeypatch.setattr(cli, "SentenceTransformerEmbeddingProvider", lambda **kwargs: StubProvider())
    monkeypatch.setattr(cli, "is_local_sentence_transformer_model_available", lambda *args, **kwargs: True)
    monkeypatch.setattr(cli, "get_embedding_dependency_versions", lambda: {"torch": "2.2.2", "numpy": "1.26.4"})
    monkeypatch.setattr(cli, "_resolve_frozen_local_snapshot", lambda **kwargs: tmp_path / "snapshot")
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
    context = cli._load_context()  # noqa: SLF001
    context["vector_config"] = context["vector_config"].model_copy(
        update={"cache_enabled": False, "cache_directory": "data/runtime/test-cli-cache"}
    )
    payload = cli._run_formal(context=context, write=True)  # noqa: SLF001
    payload["vector_summary"]["cache_hit_count"] = 40
    payload["vector_summary"]["cache_miss_count"] = 0
    payload["hybrid_summary"]["cache_hit_count"] = 40
    payload["hybrid_summary"]["cache_miss_count"] = 0
    for file_name, key in [
        ("vector.jsonl", "vector_results"),
        ("vector.json", "vector_summary"),
        ("hybrid.jsonl", "hybrid_results"),
        ("hybrid.json", "hybrid_summary"),
        ("comparison.json", "comparison"),
    ]:
        path = tmp_path / file_name
        value = payload[key]
        if isinstance(value, list):
            path.write_text(
                "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for item in value) + "\n",
                encoding="utf-8",
            )
        else:
            path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--check"])
    exit_code = cli.main()

    assert exit_code == 0


def test_cli_check_keeps_resolved_revision_strict(tmp_path: Path, monkeypatch, capsys) -> None:
    class StubProvider:
        def __init__(self, **kwargs):
            self.model_name = "intfloat/multilingual-e5-small"
            self.resolved_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
            self.dimension = 384
            self.provider_id = "sentence_transformers:intfloat/multilingual-e5-small"

        def encode_documents(self, texts):
            return [[1.0] + [0.0] * 383 for _ in texts]

        def encode_queries(self, texts):
            return [[1.0] + [0.0] * 383 for _ in texts]

    monkeypatch.setattr(cli, "SentenceTransformerEmbeddingProvider", lambda **kwargs: StubProvider())
    monkeypatch.setattr(cli, "is_local_sentence_transformer_model_available", lambda *args, **kwargs: True)
    monkeypatch.setattr(cli, "get_embedding_dependency_versions", lambda: {"torch": "2.2.2", "numpy": "1.26.4"})
    monkeypatch.setattr(cli, "_resolve_frozen_local_snapshot", lambda **kwargs: tmp_path / "snapshot")
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
    context = cli._load_context()  # noqa: SLF001
    context["vector_config"] = context["vector_config"].model_copy(
        update={"cache_enabled": False, "cache_directory": "data/runtime/test-cli-cache"}
    )
    payload = cli._run_formal(context=context, write=True)  # noqa: SLF001
    payload["vector_summary"]["resolved_model_revision"] = "wrong-revision"
    (tmp_path / "vector.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for item in payload["vector_results"]) + "\n",
        encoding="utf-8",
    )
    for file_name, key in [("vector.json", "vector_summary"), ("hybrid.jsonl", "hybrid_results"), ("hybrid.json", "hybrid_summary"), ("comparison.json", "comparison")]:
        path = tmp_path / file_name
        value = payload[key]
        if isinstance(value, list):
            path.write_text(
                "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for item in value) + "\n",
                encoding="utf-8",
            )
        else:
            path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--check"])
    exit_code = cli.main()

    assert exit_code == 1
    assert "vector_summary:resolved_model_revision" in capsys.readouterr().err


def test_cli_offline_model_smoke_uses_local_snapshot_only(monkeypatch, capsys) -> None:
    called = {"count": 0}

    def fake_offline_smoke(*, vector_config):
        called["count"] += 1
        return {
            "mode": "offline_model_smoke",
            "configured_model_name": "intfloat/multilingual-e5-small",
            "resolved_model_revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
            "embedding_dimension": 384,
            "synthetic_probe_passed": True,
        }

    monkeypatch.setattr(cli, "is_local_sentence_transformer_model_available", lambda *args, **kwargs: True)
    monkeypatch.setattr(cli, "_run_offline_model_smoke", fake_offline_smoke)
    monkeypatch.setattr(cli.sys, "argv", ["run_vector_hybrid_retrieval.py", "--offline-model-smoke"])

    exit_code = cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert called["count"] == 1
    assert payload["mode"] == "offline_model_smoke"


def test_network_guard_blocks_socket_connections() -> None:
    with cli._network_guard():  # noqa: SLF001
        with pytest.raises(RuntimeError, match="blocked"):
            socket.create_connection(("127.0.0.1", 80), timeout=0.01)
