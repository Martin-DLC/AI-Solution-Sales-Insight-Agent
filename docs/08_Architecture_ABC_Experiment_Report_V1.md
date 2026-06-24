# Architecture A/B/C 实验总结报告 V1

## 1. 实验目标

本轮实验的目标，是比较三种销售洞察实现路径在真实业务输入上的表现：

- Architecture A：普通单 Prompt 文本输出
- Architecture B：高质量单 Prompt 结构化输出
- Architecture C：节点式 Workflow + 纯代码校验 + 人工复核

核心关注点不是“谁更会说”，而是：

- 谁能更稳定地遵守业务合同
- 谁能更清楚地隔离错误
- 谁更适合进入真实销售分析闭环

## 2. 实验边界

本报告只使用已经冻结的真实实验事实，不补写新结论，不推断未记录的数据。

固定边界如下：

- 同一项目代码库
- 同一组 DEV-01 / DEV-04 / DEV-05 输入案例
- Architecture A 不使用完整 SalesInsightReport Schema
- Architecture B 使用完整 SalesInsightReport Schema
- Architecture C 使用节点化 Workflow、节点级 Pydantic 校验与纯代码收口
- 不使用 RAG
- 不使用多 Agent
- 不使用自动修复
- 不使用自动重试
- 不把 Hidden Reference Pack 暴露给运行时主流程

## 3. 三种 Architecture 定义

### Architecture A

Architecture A 是最朴素的单 Prompt 文本方案：一次 LLM 调用直接生成普通文本结果，不强制完整结构化报告。

### Architecture B

Architecture B 是高质量单 Prompt 结构化方案：一次 LLM JSON 调用直接生成完整 `SalesInsightReport`，然后由 Schema 做整体校验。

### Architecture C

Architecture C 是节点式 Workflow：把销售分析拆成多个可验证节点，每个节点独立 Prompt、独立输出模型、独立失败定位，最终再由纯代码 Report Composer 和 Final Validation 收口。

## 4. Architecture A 结果

Architecture A 的真实实验结果体现了它“快、便宜、但约束弱”的特征。

| 项目 | 结果 |
|---|---|
| 运行次数 | 2 次 live run |
| 输出形态 | 普通文本 |
| 是否强制完整业务 Schema | 否 |
| 典型延迟 | 约 27.1s、37.1s |
| 典型总 Token | 约 4,003、4,028 |

优点：

- 延迟低
- Token 成本低
- 结构简单，最容易启动

限制：

- 不保证完整结构化报告
- 不强制 fact / inference / assumption 等分类
- 不强制 Stakeholder、Solution、Action 的合同
- 很难靠文本本身发现业务错误
- 可观察性弱，后续分析成本高

结论：A 适合最早期的轻量探索，不适合作为企业级正式输出链路。

## 5. Architecture B 结果

Architecture B 证明了一件重要的事：**更强的 Prompt 合同能显著减少错误，但一次性大报告仍然不稳定。**

### 5.1 v1

- 出现 2 次 JSON Parse Failure
- 有 1 次 JSON 成功，但仍产生 12 项 Schema 错误

### 5.2 v2

- JSON 解析成功
- Schema 错误降到 5 项

### 5.3 v3

- JSON 解析成功
- Schema 错误降到 2 项
- 剩余错误都集中在同一类：`confirmed=false` 的 Stakeholder 缺少 `next_validation`

| 项目 | 结果 |
|---|---|
| 输出形态 | 一次性 JSON |
| 解析结果 | 从失败逐步收敛到成功 |
| Schema 结果 | 从 12 项错误收敛到 2 项 |
| 典型 Token | 约 19,859 - 25,937 |
| 典型延迟 | 约 79.7s - 147.6s |

结论：

- Prompt 合同强化是有效的
- 但“JSON 合法”不等于“业务合同合法”
- 一次性输出超大结构化报告仍然会把错误压缩到最后阶段，定位粒度不够细
- 成本明显高于 A

## 6. Architecture C 结果

Architecture C 把复杂大报告拆成节点级 Workflow，实验中最大的价值不是“更会生成”，而是“更会暴露问题在哪里”。

### 6.1 真实运行路径摘要

#### DEV-01 首次运行

- LLM 调用：7 次
- 延迟：151,534 ms
- Prompt tokens：48,636
- Completion tokens：14,968
- Total tokens：63,604
- 最后成功节点：Stakeholder
- 失败节点：Information Gap
- 失败原因：业务规则不足，缺少 authority 或 decision_process 类信息
- 结果：没有 `report_draft`，也没有 `final_report`

#### DEV-04 首次运行

- LLM 调用：3 次
- 延迟：68,120 ms
- Prompt tokens：15,959
- Completion tokens：7,920
- Total tokens：23,879
- 最后成功节点：Explicit Need
- 失败节点：Underlying Pain
- 失败原因：`source_id="business_rule"` 不在 Source Index
- 结果：没有 `report_draft`，也没有 `final_report`

#### DEV-05 首次运行

