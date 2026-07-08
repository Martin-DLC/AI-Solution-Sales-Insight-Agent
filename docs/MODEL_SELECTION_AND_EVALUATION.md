# Model Selection and Evaluation

## Overview

这个项目当前默认使用 deterministic mode，不是因为我们认为它比真实 LLM 更强，而是因为它最适合公开 demo、作品集展示和稳定回放。

它有三个现实优势：

- 不依赖 API key
- 输出可复现
- 能把注意力集中在 retrieval、fallback 和结构化服务层，而不是模型波动

## Why deterministic mode is the default

当前默认 deterministic mode，主要是为了控制以下风险：

- 演示时外部模型不可用
- 不同供应商响应格式波动
- 模型幻觉掩盖 retrieval 和 boundary 的真实问题
- 成本和延迟影响面试或本地体验

对这个仓库来说，deterministic mode 的角色更像：

- 一个稳定 demo baseline
- 一个无 key 的本地展示模式
- 一个验证 service / fallback / API 封装的最小闭环

## Optional LLM mode positioning

optional LLM mode 的定位不是“默认生产方案”，而是：

- 为未来真实模型接入预留接口
- 在 formal retrieval 和 fallback 保持不变的前提下，替换最终生成器
- 让项目后续能够做多模型横评

在当前阶段，LLM mode 应该被理解为：

- optional capability
- not the source of truth
- not yet benchmarked end-to-end

## Candidate model pool

当前更合理的候选模型池可以分为两类。

国内主力候选：

- DeepSeek
- Qwen
- GLM
- Doubao

国际参考基线：

- OpenAI
- Claude

这里“参考”的意思不是当前项目已经完成这些模型的正式横评，而是它们适合作为未来模型质量和成本的对照组。

## Evaluation dimensions

未来多模型横评，建议至少覆盖以下维度：

### Structured output stability

- 是否稳定输出目标 JSON
- 是否经常出现字段缺失、类型错误或额外自由文本

### Evidence adherence

- 是否真正基于 formal evidence 回答
- 是否错误引入 shadow debug 或未检索内容

### Hallucination control

- 是否会编造客户事实
- 是否会编造 ROI、预算、项目结果或产品能力

### Fallback trigger quality

- 在证据不足时是否能老实进入 fallback
- 是否错误地“看起来很完整”，但其实越界生成

### Chinese business expression quality

- 中文表达是否自然
- 是否适合售前、咨询和方案场景
- 是否能在保守约束下仍保持可读性

### Cost

- 每次调用成本
- 平均 token 消耗
- 批量评测成本

### Latency

- 单次响应速度
- 在 API 场景下的用户感知延迟

## Evaluation already completed in this project

当前项目已经完成的评测主要集中在 retrieval 和 boundary，而不是多模型生成器横评：

- formal retrieval benchmark v2
- boundary blind validation
- recall experiment

这些评测已经告诉我们：

- formal retriever 当前还没有通过最终 blocking gate
- boundary blind validation 已完成，但 P0 failed
- recall round 2 证明 chunk-only candidate model 不足
- hierarchical parent-first candidate pool 在 candidate recall 上有明确提升

## Evaluation not yet completed

当前仍未完成、但生产前非常重要的评测包括：

- 多模型 LLM 横评
- 人工评分集
- 线上 A/B

也就是说，这个项目现在已经非常适合展示“工程设计、可追溯性和边界意识”，但还不适合宣称“最佳模型已经选定”。

## Practical conclusion

当前结论很明确：

- demo 使用 deterministic mode，是为了保证可复现、可展示、可离线运行
- optional LLM mode 是未来扩展点，不是当前质量背书
- 在进入生产前，必须补充多模型横评、人工评分和线上验证

所以这个项目的价值不在于“已经找到最强模型”，而在于已经把模型选择问题放进了一个可评估、可替换、可审计的工程框架里。
