# Project Walkthrough

## 1. Problem

AI 解决方案售前和咨询类场景里，最难的部分通常不是“生成一份看起来不错的答案”，而是：

- 它是否基于真实证据
- 它是否越过了方案边界
- 它是否在证据不足时依然伪装成确定答案

这个项目尝试把这些风险显式工程化。

## 2. Agent Workflow

当前主链路可以概括为：

1. 接收用户需求和可选企业上下文
2. 运行 formal retriever 获取正式证据
3. 评估证据完整性和边界风险
4. 进入 deterministic / optional LLM generation
5. 输出结构化 AI solution insight
6. 在需要时建议人工确认

## 3. Retrieval Design

项目把 retriever 设计分成两层：

### Formal Retriever

- 用于正式 evidence
- 受冻结 benchmark 和运行时过滤约束
- 保持结果口径稳定

### Shadow Hierarchical Retrieval

- 只做诊断
- 不进入正式 answer
- 用于观察 candidate pool、context preview 和 citation preview

## 4. Skills Registry

项目内部没有上复杂 Agent orchestration framework，而是采用轻量 Skills Registry，把服务拆成几个清晰职责：

- requirement understanding
- enterprise context
- formal retrieval
- shadow retrieval
- fallback assessment
- solution generation

这样既能保留工程边界，也便于生成 skill trace。

## 5. Context Provider Interface

Context Provider Interface 负责把 demo 企业上下文统一成一套可插拔接口，包括：

- company profile
- CRM context
- ticket context
- BI context
- knowledge context

当前实现是本地 mock，但接口已经具备向真实企业系统演进的形状。

## 6. Shadow Retrieval

Shadow retrieval 的核心原则很简单：

- 可以运行
- 可以观察
- 不能污染正式结果

因此它只影响 debug 区域，不进入正式 evidence，也不改写正式 prompt。

## 7. Fallback / Human Confirmation

fallback 是系统的一个重要安全边界：

- 当证据不足时，不强行生成确定答案
- 当检索异常时，不伪造事实
- 当边界不清时，主动要求人工确认

这个机制保证了系统在“不会答”时也有合理行为。

## 8. Evaluation

项目当前的评测体系包括：

- Formal Retrieval Benchmark v2
- Retrieval failure diagnosis
- Candidate recall experiments
- LLM evaluation harness
- Human evaluation packet

重要结论是：当前 formal retriever 还没有通过最终 blocking gate，因此整个系统仍然要保留 fallback 和人工确认。

## 9. Observability

Observability 层用于把单次请求中的：

- retrieval path
- context provider trace
- skill trace
- fallback reasons
- shadow diagnostics

整理成易于查看的 snapshot 和 report。

这有助于本地调试、录屏和结果解释。

## 10. Human Review

Human Review UI 提供一个最小人工复核入口，让系统不只是“自动输出”，也能进入更真实的 review workflow。

它可以用于：

- 浏览 case
- 查看结果
- 提交人工意见
- 汇总 review 状态

## 11. Web Demo

Web Demo 是当前 MVP 的展示层：

- 左侧输入业务场景
- 右侧展示结构化结果
- 支持查看 evidence、fallback、enterprise context、skill trace 和 shadow debug

它复用现有 `/solution-insight` API，不改变后端契约。

## 12. Limitations

当前已知限制包括：

- formal retriever 尚未通过最终 blocking gate
- hierarchical retrieval 仍然只在 shadow 模式下运行
- deterministic mode 更偏向可复现演示
- 当前没有生产级鉴权、权限控制和复杂前端

## 13. Future Work

后续如果继续推进，比较自然的方向包括：

- 更强的人工复核闭环
- 更严格的多模型输出评测
- 更真实的企业系统接入
- 更完善的观测和部署方案
