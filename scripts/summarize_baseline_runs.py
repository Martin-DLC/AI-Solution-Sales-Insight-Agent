from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS_ROOT = PROJECT_ROOT / "data" / "runtime" / "baseline_runs"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize Baseline A/B run metadata.")
    parser.add_argument("--runs-root", default=str(DEFAULT_RUNS_ROOT))
    parser.add_argument("--case", dest="case_id")
    parser.add_argument("--architecture")
    parser.add_argument("--output-json")
    args = parser.parse_args(argv)

    summary = summarize_runs(
        Path(args.runs_root),
        case_id=args.case_id,
        architecture=args.architecture,
    )
    print(format_table(summary["records"]))
    if summary["warnings"]:
        print("\nWarnings:", file=sys.stderr)
        for warning in summary["warnings"]:
            print(f"- {warning}", file=sys.stderr)

    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return 0


def summarize_runs(
    runs_root: Path,
    *,
    case_id: str | None = None,
    architecture: str | None = None,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not runs_root.exists():
        return {"records": records, "warnings": [f"Runs root does not exist: {runs_root}"]}

    for run_dir in sorted(path for path in runs_root.iterdir() if path.is_dir()):
        metadata_path = run_dir / "run_metadata.json"
        if not metadata_path.exists():
            warnings.append(f"Missing metadata: {metadata_path}")
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception as exc:
            warnings.append(f"Failed to read metadata {metadata_path}: {exc}")
            continue

        record = build_record(run_dir, metadata, warnings)
        if case_id and record["case_id"] != case_id:
            continue
        if architecture and record["architecture"] != architecture:
            continue
        records.append(record)

    records.sort(key=lambda item: item.get("started_at") or "")
    return {"records": records, "warnings": warnings}


def build_record(
    run_dir: Path,
    metadata: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    validation_error = _read_optional_json(run_dir / "validation_error.json", warnings)
    json_parse_error = _read_optional_json(run_dir / "json_parse_error.json", warnings)
    architecture = metadata.get("architecture")
    status = metadata.get("status")
    usage = metadata.get("usage") or {}
    error_type = metadata.get("error_type")

    json_success: bool | None
    schema_success: bool | None
    validation_error_count: int | None = None
    if architecture == "A":
        json_success = None
        schema_success = None
    else:
        if error_type == "invalid_json" or json_parse_error is not None:
            json_success = False
            schema_success = False
        elif validation_error is not None:
            json_success = True
            schema_success = False
            validation_error_count = _validation_error_count(validation_error)
        elif status == "success" and (run_dir / "parsed_report.json").exists():
            json_success = True
            schema_success = True
            validation_error_count = 0
        elif _metadata_mentions_invalid_json(metadata):
            json_success = False
            schema_success = False
        else:
            json_success = None
            schema_success = None

    if validation_error is not None and validation_error_count is None:
        validation_error_count = _validation_error_count(validation_error)

    return {
        "run_id": metadata.get("run_id") or run_dir.name,
        "architecture": architecture,
        "case_id": metadata.get("case_id"),
        "prompt_version": metadata.get("prompt_version"),
        "model": metadata.get("model"),
        "status": status,
        "started_at": metadata.get("started_at"),
        "latency_ms": metadata.get("latency_ms"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "error_type": error_type,
        "json_success": json_success,
        "schema_success": schema_success,
        "validation_error_count": validation_error_count,
        "output_directory": metadata.get("output_directory") or str(run_dir),
    }


def format_table(records: list[dict[str, Any]]) -> str:
    headers = [
        "run_id",
        "arch",
        "case",
        "prompt",
        "status",
        "json",
        "schema",
        "errors",
        "latency_ms",
        "tokens",
    ]
    rows = [
        [
            str(record["run_id"]),
            str(record["architecture"]),
            str(record["case_id"]),
            str(record["prompt_version"]),
            str(record["status"]),
            _format_optional_bool(record["json_success"]),
            _format_optional_bool(record["schema_success"]),
            "" if record["validation_error_count"] is None else str(record["validation_error_count"]),
            "" if record["latency_ms"] is None else str(record["latency_ms"]),
            "" if record["total_tokens"] is None else str(record["total_tokens"]),
        ]
        for record in records
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows)) if rows else len(headers[index])
        for index in range(len(headers))
    ]
    lines = [_format_row(headers, widths), _format_row(["-" * width for width in widths], widths)]
    lines.extend(_format_row(row, widths) for row in rows)
    return "\n".join(lines)


def _read_optional_json(path: Path, warnings: list[str]) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warnings.append(f"Failed to read diagnostic {path}: {exc}")
        return None


def _validation_error_count(validation_error: dict[str, Any]) -> int:
    if isinstance(validation_error.get("error_count"), int):
        return validation_error["error_count"]
    errors = validation_error.get("errors")
    if isinstance(errors, list):
        return len(errors)
    return 0


def _metadata_mentions_invalid_json(metadata: dict[str, Any]) -> bool:
    message = str(metadata.get("error_message") or "")
    return "JSON response is not valid JSON" in message


def _format_optional_bool(value: bool | None) -> str:
    if value is None:
        return "null"
    return "true" if value else "false"


def _format_row(values: list[str], widths: list[int]) -> str:
    return " | ".join(value.ljust(widths[index]) for index, value in enumerate(values))


if __name__ == "__main__":
    raise SystemExit(main())
