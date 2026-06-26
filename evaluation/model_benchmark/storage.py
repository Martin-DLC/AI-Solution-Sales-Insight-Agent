from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evaluation.model_benchmark.models import (
    BenchmarkCaseRunArtifact,
    BenchmarkRunManifest,
    BenchmarkRunReport,
)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_benchmark_case_artifact(
    artifact: BenchmarkCaseRunArtifact,
    *,
    artifact_dir: Path,
    call_records: list[Any],
) -> Path:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    write_json(artifact_dir / "artifact.json", artifact.model_dump(mode="json"))
    write_json(artifact_dir / "observation.json", artifact.observation.model_dump(mode="json"))
    write_json(
        artifact_dir / "assertion_results.json",
        [result.model_dump(mode="json") for result in artifact.assertion_results],
    )
    write_json(artifact_dir / "run_result.json", artifact.run_result.model_dump(mode="json"))

    llm_calls_dir = artifact_dir / "llm_calls"
    for index, call_record in enumerate(call_records, start=1):
        call_name = getattr(getattr(call_record, "node_name", None), "value", "node")
        call_dir = llm_calls_dir / f"{index:02d}_{call_name}"
        call_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            call_dir / "metadata.json",
            call_record.model_dump(mode="json", exclude={"messages", "raw_content", "parsed_json"}),
        )
        write_json(call_dir / "messages.json", getattr(call_record, "messages", []))
        raw_content = getattr(call_record, "raw_content", None)
        if raw_content is not None:
            (call_dir / "raw_response.txt").write_text(raw_content, encoding="utf-8")
        parsed_json = getattr(call_record, "parsed_json", None)
        if parsed_json is not None:
            write_json(call_dir / "parsed_response.json", parsed_json)
    return artifact_dir


def write_benchmark_run_report(
    *,
    output_root: str | Path,
    manifest: BenchmarkRunManifest,
    report: BenchmarkRunReport,
    case_artifacts: list[tuple[BenchmarkCaseRunArtifact, list[Any]]],
) -> Path:
    root = Path(output_root) / manifest.run_id
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "run_manifest.json", manifest.model_dump(mode="json"))
    write_json(root / "benchmark_report.json", report.model_dump(mode="json"))
    for artifact, call_records in case_artifacts:
        artifact_dir = (
            root
            / "cases"
            / artifact.benchmark_case_id
            / artifact.model_config_id
            / artifact.node_name.value
        )
        write_benchmark_case_artifact(
            artifact,
            artifact_dir=artifact_dir,
            call_records=call_records,
        )
    return root
