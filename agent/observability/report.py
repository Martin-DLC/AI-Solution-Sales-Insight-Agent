from __future__ import annotations

from agent.observability.models import ObservationSnapshot


def render_observation_report(snapshot: ObservationSnapshot) -> str:
    formal = snapshot.formal_path
    shadow = snapshot.shadow_path
    skills = snapshot.skills
    providers = snapshot.providers
    fallback = snapshot.fallback
    output = snapshot.output_summary
    safety = snapshot.safety_notes

    lines = [
        "# Solution Insight Observability Report",
        "",
        "## Request",
        f"- request_id: `{snapshot.request_id}`",
        f"- generated_at: `{snapshot.generated_at}`",
        f"- llm_mode: `{snapshot.input_summary.llm_mode}`",
        f"- company_id_present: `{snapshot.input_summary.company_id_present}`",
        f"- shadow_requested: `{snapshot.input_summary.shadow_requested}`",
        f"- requirement_preview: {snapshot.input_summary.user_query_preview}",
        "",
        "## Formal Retrieval Path",
        f"- formal_candidate_count: {formal.formal_candidate_count}",
        f"- evidence_count: {formal.evidence_count}",
        f"- evidence_titles: {', '.join(formal.evidence_titles) if formal.evidence_titles else '(none)'}",
        f"- retrieval_method: `{formal.retrieval_debug_summary.get('retrieval_method', '')}`",
        f"- blocked_retrieval_status: `{formal.retrieval_debug_summary.get('blocked_retrieval_status', '')}`",
        f"- selected_method: `{formal.retrieval_debug_summary.get('selected_method', '')}`",
        "",
        "## Shadow Retrieval Path",
        f"- shadow_enabled: `{shadow.shadow_enabled}`",
        f"- shadow_candidate_count: {shadow.shadow_candidate_count}",
        f"- document_candidate_count: {shadow.document_candidate_count}",
        f"- chunk_candidate_count: {shadow.chunk_candidate_count}",
        f"- runtime_eligible_count: {shadow.runtime_eligible_count}",
        f"- runtime_rejected_count: {shadow.runtime_rejected_count}",
        f"- shadow_error: `{shadow.shadow_error}`",
        "",
        "## Skill Execution Trace",
        f"- executed_skills: {', '.join(skills.executed_skills) if skills.executed_skills else '(none)'}",
        f"- skill_count: {skills.skill_count}",
        f"- failed_skill_count: {skills.failed_skill_count}",
        f"- total_elapsed_ms: {skills.total_elapsed_ms}",
        f"- warnings: {', '.join(skills.warnings) if skills.warnings else '(none)'}",
        "",
        "## Enterprise Context Providers",
        f"- provider_names: {', '.join(providers.provider_names) if providers.provider_names else '(none)'}",
        f"- provider_success_count: {providers.provider_success_count}",
        f"- provider_failed_count: {providers.provider_failed_count}",
        f"- provider_skipped_count: {providers.provider_skipped_count}",
        f"- provider_warnings: {', '.join(providers.provider_warnings) if providers.provider_warnings else '(none)'}",
        f"- context_source: `{providers.context_source}`",
        f"- mock_data: `{providers.mock_data}`",
        "",
        "## Fallback Assessment",
        f"- fallback_recommended: `{fallback.fallback_recommended}`",
        f"- fallback_reasons: {', '.join(fallback.fallback_reasons) if fallback.fallback_reasons else '(none)'}",
        f"- human_confirmation_required: `{fallback.human_confirmation_required}`",
        f"- evidence_completeness: `{fallback.evidence_completeness}`",
        "",
        "## Output Summary",
        f"- requirement_summary: {output.requirement_summary}",
        f"- pain_point_count: {output.pain_point_count}",
        f"- opportunity_count: {output.opportunity_count}",
        f"- proposed_solution_preview: {output.proposed_solution_preview}",
        "",
        "## Safety Notes",
        f"- boundary_status: `{safety.boundary_status}`",
        f"- shadow_does_not_affect_formal_answer: `{safety.shadow_does_not_affect_formal_answer}`",
        f"- deterministic_or_llm_mode: `{safety.deterministic_or_llm_mode}`",
        "- fallback exists because the formal gate or boundary status may still be blocked.",
        "- provider data is mock data when `mock_data=true`.",
    ]
    return "\n".join(lines) + "\n"
