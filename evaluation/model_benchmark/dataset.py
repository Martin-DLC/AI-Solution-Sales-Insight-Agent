from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from agent.workflow_c.nodes.fact_extraction import FactExtractionNode
from agent.workflow_c.nodes.information_gap import InformationGapNode
from agent.workflow_c.nodes.solution_recommendation import SolutionRecommendationNode
from agent.workflow_c.nodes.underlying_pain import UnderlyingPainNode
from evaluation.model_benchmark.models import (
    BenchmarkNodeName,
    NodeBenchmarkCase,
)
from schemas import EvaluationCaseInput, HiddenReferencePack
from schemas.common_models import StrictBaseModel


DEFAULT_DEVELOPMENT_CASES_PATH = Path("data/evaluation/development_cases.jsonl")
DEFAULT_REFERENCE_PACK_PATH = Path("data/evaluation/development_reference.jsonl")

NODE_REQUIRED_STATE_FIELDS: dict[BenchmarkNodeName, tuple[str, ...]] = {
    FactExtractionNode.contract.name: FactExtractionNode.contract.required_state_fields,
    UnderlyingPainNode.contract.name: UnderlyingPainNode.contract.required_state_fields,
    InformationGapNode.contract.name: InformationGapNode.contract.required_state_fields,
    SolutionRecommendationNode.contract.name: SolutionRecommendationNode.contract.required_state_fields,
}

_FORBIDDEN_KEY_NAMES = {
    "api_key",
    "authorization",
    "bearer_token",
    "secret",
}
_FORBIDDEN_FIELD_NAMES = {
    "expected_output",
    "reference_pack",
}


class NodeBenchmarkFixture(StrictBaseModel):
    fixture_version: Literal["1.0"]
    benchmark_case_id: str
    source_case_id: str
    node_name: BenchmarkNodeName
    state: dict[str, Any]

    @field_validator("benchmark_case_id", "source_case_id")
    @classmethod
    def text_fields_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("Benchmark fixture fields are required and cannot be empty.")
        return value

    @model_validator(mode="after")
    def validate_fixture(self) -> Self:
        if self.node_name not in NODE_REQUIRED_STATE_FIELDS:
            raise ValueError("Benchmark fixture node_name must be one of the benchmark nodes.")
        if not isinstance(self.state, dict):
            raise ValueError("Benchmark fixture state must be a JSON object.")
        return self


def _load_jsonl_models(path: str | Path, model_type: type[Any]) -> list[Any]:
    file_path = Path(path)
    records: list[Any] = []
    for line_number, raw_line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            data = json.loads(raw_line)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise ValueError(f"Invalid JSON on line {line_number} of {file_path}.") from exc
        try:
            records.append(model_type.model_validate(data))
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError(
                f"Invalid record on line {line_number} of {file_path}: {exc}"
            ) from exc
    return records


def load_development_cases(
    path: str | Path = DEFAULT_DEVELOPMENT_CASES_PATH,
) -> list[EvaluationCaseInput]:
    return _load_jsonl_models(path, EvaluationCaseInput)


def load_reference_packs(
    path: str | Path = DEFAULT_REFERENCE_PACK_PATH,
) -> list[HiddenReferencePack]:
    return _load_jsonl_models(path, HiddenReferencePack)


def load_node_benchmark_cases(
    path: str | Path,
) -> list[NodeBenchmarkCase]:
    return _load_jsonl_models(path, NodeBenchmarkCase)


def load_node_input_fixture(
    path: str | Path,
) -> dict[str, object]:
    fixture_path = Path(path)
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture = NodeBenchmarkFixture.model_validate(data)
    fixture_dict = fixture.model_dump(mode="json")
    validate_node_input_fixture(fixture_dict, fixture_path=fixture_path)
    return fixture_dict


def validate_node_input_fixture(
    fixture: dict[str, object],
    *,
    fixture_path: str | Path | None = None,
) -> None:
    path_label = str(fixture_path) if fixture_path is not None else "<fixture>"
    for forbidden_path in _find_forbidden_paths(fixture):
        raise ValueError(f"Benchmark fixture {path_label} contains forbidden field at {forbidden_path}.")


def validate_node_benchmark_dataset(
    *,
    cases: list[NodeBenchmarkCase],
    project_root: str | Path,
) -> None:
    if len(cases) != 16:
        raise ValueError(f"Node benchmark dataset must contain exactly 16 cases; got {len(cases)}.")

    project_root = Path(project_root)
    development_case_ids = {case.case_id for case in load_development_cases(project_root / DEFAULT_DEVELOPMENT_CASES_PATH)}
    benchmark_case_ids: list[str] = []
    source_case_ids: list[str] = []

    node_counts = Counter(case.node_name for case in cases)
    for node_name in NODE_REQUIRED_STATE_FIELDS:
        if node_counts[node_name] != 4:
            raise ValueError(
                f"Benchmark dataset must contain exactly 4 cases for {node_name.value}; "
                f"got {node_counts[node_name]}."
            )

    for case in cases:
        benchmark_case_ids.append(case.benchmark_case_id)
        source_case_ids.append(case.source_case_id)

        if case.source_case_id not in development_case_ids:
            raise ValueError(
                f"Benchmark case {case.benchmark_case_id} references unknown source_case_id "
                f"{case.source_case_id}."
            )

        fixture_path = _resolve_fixture_path(project_root, case.input_fixture)
        fixture = load_node_input_fixture(fixture_path)
        _validate_fixture_metadata(case, fixture, fixture_path)
        _validate_fixture_state(case, fixture, fixture_path)

    if len(benchmark_case_ids) != len(set(benchmark_case_ids)):
        raise ValueError("Benchmark case IDs must be unique.")
    if len(set(source_case_ids)) < 8:
        raise ValueError("Benchmark dataset must cover at least 8 distinct source cases.")


