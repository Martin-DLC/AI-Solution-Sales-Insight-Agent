from __future__ import annotations

from pathlib import Path

from agent.workflow_c.evidence_validation import validate_evidence_references
from agent.workflow_c.state import SourceIndexItem, SourceIndexResult, WorkflowNodeName
from schemas.common_models import EvidenceReference, EvidenceSourceType


def source_index() -> SourceIndexResult:
    return SourceIndexResult(
        items=[
            SourceIndexItem(
                source_id="MTG-01",
                source_type=EvidenceSourceType.meeting_transcript,
                source_order=1,
                title="Meeting",
                content="A" * 1000,
                verified=True,
            ),
            SourceIndexItem(
                source_id="NOTE-01",
                source_type=EvidenceSourceType.salesperson_note,
                source_order=2,
                title="Note",
                content="Sensitive note content" * 100,
                verified=False,
            ),
            SourceIndexItem(
                source_id="CONSTRAINT-01",
                source_type=EvidenceSourceType.known_constraint,
                source_order=3,
                title="Constraint",
                content="Constraint content",
                verified=True,
            ),
            SourceIndexItem(
                source_id="SOLUTION-01",
                source_type=EvidenceSourceType.solution_library,
                source_order=4,
                title="Solution",
                content="Solution content",
                verified=True,
            ),
        ],
        source_count=4,
    )


def evidence(source_id: str, source_type: EvidenceSourceType) -> EvidenceReference:
    return EvidenceReference(
        source_id=source_id,
        source_type=source_type,
        evidence_summary="Useful evidence summary.",
    )


def validate(items: list[EvidenceReference], **kwargs):
    return validate_evidence_references(
        node_name=WorkflowNodeName.underlying_pain,
        field_prefix="items.0.evidence",
        evidence=items,
        source_index=source_index(),
        allowed_verified_source_types={
            EvidenceSourceType.customer_profile,
            EvidenceSourceType.meeting_transcript,
            EvidenceSourceType.known_constraint,
        },
        **kwargs,
    )


def test_valid_evidence_passes() -> None:
    assert validate([evidence("MTG-01", EvidenceSourceType.meeting_transcript)]) == []


def test_missing_source_id_generates_issue() -> None:
    issues = validate([evidence("BAD-01", EvidenceSourceType.meeting_transcript)])

    assert issues[0].location == "items.0.evidence.0.source_id"


def test_source_type_mismatch_generates_issue() -> None:
    issues = validate([evidence("MTG-01", EvidenceSourceType.customer_profile)])

    assert issues[0].location == "items.0.evidence.0.source_type"


def test_forbidden_source_type_generates_issue() -> None:
    issues = validate(
        [evidence("SOLUTION-01", EvidenceSourceType.solution_library)],
        forbidden_source_types={EvidenceSourceType.solution_library},
    )

    assert "not allowed" in issues[0].message


def test_unverified_salesperson_note_alone_fails() -> None:
    issues = validate([evidence("NOTE-01", EvidenceSourceType.salesperson_note)])

    assert issues
    assert "verified source" in issues[-1].message


def test_meeting_verified_true_passes() -> None:
    assert validate([evidence("MTG-01", EvidenceSourceType.meeting_transcript)]) == []


def test_known_constraint_verified_true_passes() -> None:
    assert validate([evidence("CONSTRAINT-01", EvidenceSourceType.known_constraint)]) == []


def test_meeting_plus_salesperson_note_passes() -> None:
    assert validate(
        [
            evidence("MTG-01", EvidenceSourceType.meeting_transcript),
            evidence("NOTE-01", EvidenceSourceType.salesperson_note),
        ]
    ) == []


def test_issue_does_not_include_full_source_content() -> None:
    issues = validate([evidence("NOTE-01", EvidenceSourceType.salesperson_note)])

    assert "Sensitive note content" not in str([issue.model_dump(mode="json") for issue in issues])


def test_input_summary_is_short() -> None:
    issues = validate(
        [evidence("SOLUTION-01", EvidenceSourceType.solution_library)],
        forbidden_source_types={EvidenceSourceType.solution_library},
    )

    assert issues[0].input_summary is None or len(issues[0].input_summary) <= 500


def test_tool_does_not_import_reference_pack() -> None:
    source = Path("agent/workflow_c/evidence_validation.py").read_text(encoding="utf-8")

    assert "evaluation_references" not in source
    assert "HiddenReferencePack" not in source