- LLM 调用：1 次
- 延迟：21,009 ms
- Prompt tokens：3,502
- Completion tokens：2,415
- Total tokens：5,917
- 失败节点：Fact Extraction
- 失败原因：`evidence_summary="诊断风险"` 长度不足 5 个字符
- 结果：没有 `report_draft`，也没有 `final_report`

### 6.2 Evidence 合同最小修复后的变化

在 Evidence Prompt 合同补强后，DEV-04 与 DEV-05 的证据类错误被定位并收敛，Workflow 得以继续向后执行；但新的限制又在下游节点暴露出来。

#### DEV-05 v2 运行

- LLM 调用：9 次
- 延迟：164,833 ms
- Prompt tokens：63,196
- Completion tokens：17,886
- Total tokens：81,082
- 9 个 LLM 节点已完成
- 失败节点：Solution Recommendation
- 失败原因：推荐结果越出了已检索候选边界
- 结果：没有 `report_draft`，也没有 `final_report`

### 6.3 Architecture C 的阶段性判断

- 节点级 Guardrail 明显提升了错误定位能力
- 证据引用错误、下游候选边界错误、业务规则错误被拆开识别
- 但真实运行下，C 还没有形成稳定可直接发布的 Final Report
- C 的 token / latency 成本显著高于 A

结论：C 更适合企业级可控分析链路，而不是单纯追求一次性“出大报告”

## 7. Failure Taxonomy

| 失败类别 | 含义 | 在本项目中是否观察到 |
|---|---|---|
| JSON Parse Failure | 模型返回不是合法 JSON | 是，B v1 观察到 |
| Schema Validation Failure | JSON 合法但不满足输出模型 | 是，B v1/v2/v3 观察到 |
| Evidence Reference Failure | 证据 ID 或摘要不合法 | 是，C 的真实运行观察到 |
| Cross-Node Business Rule Failure | 节点间业务规则不一致 | 是，C 的 Stakeholder / Information Gap 约束中观察到 |
| Candidate Boundary Failure | 结果超出检索候选或方案边界 | 是，C 的 Solution Recommendation 观察到 |
| Final Validation Failure | 全链路输出通过但最终交叉校验失败 | 本次记录中未观察到 |
| API / Network Failure | 调用层、网络或鉴权失败 | 本次记录中未观察到 |

补充说明：

- `evidence_summary` 过短
- `source_id` 不在 Source Index
- `confirmed=false` 的 Stakeholder 缺少 `next_validation`
- Solution Recommendation 超出候选边界

这些都说明：Architecture C 的价值，不只是“把错误拦住”，更是“把错误分到更具体的位置”。

## 8. A/B/C 指标对比

| 维度 | Architecture A | Architecture B | Architecture C |
|---|---|---|---|
| 输出形态 | 文本 | 单次 JSON | 节点式 Workflow |
| 结构化程度 | 低 | 高 | 高 |
| 错误定位 | 弱 | 中 | 强 |
| 实验稳定性 | 较高，但约束弱 | 中等 | 当前仍在收敛 |
| Token 成本 | 最低 | 较高 | 最高 |
| Latency | 最低 | 较高 | 较高 |
| 业务可控性 | 弱 | 中 | 强 |
| 可审计性 | 弱 | 中 | 强 |

## 9. 关键工程结论

1. Architecture A 最快、最省，但不够严
2. Architecture B 说明 Prompt 契约有用，但一次性大报告仍会把复杂错误留到最后
3. Architecture C 显著提升了错误隔离和业务约束能力
4. Architecture C 目前仍没有稳定的 live Final Report
5. Architecture C 的成本高，不能把所有节点都无限堆成大模型调用
6. 企业级路线的关键不是“更多 Agent”，而是更清晰的合同、更细的失败定位和更稳的运行边界

## 10. 当前限制

- Development 数据集只有 3 条
- 真实运行主要围绕 DEV-01、DEV-04、DEV-05 展开
- 目前还不能据此宣称完整商业 ROI
- 仍缺少更大规模、更多样输入上的稳定性验证
- 现阶段的结论更适合描述为“工程可用性验证”，不是“生产效果定论”

## 11. 生产优化方向

Architecture C 的下一步优化重点不是继续堆复杂度，而是压成本、提稳定：

- 减少重复上下文
- 简单字段优先用规则或轻量模型
- 让 Context Sufficiency 更积极地提前截断
- 压缩证据文本和候选上下文
- 对稳定中间结果做缓存
- 按节点路由模型能力，而不是所有节点都用同一级别模型

不建议在 MVP 阶段加入：

- Critic
- 多 Agent 协作
- 自动修复
- 向量 RAG 作为主链路

## 12. 求职展示价值

这组实验对外展示的价值，不是“我做了一个很大的 LLM 系统”，而是：

- 我能把企业销售分析拆成可审计的合同
- 我能把幻觉和业务错误定位到具体节点
- 我能把 Prompt、Schema、Workflow、Runtime 留痕组织成一条可追踪链路
- 我能比较不同架构的成本、稳定性和可解释性

这比单纯展示一个“能聊天”的系统，更接近真实企业场景里的工程能力。
