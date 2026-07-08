# Solution Insight Observability Report

## Request
- request_id: `insight-f6151c1aeaeb`
- generated_at: `2026-07-08T15:04:30.695467+00:00`
- llm_mode: `deterministic`
- company_id_present: `True`
- shadow_requested: `True`
- requirement_preview: 一家中型 SaaS 公司想提升销售线索转化和客户成功效率

## Formal Retrieval Path
- formal_candidate_count: 5
- evidence_count: 5
- evidence_titles: 客服辅助回复方案说明, 合成服务工单协同案例, 合成零售商品知识治理案例, 合成服务工单协同案例, 客户身份统一与数据集成方案说明
- retrieval_method: `lexical_v2_formal`
- blocked_retrieval_status: `no_eligible_method`
- selected_method: `None`

## Shadow Retrieval Path
- shadow_enabled: `True`
- shadow_candidate_count: 20
- document_candidate_count: 7
- chunk_candidate_count: 13
- runtime_eligible_count: 20
- runtime_rejected_count: 0
- shadow_error: `None`

## Skill Execution Trace
- executed_skills: requirement_understanding, enterprise_context, formal_retrieval, shadow_retrieval, fallback_assessment, solution_generation
- skill_count: 6
- failed_skill_count: 0
- total_elapsed_ms: 36
- warnings: (none)

## Enterprise Context Providers
- provider_names: crm_context, ticket_context, bi_context, knowledge_context
- provider_success_count: 4
- provider_failed_count: 0
- provider_skipped_count: 0
- provider_warnings: (none)
- context_source: `mcp_mock`
- mock_data: `True`

## Fallback Assessment
- fallback_recommended: `True`
- fallback_reasons: boundary_status_blocked_or_unknown, shadow_detected_parent_child_gap
- human_confirmation_required: `True`
- evidence_completeness: `insufficient`

## Output Summary
- requirement_summary: 一家中型 SaaS 公司想提升销售线索转化和客户成功效率
- pain_point_count: 2
- opportunity_count: 2
- proposed_solution_preview: 建议优先围绕这些已命中的知识主题做方案收敛：客服辅助回复方案说明; 合成服务工单协同案例; 合成零售商品知识治理案例。先做人工确认后的小范围试点，再决定是否扩展。

## Safety Notes
- boundary_status: `no_eligible_method`
- shadow_does_not_affect_formal_answer: `True`
- deterministic_or_llm_mode: `deterministic`
- fallback exists because the formal gate or boundary status may still be blocked.
- provider data is mock data when `mock_data=true`.
