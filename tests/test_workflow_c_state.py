from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agent.workflow_c.state import (
    AnalysisMode,
    ArchitectureCStateSnapshot,
    ContextSufficiencyResult,
    FailureCategory,
    NodeValidationIssue,
    SourceIndexItem,
    SourceIndexResult,
    WorkflowFailure,
    WorkflowNodeName,
    WorkflowStatus,
)
from schemas.common_models import ContextQuality, EvidenceSourceType


def minimal_snapshot(**overrides):
    payload = {
        "run_id": "C-test",
        "architecture_version": "C",
        "workflow_version": "c_skeleton_v1",
        "schema_version": "1.0",
        "workflow_status": WorkflowStatus.initialized,
        "case_input": {"case_id": "DEV-01"},
        "human_review_required": True,
    }
    payload.update(overrides)
    return payload


def source_item(source_id: str = "MTG-01", order: int = 1) -> SourceIndexItem:
    return SourceIndexItem(
        source_id=source_id,
        source_type=EvidenceSourceType.meeting_transcript,
        source_order=order,
        title="Meeting",
        content="Meeting content",
        verified=True,
    )


def test_valid_state_snapshot_can_be_created() -> None:
    snapshot = ArchitectureCStateSnapshot.model_validate(minimal_snapshot())

    assert snapshot.architecture_version == "C"


def test_snapshot_model_dump_json_succeeds() -> None:
    snapshot = ArchitectureCStateSnapshot.model_validate(minimal_snapshot())

    assert snapshot.model_dump(mode="json")["workflow_version"] == "c_skeleton_v1"


def test_snapshot_extra_field_fails() -> None:
    with pytest.raises(ValidationError):
        ArchitectureCStateSnapshot.model_validate(minimal_snapshot(extra_field=True))


def test_failed_status_without_failure_fails() -> None:
    with pytest.raises(ValidationError, match="failure"):
        ArchitectureCStateSnapshot.model_validate(
            minimal_snapshot(workflow_status=WorkflowStatus.failed)
        )


def test_awaiting_human_review_without_decision_fails() -> None:
    with pytest.raises(ValidationError, match="review decision"):
        ArchitectureCStateSnapshot.model_validate(
            minimal_snapshot(workflow_status=WorkflowStatus.awaiting_human_review)
        )


def test_workflow_failure_can_save_validation_issues() -> None:
    failure = WorkflowFailure(
        failure_id="failure-1",
        node_name=WorkflowNodeName.fact_extraction,
        failure_category=FailureCategory.schema_validation,
        message="schema failed",
        retryable=False,
        attempt=1,
        occurred_at=datetime.now(UTC),
        validation_issues=[
            NodeValidationIssue(
                location="facts.0",
                error_type="value_error",
                message="bad fact",
                input_summary="short",
            )
        ],
    )

    assert failure.validation_issues[0].location == "facts.0"


def test_state_model_fields_do_not_include_reference_pack() -> None:
    assert "reference_pack" not in ArchitectureCStateSnapshot.model_fields


def test_state_model_fields_do_not_include_api_key() -> None:
    assert "api_key" not in ArchitectureCStateSnapshot.model_fields


def test_source_index_count_mismatch_fails() -> None:
    with pytest.raises(ValidationError, match="Source count"):
        SourceIndexResult(items=[source_item()], source_count=2)


def test_source_index_duplicate_source_id_fails() -> None:
    with pytest.raises(ValidationError, match="Source IDs"):
        SourceIndexResult(items=[source_item("A-01", 1), source_item("A-01", 2)], source_count=2)


def test_context_quality_and_analysis_mode_mismatch_fails() -> None:
    with pytest.raises(ValidationError, match="Context quality"):
        ContextSufficiencyResult(
            context_quality=ContextQuality.sufficient,
            analysis_mode=AnalysisMode.partial_analysis,
            available_categories=["business_goal"],
            missing_categories=[],
            blocking_gaps=[],
            reasoning_summary="This reasoning is long enough.",
        )
