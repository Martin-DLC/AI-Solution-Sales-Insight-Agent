from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.retrieval.metadata_authoring_v2 import (  # noqa: E402
    TRACKED_DOC_PATH,
    TRACKED_MANIFEST_PATH,
    TRACKED_MAPPING_PATH,
    TRACKED_PACKET_PATH,
    RUNTIME_BUNDLE_DIR,
    build_authoring_packet,
    build_plan_payload,
    check_authoring_outputs,
    load_authoring_sources,
    write_authoring_outputs,
    PROTOCOL_VERSION,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the retrieval metadata blind authoring packet without reading cases, gold, or formal results."
    )
    parser.add_argument("--write", action="store_true", help="Write tracked artifacts and the gitignored blind bundle.")
    parser.add_argument("--check", action="store_true", help="Recompute and compare tracked artifacts and blind bundle outputs.")
    args = parser.parse_args()

    if args.write and args.check:
        print("Choose either --write or --check, not both.", file=sys.stderr)
        return 2

    if args.check:
        ok, differences = check_authoring_outputs()
        print(
            json.dumps(
                {
                    "mode": "check",
                    "status": "authoring_packet_outputs_match" if ok else "authoring_packet_outputs_drifted",
                    "differences": differences,
                    "tracked_outputs": {
                        "packet": str(TRACKED_PACKET_PATH),
                        "mapping": str(TRACKED_MAPPING_PATH),
                        "manifest": str(TRACKED_MANIFEST_PATH),
                        "protocol_doc": str(TRACKED_DOC_PATH),
                    },
                    "runtime_bundle_dir": str(RUNTIME_BUNDLE_DIR),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if ok else 1

    if args.write:
        documents, chunks, solution_scope = load_authoring_sources()
        payload = build_authoring_packet(documents, chunks, solution_scope, PROTOCOL_VERSION)
        write_authoring_outputs(payload)
        manifest = payload["bundle_manifest_payload"]
        print(
            json.dumps(
                {
                    "mode": "write",
                    "protocol_version": PROTOCOL_VERSION,
                    "document_count": manifest["document_count"],
                    "chunk_count": manifest["chunk_count"],
                    "packet_contains_cases": manifest["packet_contains_cases"],
                    "packet_contains_gold": manifest["packet_contains_gold"],
                    "packet_contains_results": manifest["packet_contains_results"],
                    "packet_contains_original_ids": manifest["packet_contains_original_ids"],
                    "labels_prefilled": manifest["labels_prefilled"],
                    "runtime_bundle_dir": str(RUNTIME_BUNDLE_DIR),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    print(json.dumps(build_plan_payload(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
