from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_jsonl_atomic(path: str | Path, records: list[dict[str, Any]]) -> None:
    content = "\n".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for record in records
    ) + "\n"
    _atomic_write_text(Path(path), content)


def write_json_atomic(path: str | Path, payload: dict[str, Any]) -> None:
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    _atomic_write_text(Path(path), content)


def write_many_atomic(items: list[tuple[str | Path, str]]) -> None:
    written_temp_paths: list[tuple[Path, Path]] = []
    for raw_path, content in items:
        path = Path(raw_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(content, encoding="utf-8")
        written_temp_paths.append((path, temp_path))
    for path, temp_path in written_temp_paths:
        temp_path.replace(path)


def load_jsonl_records(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError("Tracked lexical baseline JSONL must contain one JSON object per line.")
        records.append(payload)
    return records


def load_json_record(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Tracked lexical baseline JSON must be a JSON object.")
    return payload


def diff_json_objects(
    expected: Any,
    actual: Any,
    *,
    path: str = "",
) -> list[str]:
    if type(expected) is not type(actual):
        return [path or "$"]

    if isinstance(expected, dict):
        differences: list[str] = []
        all_keys = sorted(set(expected) | set(actual))
        for key in all_keys:
            child_path = f"{path}.{key}" if path else key
            if key not in expected or key not in actual:
                differences.append(child_path)
                continue
            differences.extend(diff_json_objects(expected[key], actual[key], path=child_path))
        return differences

    if isinstance(expected, list):
        differences: list[str] = []
        if len(expected) != len(actual):
            differences.append(path or "$")
            return differences
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            child_path = f"{path}[{index}]" if path else f"[{index}]"
            differences.extend(diff_json_objects(expected_item, actual_item, path=child_path))
        return differences

    if expected != actual:
        return [path or "$"]
    return []


def diff_json_objects_ignoring_paths(
    expected: Any,
    actual: Any,
    *,
    ignored_suffixes: set[str],
    path: str = "",
) -> list[str]:
    differences = diff_json_objects(expected, actual, path=path)
    return [difference for difference in differences if not any(difference.endswith(suffix) for suffix in ignored_suffixes)]


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)
