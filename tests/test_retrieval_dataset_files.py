from __future__ import annotations

import json
import subprocess
from pathlib import Path

from evaluation.retrieval.dataset import load_retrieval_evaluation_cases
from knowledge_base.dataset import (
    load_demo_solution_scope,
    load_knowledge_chunks,
    load_knowledge_documents,
    load_knowledge_manifest,
)


def test_build_script_check_mode_succeeds() -> None:
    completed = subprocess.run(
        [".venv/bin/python", "scripts/build_synthetic_knowledge_base.py", "--check"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert '"mode": "check"' in completed.stdout


def test_chunk_and_manifest_files_exist_and_match_expected_counts() -> None:
    chunks = load_knowledge_chunks("data/knowledge_base/chunks.v1.jsonl")
    manifest = load_knowledge_manifest("data/knowledge_base/manifest.v1.json")

    assert len(chunks) == 40
    assert manifest.document_count == 20
    assert manifest.chunk_count == 40


def test_documents_and_retrieval_cases_are_json_serializable_line_by_line() -> None:
    for path in (
        Path("data/knowledge_base/documents.v1.jsonl"),
        Path("data/knowledge_base/chunks.v1.jsonl"),
        Path("data/evaluation/retrieval/retrieval_cases.v1.jsonl"),
    ):
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert lines
        for line in lines:
            payload = json.loads(line)
            assert isinstance(payload, dict)


def test_demo_scope_and_data_files_do_not_contain_local_runtime_paths() -> None:
    files = [
        Path("data/knowledge_base/demo_solution_scope.v1.json"),
        Path("data/knowledge_base/documents.v1.jsonl"),
        Path("data/knowledge_base/chunks.v1.jsonl"),
        Path("data/knowledge_base/manifest.v1.json"),
        Path("data/evaluation/retrieval/retrieval_cases.v1.jsonl"),
    ]

    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "/Users/" not in text
        assert "data/runtime/" not in text
        assert ".env" not in text
        assert "api_key" not in text.casefold()


def test_selected_scope_is_fully_covered_in_documents_and_retrieval_cases() -> None:
    scope = load_demo_solution_scope("data/knowledge_base/demo_solution_scope.v1.json")
    documents = load_knowledge_documents("data/knowledge_base/documents.v1.jsonl")
    cases = load_retrieval_evaluation_cases("data/evaluation/retrieval/retrieval_cases.v1.jsonl")

    covered_in_documents = {
        solution_id
        for document in documents
        for solution_id in document.solution_ids
    }
    covered_in_cases = {
        solution_id
        for case in cases
        for solution_id in (case.required_solution_ids + case.forbidden_solution_ids)
    }
    for case in cases:
        for document_id in case.expected_relevant_document_ids:
            document = next(document for document in documents if document.document_id == document_id)
            covered_in_cases.update(document.solution_ids)

    assert covered_in_documents == set(scope.selected_solution_ids)
    assert covered_in_cases == set(scope.selected_solution_ids)
