# Architecture Overview

## Overview

这个仓库的产品化路径可以分成两条：

1. 正式主链路：输入 -> 检索 -> 证据 -> fallback -> 结构化输出
2. Shadow 旁路：输入 -> hierarchical retrieval debug -> 仅供诊断
3. Web Demo 展示层：输入表单 -> `/solution-insight` -> 结果卡片，不改变 service / retrieval / evaluation 主链路

可维护的 Mermaid 图源文件见 [architecture_diagram.mmd](architecture_diagram.mmd)。

## Main Flow

```mermaid
flowchart LR
    U[User Input] --> A[FastAPI / CLI / Web Demo]
    A --> B[Solution Insight Service]
    B --> C[Formal Retriever]
    C --> D[Evidence Items]
    D --> E[Fallback Assessor]
    E --> F[Deterministic / LLM Generator]
    F --> G[Structured Output]
    G --> M[Observation Snapshot / Report]
```

## Shadow Flow

```mermaid
flowchart LR
    B[Solution Insight Service] -.-> H[Shadow Hierarchical Retrieval]
    H -.-> I[Runtime Eligibility]
    H -.-> J[Context Preview]
    H -.-> K[Citation Preview]
    H -.-> L[Shadow Debug]
```

## Design Principles

### Formal path stays frozen

- 正式 retriever 的默认行为不变
- formal evidence 仍然来自同一套冻结结果和运行时过滤
- 任何 shadow / debug 都不应改写正式 answer

### Shadow is diagnostic only

- `HIERARCHICAL_RETRIEVAL_MODE=off` 时完全关闭
- `HIERARCHICAL_RETRIEVAL_MODE=shadow` 时只输出 debug
- shadow 不参与正式 response 的 evidence 选择

### Fallback protects the boundary

fallback 不是“失败就硬继续”，而是：

- 证据不足时提醒人工确认
- 检索错误时不伪造结论
- 边界不清时不冒充可信答案

## Why this architecture works for demos

- CLI 可以快速演示
- FastAPI 可以给出最小 HTTP 入口
- Web Demo 让面试或录屏时更容易展示结构化结果，不影响后端契约
- formal benchmark 结果仍然冻结可追溯
- shadow 让我们可以展示技术深度，但不会污染正式结论
- Observability Snapshot 位于正式输出之后，不影响主链路，只负责可展示、可排障的只读观测
