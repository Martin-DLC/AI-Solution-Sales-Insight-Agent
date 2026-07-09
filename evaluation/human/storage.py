from __future__ import annotations

import json
from pathlib import Path

from dataio.jsonl_loader import load_jsonl_models
from evaluation.human.models import SolutionInsightHumanAnnotation, SolutionInsightHumanEvalPacket
from evaluation.human.packet_builder import ANNOTATION_TEMPLATE_PATH, PACKET_PATH


LOCAL_ANNOTATIONS_PATH = Path("data/evaluation/human/solution_insight_human_eval_annotations.local.jsonl")


def load_packets() -> list[SolutionInsightHumanEvalPacket]:
    return load_jsonl_models(PACKET_PATH, SolutionInsightHumanEvalPacket)


def load_packet_map() -> dict[str, SolutionInsightHumanEvalPacket]:
    return {packet.case_id: packet for packet in load_packets()}


def load_annotation_template() -> list[SolutionInsightHumanAnnotation]:
    return load_jsonl_models(ANNOTATION_TEMPLATE_PATH, SolutionInsightHumanAnnotation)


def load_annotation_template_map() -> dict[str, SolutionInsightHumanAnnotation]:
    return {item.case_id: item for item in load_annotation_template()}


def load_local_annotations() -> list[SolutionInsightHumanAnnotation]:
    if not LOCAL_ANNOTATIONS_PATH.exists():
        return []
    return load_jsonl_models(LOCAL_ANNOTATIONS_PATH, SolutionInsightHumanAnnotation)


def load_local_annotation_map() -> dict[str, SolutionInsightHumanAnnotation]:
    return {item.case_id: item for item in load_local_annotations()}


def load_effective_annotations() -> dict[str, SolutionInsightHumanAnnotation]:
    effective = load_annotation_template_map()
    effective.update(load_local_annotation_map())
    return effective


def save_local_annotation(annotation: SolutionInsightHumanAnnotation) -> SolutionInsightHumanAnnotation:
    packets = load_packets()
    valid_case_ids = {packet.case_id for packet in packets}
    if annotation.case_id not in valid_case_ids:
        raise KeyError(f"Unknown human eval case_id: {annotation.case_id}")

    annotations = load_local_annotation_map()
    annotations[annotation.case_id] = annotation
    LOCAL_ANNOTATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ordered = [annotations[packet.case_id] for packet in packets if packet.case_id in annotations]
    LOCAL_ANNOTATIONS_PATH.write_text(_serialize_jsonl(ordered), encoding="utf-8")
    return annotation


def _serialize_jsonl(items: list[SolutionInsightHumanAnnotation]) -> str:
    return "".join(json.dumps(item.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n" for item in items)
