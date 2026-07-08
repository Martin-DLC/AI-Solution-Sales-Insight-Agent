# Agent Skills Design

## Overview

当前项目已经实现一个轻量的 Skills Registry，用来在不引入第三方 Agent 框架的前提下，把 Solution Insight Service 的核心能力组织成项目内 Skills。

这对求职展示很有帮助，因为它说明：

- 现在的 service 已经不是一段“塞满逻辑的脚本”
- 每一段能力都具备明确输入输出边界
- 未来可以自然扩展为更正式的技能编排层

## Current implementation

### RequirementUnderstandingSkill

职责：

- 接收用户需求输入
- 整理行业、规模、目标和约束
- 生成统一的查询上下文

当前输入：

- `user_query`
- `industry`
- `company_size`
- `target_goal`
- `constraints`

当前输出：

- `requirement_summary`
- `normalized_industry`
- `detected_goals`
- `detected_constraints`
- `query`
- `runtime_context`

### FormalRetrievalSkill

职责：

- 调用 formal retriever
- 获取正式 evidence 候选
- 保持 formal retrieval 行为冻结

当前输出：

- `formal_candidates`
- `evidence_items`
- `retrieval_debug`
- `retrieval_error`

### ShadowRetrievalSkill

职责：

- 运行 hierarchical retrieval shadow pipeline
- 观察 document / chunk candidate pool
- 只产出 debug，不进入正式答案

当前输出：

- `shadow_retrieval_debug`
- `shadow_result`

说明：

- disabled 时 `status=skipped`
- failed 时 `status=failed`
- 不影响正式 evidence

### FallbackAssessmentSkill

职责：

- 判断当前证据是否足够
- 识别 retrieval error、boundary risk 和 evidence gap
- 决定是否需要 human confirmation

当前输出：

- `fallback_recommended`
- `fallback_reasons`
- `human_confirmation_required`
- `evidence_completeness`

### SolutionGenerationSkill

职责：

- 把 evidence 和 fallback 结果组织成结构化洞察
- 支持 deterministic mode
- 预留 optional LLM mode

当前输出：

- `requirement_summary`
- `pain_points`
- `ai_opportunity_points`
- `proposed_solution`
- `response_note`

## Skill Registry behavior

当前 registry 支持：

- `register(skill)`
- `get(name)`
- `list_skills()`
- `execute(name, input)`
- `execute_sequence(skill_names, input)`

设计特点：

- skill name 唯一
- 重复注册直接报错
- 单个 skill 异常会被转成 failed `SkillOutput`
- 主 service 不会因为单个 skill 抛异常而直接炸掉

## Service orchestration

当前 `SolutionInsightService.generate_insight()` 已经通过以下顺序编排：

1. `requirement_understanding`
2. `formal_retrieval`
3. `shadow_retrieval`
4. `fallback_assessment`
5. `solution_generation`

最后再由 service 统一 assemble 成原有 `SolutionInsightResponse`。

这保证了：

- CLI / FastAPI 外部输入不变
- 正式输出结构基本不变
- formal retriever 不变
- shadow 仍只进入 debug

## Skill Trace

当前响应里新增了可选 `skill_trace`，包含：

- `executed_skills`
- `skill_count`
- `failed_skill_count`
- `total_elapsed_ms`
- `warnings`

不会包含：

- API key
- traceback
- benchmark gold
- case id

## Why there is no complex Skill Registry yet

当前没有引入复杂第三方 Agent / Skill 框架，原因很现实：

- 当前重点是保持项目可解释、可测试、可演示
- 当前没有大量异构工具调用需要重型编排
- LangChain / CrewAI / AutoGen 会增加依赖和心智负担
- 轻量 registry 已经足够为后续 MCP 扩展留出清晰边界

换句话说，现在的设计是“先把 skill boundary 做清楚，再决定要不要上 registry”。

## MCP preparation direction

如果后续接入 MCP Mock 或真实企业系统，当前 registry 已经可以自然扩展去承接：

- tool invocation
- permission boundary
- structured logging
- retry policy
- graceful degradation
- failure routing

## Current limitations

当前 Skills Registry 仍然是 v0.2 级别：

- 不是完整 Tool Marketplace
- 没有权限系统
- 没有持久化 Skill Memory
- 还没有接 MCP Mock

## Conclusion

现在这个项目已经不是“只有 service 没有 skills 边界”的状态了。它有了一个轻量、可测试、可追踪的 Skills 编排层，同时保持了现有正式输出和评测合同不变。
