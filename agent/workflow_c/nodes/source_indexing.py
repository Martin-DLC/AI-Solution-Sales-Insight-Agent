from __future__ import annotations

import json
from typing import Any

from agent.workflow_c.contracts import NodeContract, NodeFailurePolicy, SourceIndexingOutput
from agent.workflow_c.state import SourceIndexItem, SourceIndexResult, WorkflowNodeName
from schemas import EvaluationCaseInput
from schemas.common_models import EvidenceSourceType


class SourceIndexingNode:
    contract = NodeContract(
        name=WorkflowNodeName.source_indexing,
        required_state_fields=("validated_case",),
        produced_state_fields=("source_index",),
        output_model=SourceIndexingOutput,
        failure_policy=NodeFailurePolicy.require_human_review,
        prompt_version=None,
    )

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        case: EvaluationCaseInput = state["validated_case"]
        items: list[SourceIndexItem] = []

        def add(
            *,
            source_id: str,
            source_type: EvidenceSourceType,
            title: str,
            content: str,
            verified: bool,
        ) -> None:
            items.append(
                SourceIndexItem(
                    source_id=source_id,
                    source_type=source_type,
                    source_order=len(items) + 1,
                    title=title,
                    content=content,
                    verified=verified,
                )
            )

        add(
            source_id="PROFILE-01",
            source_type=EvidenceSourceType.customer_profile,
            title="Customer profile",
            content=json.dumps(case.customer_profile.model_dump(mode="json"), ensure_ascii=False),
            verified=True,
        )
        add(
            source_id="MTG-01",
            source_type=EvidenceSourceType.meeting_transcript,
            title="Meeting transcript",
            content=case.meeting.transcript,
            verified=True,
        )
        for index, note in enumerate(case.salesperson_notes, start=1):
            add(
                source_id=f"NOTE-{index:02d}",
                source_type=EvidenceSourceType.salesperson_note,
                title=f"Salesperson note {index}",
                content=note.content,
                verified=note.verified,
            )
        for index, constraint in enumerate(case.known_constraints, start=1):
            add(
                source_id=f"CONSTRAINT-{index:02d}",
                source_type=EvidenceSourceType.known_constraint,
                title=f"Known constraint {index}",
                content=f"{constraint.category}: {constraint.description}",
                verified=True,
            )
        for index, solution in enumerate(case.available_solution_library, start=1):
            add(
                source_id=f"SOLUTION-{index:02d}",
                source_type=EvidenceSourceType.solution_library,
                title=f"Available solution {index}",
                content=solution,
                verified=True,
            )
        return {
            "source_index": SourceIndexResult(items=items, source_count=len(items)),
        }
