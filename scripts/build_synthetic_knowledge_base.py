from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dataio.runtime_cases import load_runtime_cases
from evaluation.retrieval.dataset import load_retrieval_evaluation_cases, validate_retrieval_evaluation_dataset
from knowledge_base.chunking import build_knowledge_chunks
from knowledge_base.dataset import (
    DEFAULT_CHUNKS_PATH,
    DEFAULT_DOCUMENTS_PATH,
    DEFAULT_MANIFEST_PATH,
    DEFAULT_SCOPE_PATH,
    load_demo_solution_scope,
    load_knowledge_chunks,
    load_knowledge_documents,
    load_knowledge_manifest,
    validate_knowledge_base_dataset,
    write_json,
    write_jsonl,
)
from knowledge_base.models import KnowledgeValidationStatus, build_manifest


DEFAULT_RETRIEVAL_CASES_PATH = Path("data/evaluation/retrieval/retrieval_cases.v1.jsonl")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or verify the synthetic enterprise knowledge base artifacts.")
    parser.add_argument("--check", action="store_true", help="Verify that the tracked chunk and manifest files match deterministic regeneration.")
    args = parser.parse_args()

    allowed_solution_ids = {
        solution_id
        for case in load_runtime_cases("data/evaluation/development_cases.jsonl")
        for solution_id in case.available_solution_library
    }

    demo_scope = load_demo_solution_scope(DEFAULT_SCOPE_PATH)
    documents = load_knowledge_documents(DEFAULT_DOCUMENTS_PATH)
    generated_chunks = build_knowledge_chunks(documents)
    generated_manifest = build_manifest(
        knowledge_base_version="kb-demo-v1",
        documents=documents,
        chunks=generated_chunks,
        generated_at=max(document.updated_at for document in documents),
        validation_status=KnowledgeValidationStatus.valid,
    )

    validate_knowledge_base_dataset(
        documents=documents,
        chunks=generated_chunks,
        manifest=generated_manifest,
        demo_scope=demo_scope,
        allowed_solution_ids=allowed_solution_ids,
    )

    generated_chunk_payloads = [chunk.model_dump(mode="json") for chunk in generated_chunks]
    generated_manifest_payload = generated_manifest.model_dump(mode="json")

    if args.check:
        existing_chunks = load_knowledge_chunks(DEFAULT_CHUNKS_PATH)
        existing_manifest = load_knowledge_manifest(DEFAULT_MANIFEST_PATH)
        if [chunk.model_dump(mode="json") for chunk in existing_chunks] != generated_chunk_payloads:
            print("Knowledge base chunk file is out of date.", file=sys.stderr)
            return 1
        if existing_manifest.model_dump(mode="json") != generated_manifest_payload:
            print("Knowledge base manifest file is out of date.", file=sys.stderr)
            return 1
    else:
        write_jsonl(DEFAULT_CHUNKS_PATH, generated_chunk_payloads)
        write_json(DEFAULT_MANIFEST_PATH, generated_manifest_payload)

    retrieval_cases = load_retrieval_evaluation_cases(DEFAULT_RETRIEVAL_CASES_PATH)
    validate_retrieval_evaluation_dataset(
        cases=retrieval_cases,
        documents=documents,
        chunks=generated_chunks,
        development_case_ids={case.case_id for case in load_runtime_cases("data/evaluation/development_cases.jsonl")},
        solution_ids=allowed_solution_ids,
        demo_scope=demo_scope,
    )

    print(
        json.dumps(
            {
                "documents": len(documents),
                "chunks": len(generated_chunks),
                "manifest_solution_ids": generated_manifest.solution_ids,
                "retrieval_cases": len(retrieval_cases),
                "mode": "check" if args.check else "write",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
