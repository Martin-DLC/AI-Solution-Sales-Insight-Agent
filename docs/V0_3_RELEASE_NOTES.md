# v0.3 Release Notes

## v0.3 MVP Summary

v0.3 把仓库从“以实验和评测为主”的原型，推进到了一个更完整的 local-first AI Agent MVP：

- 有正式的 Solution Insight Service
- 有 CLI、FastAPI 和 Web Demo 展示层
- 有 Human Review UI
- 有 Context Provider Interface
- 有 Shadow Retrieval Debug
- 有 Observability Snapshot / Report
- 有 LLM Evaluation Harness 和 Human Evaluation Layer

这仍然不是 production SaaS，但已经具备清晰的产品接口、可运行演示路径和可验证的工程边界。

## Added Web Demo

新增 `GET /demo`，提供浏览器交互式展示页：

- 输入客户需求
- 查看结构化输出
- 展示 evidence、fallback、enterprise context、skill trace 和 shadow debug

Web Demo 只作为展示层，不改变 `/solution-insight` 的后端契约。

## Added Human Review UI

新增 `GET /human-eval` 系列页面，用于：

- 浏览人工评审 case
- 查看待复核输出
- 提交人工判断
- 汇总 review 进度

这让系统不仅能“自动输出”，也能更自然地进入人工确认环节。

## Added Context Provider Interface

新增统一的 enterprise context provider 抽象，用于接入：

- company profile
- CRM context
- ticket context
- BI context
- knowledge context

当前实现仍然是本地 mock，但服务层边界已经清晰。

## Added Observability Report

新增本地只读 observability snapshot / report，用于统一查看：

- formal retrieval path
- shadow retrieval path
- context provider trace
- skill trace
- fallback reasons

这让 demo、排障和结果解释更容易对齐。

## Added Human Evaluation Layer

项目现在同时具备：

- 自动规则评测
- LLM 输出评测
- Human evaluation packet
- Human review UI

自动评测和人工评审被明确区分，避免把未完成的人评伪装成“已经验证过”的质量结论。

## Evaluation Status

当前评测状态需要保持清晰：

- Formal Retrieval Benchmark 已冻结
- formal retriever 尚未通过最终 blocking gate
- boundary blind validation 结果仍为 blocked_with_known_limitations
- deterministic mode 适合本地演示和可复现测试

这些结论对系统可信度很重要，也决定了当前 MVP 的边界。

## Known Limitations

- formal retrieval 结果还不满足最终接入门槛
- hierarchical retrieval 当前只在 shadow/debug 中运行
- 当前没有复杂前端或生产化权限控制
- 当前没有真实企业系统集成
- deterministic mode 不代表最终生产生成质量

## Next Roadmap

下一阶段如果继续推进，优先级通常会放在：

1. 更强的 Web Demo 与可视化观测
2. 更完整的人工复核闭环
3. 更稳定的部署和运行说明
4. 更严格的多模型输出评测
5. 更真实的企业上下文接入
