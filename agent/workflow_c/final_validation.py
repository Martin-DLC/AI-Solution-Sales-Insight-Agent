from __future__ import annotations

import json
import re
from typing import Any

from pydantic import field_validator, model_validator

from agent.workflow_c.decision_models import ActionTrace, RiskTrace
from agent.workflow_c.retrieval_models import SolutionRetrievalResult
from schemas.common_models import StrictBaseModel
from schemas.decision_models import DealScore, NextBestAction
from schemas.insight_models import InformationGap
from schemas.output_models import SalesInsightReport
from schemas.solution_models import AIOpportunity, Risk, SolutionRecommendation

_FORBIDDEN_REPORT_KEYS = {
    "risk_trace",
    "risk_traces",
    "action_trace",
    "action_traces",
    "node_records",
    "failures",
    "artifact_paths",
    "matched_terms",
    "prompt_version",
    "api_key",
}
_ALLOWED_RECOMMENDATION_SUITABILITIES = {
    "suitable_now",
    "suitable_for_poc",
    "suitable_after_prerequisites",
}
_HIGH_OR_CRITICAL = {"high", "critical"}
_SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]+", re.IGNORECASE)


def _redact_secrets(value: str) -> str:
    return _SECRET_PATTERN.sub("[REDACTED]", value)


class FinalValidationIssue(StrictBaseModel):
    issue_code: str
    location: str
    message: str
    blocking: bool

    @field_validator("message")
    @classmethod
    def message_must_be_safe(cls, value: str) -> str:
        safe = _redact_secrets(value)
        if "Authorization" in safe:
            safe = safe.replace("Authorization", "[REDACTED]")
        if len(safe) > 300:
            safe = f"{safe[:297]}..."
        return safe


class FinalValidationResult(StrictBaseModel):
    passed: bool
    issues: list[FinalValidationIssue]
    blocking_issue_count: int

    @model_validator(mode="after")
    def validate_counts(self) -> "FinalValidationResult":
        blocking_count = sum(1 for issue in self.issues if issue.blocking)
        if self.blocking_issue_count != blocking_count:
            raise ValueError("blocking_issue_count must equal the number of blocking issues.")
        if self.passed and self.blocking_issue_count != 0:
            raise ValueError("Passed validation cannot contain blocking issues.")
        if not self.passed and self.blocking_issue_count < 1:
            raise ValueError("Failed validation must contain at least one blocking issue.")
        return self


def build_validation_issue(
    *,
    issue_code: str,
    location: str,
    message: str,
    blocking: bool,
) -> FinalValidationIssue:
    safe_message = _redact_secrets(message)
    if "Authorization" in safe_message:
        safe_message = safe_message.replace("Authorization", "[REDACTED]")
    return FinalValidationIssue(
        issue_code=issue_code,
        location=location,
        message=safe_message,
        blocking=blocking,
    )


