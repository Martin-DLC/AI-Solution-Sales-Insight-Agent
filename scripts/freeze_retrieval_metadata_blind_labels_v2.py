from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.retrieval.metadata_label_freeze_v2 import (  # noqa: E402
    _tracked_outputs_for_variant,
    TRACKED_DOC_PATH,
    TRACKED_FREEZE_MANIFEST_PATH,
    TRACKED_LABELS_PATH,
    TRACKED_REPORT_PATH,
    build_plan_payload,
    check_frozen_outputs,
    freeze_blind_labels,
    write_frozen_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Freeze blind-authored retrieval metadata labels without running any evaluation."
    )
    parser.add_argument("--protocol-version", default="2.1", help="Freeze protocol version to validate and import.")
    parser.add_argument("--attempt-number", type=int, default=1, help="Blind authoring attempt number to freeze.")
    parser.add_argument("--source-dir", type=Path, help="External isolated blind authoring directory.")
    parser.add_argument("--write", action="store_true", help="Validate and import frozen labels from the external isolated directory.")
    parser.add_argument("--check", action="store_true", help="Check frozen tracked outputs without re-reading the external source directory.")
    args = parser.parse_args()

    if args.write and args.check:
        print("Choose either --write or --check, not both.", file=sys.stderr)
        return 2

    if args.check:
        ok, differences = check_frozen_outputs(
            protocol_version=args.protocol_version,
            attempt_number=args.attempt_number,
        )
        tracked_outputs = _tracked_outputs_for_variant(
            protocol_version=args.protocol_version,
            attempt_number=args.attempt_number,
        )
        print(
            json.dumps(
                {
                    "mode": "check",
                    "status": "blind_label_freeze_outputs_match" if ok else "blind_label_freeze_outputs_drifted",
                    "differences": differences,
                    "tracked_outputs": {
                        "labels": str(tracked_outputs["labels"]),
                        "authoring_report": str(tracked_outputs["authoring_report"]),
                        "freeze_manifest": str(tracked_outputs["freeze_manifest"]),
                        "freeze_doc": str(tracked_outputs["freeze_doc"]),
                    },
                    "protocol_version": args.protocol_version,
                    "blind_attempt_number": args.attempt_number,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if ok else 1

    if args.source_dir is None:
        if args.write:
            print("--source-dir is required with --write.", file=sys.stderr)
            return 2
        print(
            json.dumps(
                build_plan_payload(
                    source_dir=Path("<required-source-dir>"),
                    protocol_version=args.protocol_version,
                    attempt_number=args.attempt_number,
                ),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.write:
        payload = freeze_blind_labels(
            source_dir=args.source_dir,
            protocol_version=args.protocol_version,
            attempt_number=args.attempt_number,
        )
        write_frozen_outputs(payload)
        print(
            json.dumps(
                {
                    "mode": "write",
                    "protocol_version": payload["protocol_version"],
                    "blind_attempt_number": payload["attempt_number"],
                    "source_dir_validated": True,
                    "document_count": payload["freeze_manifest"]["document_count"],
                    "chunk_count": payload["freeze_manifest"]["chunk_count"],
                    "evaluation_performed": payload["freeze_manifest"]["evaluation_performed"],
                    "p0_validation_status": payload["freeze_manifest"]["p0_validation_status"],
                    "architecture_c_status": payload["freeze_manifest"]["architecture_c_status"],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    print(
        json.dumps(
            build_plan_payload(
                source_dir=args.source_dir,
                protocol_version=args.protocol_version,
                attempt_number=args.attempt_number,
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
