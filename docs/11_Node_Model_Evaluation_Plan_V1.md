# Node Model Evaluation Plan V1

## 1. 为什么需要节点级模型评测

Architecture C 把销售洞察拆成多个节点以后，模型不再只是“会不会聊天”的问题，而是“在每个业务合同上是否稳定遵守”的问题。

节点级评测的意义在于：

- 可以比较不同模型在不同业务判断上的稳定性
- 可以发现某个模型适合快节点，还是更适合推理节点
- 可以为后续模型路由提供客观依据
- 可以避免把整条 Workflow 的失败都归因给“模型不行”

## 2. 当前 DeepSeek 单模型实验的限制

当前 Architecture C 的真实实验主要围绕单一模型进行。

这意味着我们已经能看到：

- 合同约束是否可执行
- 失败能否被准确定位
- Token 和延迟成本大概处于什么水平

但还不能直接得出：

- 哪个模型是最终最优
- 哪个模型适合所有节点
- 哪个模型能自动覆盖所有业务场景

## 3. 为什么不直接对完整 Workflow 同时比较多个模型

如果一开始就把整条 Workflow 全部切成多模型并行比较，会有几个问题：

- 难以判断失败来自哪个节点
- 成本会迅速放大
- 节点之间的差异会被流程噪声淹没
- 结果不适合做清晰的路由决策

因此，v1.1A 先做节点级基础设计，而不是直接上完整多模型 Workflow。

## 4. 四个代表节点的选择原因

本轮先评测四个节点：

- `fact_extraction`
- `underlying_pain`
- `information_gap`
- `solution_recommendation`

选择理由：

- `fact_extraction` 代表证据提取能力
- `underlying_pain` 代表推理与证据约束能力
- `information_gap` 代表业务规则判断能力
- `solution_recommendation` 代表候选边界遵守能力

这四个节点分别对应不同的模型风险类型，适合做第一轮 Pilot。

## 5. 三个 Model Tier 定义

- `fast`：偏低延迟、偏低成本，适合简单节点
- `balanced`：速度与质量均衡，适合中等复杂度节点
- `strong_reasoning`：偏强推理，适合更复杂的业务判断

Model Tier 只表示评测分组，不等于具体厂商模型名。

## 6. 48 次 Pilot 矩阵

本轮 Pilot 矩阵由以下组合构成：

- 4 个节点
- 3 个模型档位
- 每个节点 4 个样本

总计：

```text
4 x 3 x 4 = 48
```

这里我们只定义合同和指标，不执行这 48 次调用。

## 7. 指标定义

评测重点不是单纯看回答好不好，而是看以下合同是否稳定成立：

- JSON 解析是否成功
- Schema 校验是否成功
- 业务规则是否成功
- Evidence 引用是否有效
- Candidate Boundary 是否被遵守
- Blocking Assertion 是否全部通过
- 延迟和 Token 是否可接受

## 8. Blocking Gate

Blocking Assertion 表示“这条样本不允许带着错误进入下一阶段”的硬门槛。

Pilot 阶段的规则是零 Blocking Failure：

- 只要出现 Blocking Failure，就不能认为这个模型在该节点上可路由

## 9. Token 与延迟记录

每次运行都记录：

- `latency_ms`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `estimated_cost`（如可得）

这些指标用于判断模型是否适合某个节点，而不是只看正确率。

## 10. 成本预算原则

本轮评测只做基础可行性验证，不做大规模浪费性试跑。

原则：

- 先定义合同
- 再定义样本
- 再定义指标
- 最后才谈模型路由

## 11. 数据隔离规则

评测必须遵守数据隔离：

- 不读取 Hidden Reference Pack 作为 runtime 输入
- 不读取 `.env`
- 不读取 `data/runtime`
- 不把完整模型输出或客户原文写进 benchmark 合同

## 12. Benchmark 运行后的模型路由产物

Benchmark 结束后，会得到节点级 summary，用来支持后续路由决策，例如：

- 某个节点应优先使用 fast 还是 strong_reasoning
- 某个节点是否满足 pilot 级路由资格
- 某个模型在哪些节点上不应直接上线

## 13. 当前阶段不做什么

本轮不做：

- 不执行真实 API
- 不运行正式 Benchmark
- 不修改现有 Architecture C 业务逻辑
- 不修改 Prompt 迎合单个模型
- 不自动选择 primary model

## 14. v1.1B 与 v1.1C 后续步骤

后续如果继续推进，建议按这个节奏：

1. v1.1B：补全节点级样本和离线断言
2. v1.1C：接入实际模型配置和路由规则

在那之前，先把数据合同、指标计算和评测计划固定下来。