def find_forbidden_report_keys(payload: object) -> list[str]:
    seen: set[str] = set()
    matches: list[str] = []

    def walk(value: object, path: str) -> None:
        if isinstance(value, dict):
            for key in value:
                next_path = f"{path}.{key}"
                if key in _FORBIDDEN_REPORT_KEYS and next_path not in seen:
                    seen.add(next_path)
                    matches.append(next_path)
                walk(value[key], next_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(payload, "$")
    return matches


def validate_report_draft(
    *,
    report_draft: SalesInsightReport,
    expected_case_id: str,
    retrieved_solutions: SolutionRetrievalResult,
    ai_opportunities: list[AIOpportunity],
    solution_recommendations: list[SolutionRecommendation],
    deal_score: DealScore,
    information_gaps: list[InformationGap],
    risks_and_objections: list[Risk],
    next_best_actions: list[NextBestAction],
    risk_traces: list[RiskTrace],
    action_traces: list[ActionTrace],
) -> FinalValidationResult:
    issues: list[FinalValidationIssue] = []
    dumped = report_draft.model_dump(mode="json")

    try:
        SalesInsightReport.model_validate(dumped)
    except Exception:
        issues.append(
            build_validation_issue(
                issue_code="REPORT_SCHEMA_INVALID",
                location="report_draft",
                message="Report draft failed final SalesInsightReport schema validation.",
                blocking=True,
            )
        )

    if report_draft.case_id != expected_case_id:
        issues.append(
            build_validation_issue(
                issue_code="CASE_ID_MISMATCH",
                location="report_draft.case_id",
                message="Report draft case_id does not match the validated case.",
                blocking=True,
            )
        )

    if report_draft.reliability_summary.human_review_required is not True:
        issues.append(
            build_validation_issue(
                issue_code="HUMAN_REVIEW_DISABLED",
                location="report_draft.reliability_summary.human_review_required",
                message="Final outputs must keep human review enabled.",
                blocking=True,
            )
        )

    issues.extend(
        _validate_deal_score(report_draft=report_draft, deal_score=deal_score)
    )
    issues.extend(
        _validate_recommendations(
            report_draft=report_draft,
            retrieved_solutions=retrieved_solutions,
            ai_opportunities=ai_opportunities,
            solution_recommendations=solution_recommendations,
        )
    )
    issues.extend(
        _validate_traces(
            report_draft=report_draft,
            information_gaps=information_gaps,
            risks_and_objections=risks_and_objections,
            next_best_actions=next_best_actions,
            risk_traces=risk_traces,
            action_traces=action_traces,
        )
    )

    forbidden_paths = find_forbidden_report_keys(dumped)
    if forbidden_paths:
        issues.append(
            build_validation_issue(
                issue_code="INTERNAL_WORKFLOW_DATA_LEAK",
                location="report_draft",
                message=f"Report draft contains forbidden internal keys: {', '.join(forbidden_paths)}.",
                blocking=True,
            )
        )

    blocking_count = sum(1 for issue in issues if issue.blocking)
    return FinalValidationResult(
        passed=blocking_count == 0,
        issues=issues,
        blocking_issue_count=blocking_count,
    )


def _validate_deal_score(
    *,
    report_draft: SalesInsightReport,
    deal_score: DealScore,
) -> list[FinalValidationIssue]:
    issues: list[FinalValidationIssue] = []
    if report_draft.deal_score.model_dump(mode="json") != deal_score.model_dump(mode="json"):
        issues.append(
            build_validation_issue(
                issue_code="DEAL_SCORE_MISMATCH",
                location="report_draft.deal_score",
                message="Report deal score does not match the workflow state deal score.",
                blocking=True,
            )
        )
    total = sum(dimension.score for dimension in report_draft.deal_score.dimensions)
    if report_draft.deal_score.total_score != total or not 0 <= report_draft.deal_score.total_score <= 100:
        issues.append(
            build_validation_issue(
                issue_code="DEAL_SCORE_TOTAL_INVALID",
                location="report_draft.deal_score.total_score",
                message="Deal score total must equal the sum of dimensions and stay within 0 to 100.",
                blocking=True,
            )
        )
    for index, dimension in enumerate(report_draft.deal_score.dimensions):
        if dimension.score < 0 or dimension.score > dimension.max_score:
            issues.append(
                build_validation_issue(
                    issue_code="DEAL_SCORE_DIMENSION_INVALID",
                    location=f"report_draft.deal_score.dimensions[{index}]",
                    message="Deal score dimension score must stay between 0 and max_score.",
                    blocking=True,
                )
            )
            break
    return issues


def _validate_recommendations(
    *,
    report_draft: SalesInsightReport,
    retrieved_solutions: SolutionRetrievalResult,
    ai_opportunities: list[AIOpportunity],
    solution_recommendations: list[SolutionRecommendation],
) -> list[FinalValidationIssue]:
    issues: list[FinalValidationIssue] = []
    if [item.model_dump(mode="json") for item in report_draft.solution_recommendations] != [
        item.model_dump(mode="json") for item in solution_recommendations
    ]:
        issues.append(
            build_validation_issue(
                issue_code="SOLUTION_RECOMMENDATION_MISMATCH",
                location="report_draft.solution_recommendations",
                message="Report solution recommendations do not match the workflow state recommendations.",
                blocking=True,
            )
        )
    candidate_ids = {candidate.solution_id for candidate in retrieved_solutions.candidates}
    if retrieved_solutions.candidate_count == 0 and report_draft.solution_recommendations:
        issues.append(
            build_validation_issue(
                issue_code="RECOMMENDATION_WITHOUT_CANDIDATE",
                location="report_draft.solution_recommendations",
                message="Report recommendations must be empty when retrieval returned zero candidates.",
                blocking=True,
            )
        )
    opportunities = {item.opportunity_id: item for item in ai_opportunities}
    for index, recommendation in enumerate(report_draft.solution_recommendations):
        if recommendation.solution_id not in candidate_ids:
            issues.append(
                build_validation_issue(
                    issue_code="SOLUTION_OUTSIDE_RETRIEVED_CANDIDATES",
                    location=f"report_draft.solution_recommendations[{index}].solution_id",
                    message="Recommended solution must come from retrieved solution candidates.",
                    blocking=True,
                )
            )
        for opportunity_id in recommendation.related_opportunity_ids:
            opportunity = opportunities.get(opportunity_id)
            if opportunity is None:
                issues.append(
                    build_validation_issue(
                        issue_code="UNKNOWN_OPPORTUNITY_REFERENCE",
                        location=f"report_draft.solution_recommendations[{index}].related_opportunity_ids",
                        message="Recommendation references an unknown AI opportunity.",
                        blocking=True,
                    )
                )
                continue
            if opportunity.suitability.value not in _ALLOWED_RECOMMENDATION_SUITABILITIES:
                issues.append(
                    build_validation_issue(
                        issue_code="INELIGIBLE_OPPORTUNITY_RECOMMENDATION",
                        location=f"report_draft.solution_recommendations[{index}].related_opportunity_ids",
                        message="Recommendation references an AI opportunity that is not eligible for recommendation.",
                        blocking=True,
                    )
                )
    return issues


def _validate_traces(
    *,
    report_draft: SalesInsightReport,
    information_gaps: list[InformationGap],
    risks_and_objections: list[Risk],
    next_best_actions: list[NextBestAction],
    risk_traces: list[RiskTrace],
    action_traces: list[ActionTrace],
) -> list[FinalValidationIssue]:
    issues: list[FinalValidationIssue] = []
    report_risk_ids = {risk.risk_id for risk in report_draft.risks_and_objections}
    report_action_ids = {action.action_id for action in report_draft.next_best_actions}
    gap_by_id = {gap.gap_id: gap for gap in information_gaps}
    risk_by_id = {risk.risk_id: risk for risk in risks_and_objections}

    for index, trace in enumerate(risk_traces):
        if trace.risk_id not in report_risk_ids:
            issues.append(
                build_validation_issue(
                    issue_code="ORPHAN_RISK_TRACE",
                    location=f"risk_traces[{index}].risk_id",
                    message="Risk trace must reference a risk present in the report draft.",
                    blocking=True,
                )
            )
        for gap_id in trace.related_gap_ids:
            if gap_id not in gap_by_id:
                issues.append(
                    build_validation_issue(
                        issue_code="UNKNOWN_GAP_REFERENCE",
                        location=f"risk_traces[{index}].related_gap_ids",
                        message="Risk trace references an unknown information gap.",
                        blocking=True,
                    )
                )
                break

    action_trace_by_id = {trace.action_id: trace for trace in action_traces}
    high_gap_ids = {gap.gap_id for gap in information_gaps if gap.priority.value in _HIGH_OR_CRITICAL}
    high_risk_ids = {risk.risk_id for risk in risks_and_objections if risk.severity.value in _HIGH_OR_CRITICAL}

    for index, trace in enumerate(action_traces):
        if trace.action_id not in report_action_ids:
            issues.append(
                build_validation_issue(
                    issue_code="ORPHAN_ACTION_TRACE",
                    location=f"action_traces[{index}].action_id",
                    message="Action trace must reference a next best action present in the report draft.",
                    blocking=True,
                )
            )
        for risk_id in trace.related_risk_ids:
            if risk_id not in risk_by_id:
                issues.append(
                    build_validation_issue(
                        issue_code="UNKNOWN_RISK_REFERENCE",
                        location=f"action_traces[{index}].related_risk_ids",
                        message="Action trace references an unknown risk.",
                        blocking=True,
                    )
                )
                break

    for index, action in enumerate(next_best_actions):
        if action.priority.value != "P0":
            continue
        trace = action_trace_by_id.get(action.action_id)
        related_high_gap = bool(set(action.related_gap_ids) & high_gap_ids)
        related_high_risk = bool(trace and set(trace.related_risk_ids) & high_risk_ids)
        if not related_high_gap and not related_high_risk:
            issues.append(
                build_validation_issue(
                    issue_code="P0_ACTION_WITHOUT_CRITICAL_DRIVER",
                    location=f"report_draft.next_best_actions[{index}]",
                    message="P0 action must be grounded by a high or critical gap or risk.",
                    blocking=True,
                )
            )
    return issues


def canonical_report_json(report: SalesInsightReport) -> str:
    return json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
