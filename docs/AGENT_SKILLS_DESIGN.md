# Agent Skills Design

## Overview

当前项目没有实现一个复杂的 Skill Registry，但服务层边界已经足够清晰，完全可以把现有能力抽象成一组可组合的 Agent Skills。

这对求职展示很有帮助，因为它说明：

- 现在的 service 已经不是一段“塞满逻辑的脚本”
- 每一段能力都具备明确输入输出边界
- 未来可以自然扩展为更正式的技能编排层

## Current skill mapping

### Requirement Understanding Skill

职责：

- 接收用户需求输入
- 整理行业、规模、目标和约束
- 生成统一的查询上下文

当前落点：

- `SolutionInsightRequest`
- `SolutionInsightService` 中的 query / runtime context 构造

### Formal Retrieval Skill

职责：

- 调用 formal retriever
- 获取正式 evidence 候选
- 保持 formal retrieval 行为冻结

当前落点：

- `SolutionInsightService`
- formal lexical retriever

### Shadow Retrieval Skill

职责：

- 运行 hierarchical retrieval shadow pipeline
- 观察 document / chunk candidate pool
- 只产出 debug，不进入正式答案

当前落点：

- `ShadowHierarchicalRetrievalService`
- `HIERARCHICAL_RETRIEVAL_MODE=off|shadow`

### Runtime Eligibility Skill

职责：

- 对候选进行运行时资格判断
- 区分 formal path 和 shadow path 中的可用候选
- 保护 solution boundary 和上下文约束

当前落点：

- runtime eligibility filtering
- shadow debug 中的候选状态分析

### Fallback Assessment Skill

职责：

- 判断当前证据是否足够
- 识别 retrieval error、boundary risk 和 evidence gap
- 决定是否需要 human confirmation

当前落点：

- `fallback_recommended`
- `fallback_reasons`
- `human_confirmation_required`

### Solution Insight Generation Skill

职责：

- 把 evidence 和 fallback 结果组织成结构化洞察
- 支持 deterministic mode
- 预留 optional LLM mode

当前落点：

- `SolutionInsightService`
- deterministic generator
- optional LLM wrapper integration

### Citation / Evidence Packaging Skill

职责：

- 组织 evidence items
- 输出 citation label、excerpt 和 evidence completeness
- 保证结构化响应对用户可读

当前落点：

- evidence item assembly
- API / CLI structured response

## Why there is no complex Skill Registry yet

当前没有引入复杂 Skill Registry，原因很现实：

- 当前重点是先把 retrieval、fallback 和 structured output 的闭环跑通
- 当前没有大量异构工具调用要统一编排
- 引入 registry 会增加抽象层，但不会明显提升 demo 价值

换句话说，现在的设计是“先把 skill boundary 做清楚，再决定要不要上 registry”。

## Future Skill Registry direction

如果后续要扩展成更完整的 agent platform，可以增加一个 Skill Registry 来统一管理：

- tool invocation
- permission boundary
- structured logging
- retry policy
- graceful degradation
- failure routing

那时当前这些 skills 就可以自然映射为：

- retrieval skill
- validation skill
- generation skill
- escalation skill
- packaging skill

## Conclusion

当前项目虽然没有显式 Skill Registry，但已经具备了 skill-oriented design 的骨架。

这意味着它不是“一个会说话的 demo”，而是一个已经能拆解为多段职责、并适合未来继续产品化的 Agent service。
