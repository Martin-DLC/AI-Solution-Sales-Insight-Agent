from __future__ import annotations

from datetime import UTC, datetime

from agent.models import SolutionInsightResponse
from agent.observability.models import (
    ObservationFallback,
    ObservationFormalPath,
    ObservationInputSummary,
    ObservationOutputSummary,
    ObservationProviders,
    ObservationSafetyNotes,
    ObservationShadowPath,
    ObservationSkills,
    ObservationSnapshot,
)


def build_observation_snapshot(response: SolutionInsightResponse) -> ObservationSnapshot:
    retrieval_debug = response.retrieval_debug
    shadow_debug = response.shadow_retrieval_debug
    enterprise_context = response.enterprise_context
    skill_trace = response.skill_trace
    warnings = [] if skill_trace is None else list(skill_trace.warnings)
    provider_results = [] if enterprise_context is None else list(enterprise_context.provider_results)

    return ObservationSnapshot(
        request_id=response.request_id,
        generated_at=datetime.now(UTC).isoformat(),
        input_summary=ObservationInputSummary(
            user_query_preview=_safe_preview(response.requirement_summary, limit=80),
            llm_mode=response.llm_mode,
            company_id_present=enterprise_context is not None,
            shadow_requested=shadow_debug is not None,
            enterprise_context_present=enterprise_context is not None,
        ),
        formal_path=ObservationFormalPath(
            formal_candidate_count=retrieval_debug.formal_candidate_count,
            evidence_count=len(response.evidence_items),
            evidence_titles=[item.title for item in response.evidence_items],
            retrieval_debug_summary={
                "retrieval_method": retrieval_debug.retrieval_method,
                "query_hash": retrieval_debug.query_hash,
                "blocked_retrieval_status": retrieval_debug.blocked_retrieval_status,
                "selected_method": retrieval_debug.selected_method,
                "selection_status": retrieval_debug.selection_status,
                "top_k": retrieval_debug.top_k,
            },
        ),
        shadow_path=ObservationShadowPath(
            shadow_enabled=shadow_debug is not None,
            shadow_candidate_count=0 if shadow_debug is None else shadow_debug.candidate_count,
            document_candidate_count=0 if shadow_debug is None else shadow_debug.document_candidate_count,
            chunk_candidate_count=0 if shadow_debug is None else shadow_debug.chunk_candidate_count,
            runtime_eligible_count=0 if shadow_debug is None else shadow_debug.runtime_eligible_count,
            runtime_rejected_count=0 if shadow_debug is None else shadow_debug.runtime_rejected_count,
            shadow_error=None if shadow_debug is None else shadow_debug.shadow_error,
        ),
        skills=ObservationSkills(
            executed_skills=[] if skill_trace is None else list(skill_trace.executed_skills),
            skill_count=0 if skill_trace is None else skill_trace.skill_count,
            failed_skill_count=0 if skill_trace is None else skill_trace.failed_skill_count,
            total_elapsed_ms=0 if skill_trace is None else skill_trace.total_elapsed_ms,
            warnings=warnings,
        ),
        providers=ObservationProviders(
            provider_success_count=0 if enterprise_context is None else enterprise_context.provider_success_count,
            provider_failed_count=0 if enterprise_context is None else enterprise_context.provider_failed_count,
            provider_skipped_count=0 if enterprise_context is None else enterprise_context.provider_skipped_count,
            provider_warnings=[] if enterprise_context is None else list(enterprise_context.provider_warnings),
            provider_names=[item.get("provider_name", "") for item in provider_results if item.get("provider_name")],
            mock_data=True if enterprise_context is None else enterprise_context.mock_data,
            context_source=None if enterprise_context is None else enterprise_context.context_source,
        ),
        fallback=ObservationFallback(
            fallback_recommended=response.fallback_recommended,
            fallback_reasons=list(response.fallback_reasons),
            human_confirmation_required=response.human_confirmation_required,
            evidence_completeness=response.evidence_completeness,
        ),
        output_summary=ObservationOutputSummary(
            requirement_summary=_safe_preview(response.requirement_summary, limit=120),
            pain_point_count=len(response.pain_points),
            opportunity_count=len(response.ai_opportunity_points),
            proposed_solution_preview=_safe_preview(response.proposed_solution, limit=160),
        ),
        safety_notes=ObservationSafetyNotes(
            boundary_status=retrieval_debug.blocked_retrieval_status,
            shadow_does_not_affect_formal_answer=True,
            deterministic_or_llm_mode=response.llm_mode,
        ),
    )


def _safe_preview(value: str, *, limit: int) -> str:
    normalized = " ".join(value.split())
    return normalized[:limit]