def summarize_dataset_coverage(
    cases: list[NodeBenchmarkCase],
) -> dict[str, object]:
    cases_per_node: dict[str, int] = {
        node_name.value: 0 for node_name in NODE_REQUIRED_STATE_FIELDS
    }
    source_case_ids: list[str] = []
    assertion_type_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}

    for case in cases:
        cases_per_node[case.node_name.value] += 1
        if case.source_case_id not in source_case_ids:
            source_case_ids.append(case.source_case_id)
        for assertion in case.assertions:
            key = assertion.assertion_type.value
            assertion_type_counts[key] = assertion_type_counts.get(key, 0) + 1
        for tag in case.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    return {
        "total_cases": len(cases),
        "cases_per_node": cases_per_node,
        "unique_source_case_count": len(source_case_ids),
        "source_case_ids": source_case_ids,
        "assertion_type_counts": assertion_type_counts,
        "tag_counts": tag_counts,
    }


def _resolve_fixture_path(project_root: Path, input_fixture: str) -> Path:
    fixture_path = Path(input_fixture)
    if fixture_path.is_absolute():
        raise ValueError(f"Benchmark fixture path must be relative: {input_fixture}")
    if any(part == ".." for part in fixture_path.parts):
        raise ValueError(f"Benchmark fixture path must not escape the project root: {input_fixture}")
    resolved = project_root / fixture_path
    if not resolved.exists():
        raise ValueError(
            f"Benchmark fixture does not exist for path {input_fixture}."
        )
    return resolved


def _validate_fixture_metadata(
    case: NodeBenchmarkCase,
    fixture: dict[str, object],
    fixture_path: Path,
) -> None:
    for field_name in ("fixture_version", "benchmark_case_id", "source_case_id", "node_name", "state"):
        if field_name not in fixture:
            raise ValueError(
                f"Benchmark fixture {fixture_path} is missing required field {field_name}."
            )
    if fixture["fixture_version"] != "1.0":
        raise ValueError(f"Benchmark fixture {fixture_path} must declare fixture_version 1.0.")
    if fixture["benchmark_case_id"] != case.benchmark_case_id:
        raise ValueError(
            f"Benchmark fixture {fixture_path} benchmark_case_id must match {case.benchmark_case_id}."
        )
    if fixture["source_case_id"] != case.source_case_id:
        raise ValueError(
            f"Benchmark fixture {fixture_path} source_case_id must match {case.source_case_id}."
        )
    if fixture["node_name"] != case.node_name.value:
        raise ValueError(
            f"Benchmark fixture {fixture_path} node_name must match {case.node_name.value}."
        )


def _validate_fixture_state(
    case: NodeBenchmarkCase,
    fixture: dict[str, object],
    fixture_path: Path,
) -> None:
    state = fixture["state"]
    if not isinstance(state, dict):
        raise ValueError(f"Benchmark fixture {fixture_path} state must be a JSON object.")

    required_fields = NODE_REQUIRED_STATE_FIELDS[case.node_name]
    missing_fields = [field_name for field_name in required_fields if field_name not in state]
    if missing_fields:
        raise ValueError(
            f"Benchmark fixture {fixture_path} is missing required state fields: {missing_fields}."
        )

    for forbidden_path in _find_forbidden_paths(state):
        raise ValueError(
            f"Benchmark fixture {fixture_path} contains forbidden field at {forbidden_path}."
        )


def _find_forbidden_paths(value: Any, *, path: str = "state") -> list[str]:
    issues: list[str] = []
    if isinstance(value, dict):
        for key, nested_value in value.items():
            normalized_key = key.casefold()
            nested_path = f"{path}.{key}"
            if normalized_key in _FORBIDDEN_KEY_NAMES or normalized_key in _FORBIDDEN_FIELD_NAMES:
                issues.append(nested_path)
            issues.extend(_find_forbidden_paths(nested_value, path=nested_path))
        return issues
    if isinstance(value, list):
        for index, nested_value in enumerate(value):
            issues.extend(_find_forbidden_paths(nested_value, path=f"{path}[{index}]"))
        return issues
    if isinstance(value, str):
        lowered = value.casefold()
        if "hidden reference pack" in lowered:
            issues.append(path)
        return issues
    return issues
