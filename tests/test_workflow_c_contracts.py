from __future__ import annotations

import pytest

from agent.workflow_c.contracts import (
    ContextSufficiencyOutput,
    ExplicitNeedNodeOutput,
    FakeFactExtractionOutput,
    FactExtractionNodeOutput,
    HumanReviewGateOutput,
    InputValidationOutput,
    NodeContract,
    NodeFailurePolicy,
    SolutionRetrievalNodeOutput,
    SourceIndexingOutput,
)
from agent.workflow_c.retrieval_models import SolutionRetrievalResult
from agent.workflow_c.fake_llm import default_explicit_need_response, default_fact_response
from agent.workflow_c.state import (
    AnalysisMode,
    ContextSufficiencyResult,
    HumanReviewDecision,
    SourceIndexItem,
    SourceIndexResult,
    WorkflowNodeName,
    WorkflowStatus,
)
from dataio.runtime_cases import load_runtime_cases
from schemas.common_models import ContextQuality, EvidenceSourceType


def test_valid_node_contract_can_be_created() -> None:
    contract = NodeContract(
        name=WorkflowNodeName.input_validation,
        required_state_fields=("case_input",),
        produced_state_fields=("validated_case",),
        output_model=InputValidationOutput,
        failure_policy=NodeFailurePolicy.fail_workflow,
    )

    assert contract.name is WorkflowNodeName.input_validation


def test_produced_fields_empty_fails() -> None:
    with pytest.raises(ValueError, match="Produced"):
        NodeContract(
            name=WorkflowNodeName.input_validation,
            required_state_fields=(),
            produced_state_fields=(),
            output_model=InputValidationOutput,
            failure_policy=NodeFailurePolicy.fail_workflow,
        )


def test_required_fields_duplicate_fails() -> None:
    with pytest.raises(ValueError, match="Required"):
        NodeContract(
            name=WorkflowNodeName.input_validation,
            required_state_fields=("case_input", "case_input"),
            produced_state_fields=("validated_case",),
            output_model=InputValidationOutput,
            failure_policy=NodeFailurePolicy.fail_workflow,
        )


def test_produced_fields_duplicate_fails() -> None:
    with pytest.raises(ValueError, match="Produced"):
        NodeContract(
            name=WorkflowNodeName.input_validation,
            required_state_fields=("case_input",),
            produced_state_fields=("validated_case", "validated_case"),
            output_model=InputValidationOutput,
            failure_policy=NodeFailurePolicy.fail_workflow,
        )


def test_required_and_produced_overlap_fails() -> None:
    with pytest.raises(ValueError, match="overlap"):
        NodeContract(
            name=WorkflowNodeName.input_validation,
            required_state_fields=("case_input",),
            produced_state_fields=("case_input",),
            output_model=InputValidationOutput,
            failure_policy=NodeFailurePolicy.fail_workflow,
        )


def test_node_cannot_declare_node_records() -> None:
    with pytest.raises(ValueError, match="internal"):
        NodeContract(
            name=WorkflowNodeName.input_validation,
            required_state_fields=("node_records",),
            produced_state_fields=("validated_case",),
            output_model=InputValidationOutput,
            failure_policy=NodeFailurePolicy.fail_workflow,
        )


def test_node_cannot_declare_failures() -> None:
    with pytest.raises(ValueError, match="internal"):
        NodeContract(
            name=WorkflowNodeName.input_validation,
            required_state_fields=("case_input",),
            produced_state_fields=("failures",),
            output_model=InputValidationOutput,
            failure_policy=NodeFailurePolicy.fail_workflow,
        )


def test_output_wrappers_validate() -> None:
    case = load_runtime_cases("data/evaluation/development_cases.jsonl")[0]
    source_index = SourceIndexResult(
        items=[
            SourceIndexItem(
                source_id="MTG-01",
                source_type=EvidenceSourceType.meeting_transcript,
                source_order=1,
                title="Meeting",
                content="Meeting content",
                verified=True,
            )
        ],
        source_count=1,
    )
    context = ContextSufficiencyResult(
        context_quality=ContextQuality.partially_sufficient,
        analysis_mode=AnalysisMode.partial_analysis,
        available_categories=["business_goal"],
        missing_categories=["budget"],
        blocking_gaps=[],
        reasoning_summary="Context is enough for partial analysis.",
    )

    assert InputValidationOutput(validated_case=case)
    assert SourceIndexingOutput(source_index=source_index)
    assert FactExtractionNodeOutput(fact_extraction=default_fact_response())
    assert FakeFactExtractionOutput(fact_extraction=default_fact_response())
    assert ExplicitNeedNodeOutput(**default_explicit_need_response())
    assert SolutionRetrievalNodeOutput(
        retrieved_solutions=SolutionRetrievalResult(
            query_text="NO_ELIGIBLE_AI_OPPORTUNITY",
            eligible_opportunity_ids=[],
            top_k=5,
            candidate_count=0,
            candidates=[],
        )
    )
    assert ContextSufficiencyOutput(context_sufficiency=context)
    assert HumanReviewGateOutput(
        human_review_decision=HumanReviewDecision(
            reasons=["review needed"],
            blocked_actions=["发送客户邮件"],
        ),
        human_review_required=True,
        human_review_reasons=["review needed"],
        workflow_status=WorkflowStatus.awaiting_human_review,
    )
