# Retrieval V1 Failure Analysis

## 1. 分析目标

本次分析只针对已经冻结的 Retrieval v1 结果做离线归因，不重跑正式实验，不覆盖任何 v1 输入、配置或结果文件。分析范围包括：

- `lexical_v1`
- `vector_v1`
- `hybrid_v1`

目标是把失败原因拆成可操作的几类：技术实现问题、Failure Taxonomy 问题、Evaluation 合同问题、Knowledge Base Metadata 问题、Retriever 能力问题，以及 Blocking Gate 问题。

## 2. 冻结实验范围

本次分析基于以下冻结范围：

- 16 条 Retrieval Evaluation Cases
- 20 份合成 Knowledge Documents
- 40 个 Knowledge Chunks
- 6 个 Demo Scope Solutions
- 已冻结的 Lexical / Vector / Hybrid v1 正式结果

本分析不读取 Runtime Embedding 缓存，不加载真实 embedding 模型，不访问网络。

## 3. 三方法原始结果

### Lexical v1

- `recall_at_1 = 0.25`
- `recall_at_3 = 0.703125`
- `recall_at_5 = 0.921875`
- `precision_at_3 = 0.9375`
- `precision_at_5 = 0.796875`
- `mean_reciprocal_rank = 1.0`
- `forbidden_hit_rate = 0.0`
- `solution_boundary_violation_rate = 0.4375`
- `eligible_for_rag = false`

### Vector v1

- `recall_at_1 = 0.234375`
- `recall_at_3 = 0.71875`
- `recall_at_5 = 0.90625`
- `precision_at_3 = 0.9583333333333334`
- `precision_at_5 = 0.775`
- `mean_reciprocal_rank = 0.96875`
- `forbidden_hit_rate = 0.0625`
- `solution_boundary_violation_rate = 0.625`
- `eligible_for_rag = false`

### Hybrid v1

- `recall_at_1 = 0.25`
- `recall_at_3 = 0.71875`
- `recall_at_5 = 0.90625`
- `precision_at_3 = 0.9583333333333334`
- `precision_at_5 = 0.775`
- `mean_reciprocal_rank = 1.0`
- `forbidden_hit_rate = 0.0`
- `solution_boundary_violation_rate = 0.5`
- `eligible_for_rag = false`

## 4. 为什么当前不能直接接入 Architecture C

`retrieval_method_comparison.v1.json` 的冻结结论仍然成立：

- `selected_method = null`
- `selection_status = "no_eligible_method"`

这不是因为某个方法“完全不可用”，而是因为当前 v1 基准下没有任何方法同时满足：

- `recall_at_5 == 1.0`
- `forbidden_hit_rate == 0`
- `solution_boundary_violation_rate == 0`
- 全部 case 通过 blocking gate

在 v2 之前，不应把当前 Retrieval v1 直接接入 Architecture C。

## 5. `empty_query_tokens` 根因

这是本轮发现的最明确技术问题。

- `empty_query_tokens` 由通用 runner 中的 `not retrieval_debug.get("query_tokens")` 触发
- `query_tokens` 实际上是 Lexical Retriever 的 debug 字段
- Vector Retriever 的 debug 只包含过滤后候选数和耗时，不提供 `query_tokens`
- Hybrid Retriever 同样不保证提供该字段

因此：

- 16 条 Vector cases 全部被标记了 `empty_query_tokens`
- 16 条 Hybrid cases 全部被标记了 `empty_query_tokens`
- 但 16 条原始 query 没有一条为空
- Vector 和 Hybrid 两者都成功返回了候选

这说明：

- 这不是“空 query”
- 这不是“没有候选”
- 这是 **Failure Taxonomy 误分类**

## 6. Counterfactual 结果

本次做了一个严格受限的 Counterfactual 诊断：

- 不修改正式结果
- 不修改排名
- 不修改分数
- 不修改 summary 指标
- 仅在分析中排除 `empty_query_tokens`

结论：

### Vector

- 去掉 `empty_query_tokens` 后，仍失败的 case 还有 10 条：
  - `RET-001`
  - `RET-002`
  - `RET-003`
  - `RET-004`
  - `RET-005`
  - `RET-006`
  - `RET-009`
  - `RET-012`
  - `RET-013`
  - `RET-015`
- 剩余真实失败原因：
  - `solution_boundary_violation`
  - `forbidden_document_hit`

### Hybrid

- 去掉 `empty_query_tokens` 后，仍失败的 case 还有 8 条：
  - `RET-001`
  - `RET-002`
  - `RET-003`
  - `RET-004`
  - `RET-005`
  - `RET-006`
  - `RET-009`
  - `RET-012`
- 剩余真实失败原因：
  - `solution_boundary_violation`

因此，`empty_query_tokens` 虽然是错误标签，但它不是导致 `selected_method = null` 的唯一原因。Counterfactual 不是正式结果，只是帮助我们定位误分类影响范围。

## 7. Boundary Violation 分类

本轮没有把全部 boundary 失败都直接归为检索能力差，而是拆成多类原因：

- `cross_solution_retrieval`
- `multi_solution_document_overlap`
- `expected_document_contains_forbidden_solution`
- `operational_filter_gap`
- `gold_boundary_overconstraint`

当前最常见的模式有两个：

1. 多 solution 文档本身进入候选，天然带来跨 solution 暴露  
2. Gold 期望文档自身就含有 forbidden 或 out-of-required 的 solution metadata

也就是说，Boundary Violation 不是单一问题，而是：

- 检索排序
- 文档 metadata 粒度
- case 过滤表达能力
- expected relevant 合同

一起造成的。

## 8. 每种方法的真实 Retriever 失败

### Lexical

Lexical 没有 `empty_query_tokens` 误分类，也没有 forbidden hit。它的主要问题是：

- 多 solution 文档被 lexical overlap 命中后，较容易触发 boundary violation
- 在若干 case 上，虽然首个 relevant 结果能排到第一，但 top-5 不足以覆盖全部 expected relevant items

### Vector

Vector 的真实问题包括：

- Boundary Violation 最多
- 出现了唯一一次 `forbidden_document_hit`（`RET-013`）
- 在若干 case 上 Recall@5 不足

### Hybrid

Hybrid 比 Vector 少了一次 forbidden hit，但没有真正消除 boundary 问题。它在 v1 下仍然无法通过 gate。

## 9. Case 可达性分析

最重要的可达性结论：

- `RET-006`
- `RET-009`

这两条 case 在当前 v1 数据合同下是 **benchmark_case_infeasible**

原因是：

- expected relevant items 本身就与 boundary 合同冲突
- `safe_expected_item_count < minimum_relevant_hits`

更直白地说：  
这两条 case 在当前 v1 数据和 boundary 定义下，即使 retriever 排得“再好”，也不可能同时满足：

- 命中足够多的 expected relevant items
- 又保持 zero boundary violation

另外还有三条 case：

- `RET-001`
- `RET-002`
- `RET-005`

虽然仍可达，但 expected relevant 中已经带着 boundary 冲突信号，属于高风险合同。

## 10. Knowledge Metadata 问题

当前 20 份 Knowledge Documents 的 solution 绑定分布是：

- 单 solution：6
- 双 solution：10
- 三 solution：3
- 六 solution：1

也就是说：

- 14 / 20 文档是多 solution 文档

其中需要特别关注：

- `KB-COM-001` 绑定了全部 6 个 demo solutions
- `KB-UNS-001`、`KB-READY-002`、`KB-CAP-002` 等文档也绑定了 3 个 solution

同时，当前 chunk 完全继承 document 级 solution scope。  
这会导致：

- 只要一个 document 绑定过宽
- 它的所有 chunk 都继承同样宽的 solution_ids
- boundary 评测就会非常敏感

## 11. Evaluation Contract 问题

当前 v1 有一类很明显的合同冲突：

- `RET-001`
- `RET-002`
- `RET-005`
- `RET-006`
- `RET-009`

这些 case 的 expected relevant items 中，已经包含了 forbidden 或 out-of-required 的 solution metadata。

因此当前 v1 同时混合了两种语义：

1. “这个文档/块是相关的”
2. “这个候选不能带其他 solution metadata”

当多 solution 文档被允许进入 Gold 时，这两条语义会互相打架。

## 12. Retriever 能力问题

不能把全部失败都甩给数据合同。Retriever 也确实有自己的能力问题：

- Vector 在 `RET-013` 上出现 forbidden hit
- Lexical / Vector / Hybrid 各自都有 top-5 覆盖不足的 case
- Vector 和 Hybrid 没有有效降低 boundary violation

所以 v2 不能只修合同，也需要重新评估 retriever 方法本身。

## 13. Blocking Gate 问题

本轮结论不是“应该放宽 gate”。

相反，当前判断是：

- v1 gate 和冻结 v1 结果之间是自洽的
- 问题不在于 gate 过严
- 问题在于：
  - taxonomy 有误分类
  - metadata 粒度过粗
  - case / gold 合同有冲突
  - retriever 也还有真实不足

因此，不能为了让某个方法通过而直接删除 forbidden 或 boundary 规则。

## 14. 哪些问题属于技术 Bug

明确属于技术 Bug 的有：

- 用 Lexical 专属 `query_tokens` debug 字段去判 Vector / Hybrid 的空 query 失败

这类问题应在 v2 中修复，但不回写 v1 正式结果。

## 15. 哪些问题需要 v2 数据版本

需要通过 v2 数据版本解决的有：

- Document 级 `solution_ids` 过宽
- Chunk 继承 Document 全量 solution scope
- 缺少：
  - `primary_solution_id`
  - `applicable_solution_ids`
  - `excluded_solution_ids`
  - `chunk-level solution scope`
  - `scope_type`

这些都不应直接修改 v1 知识库，而应创建新的 v2 数据版本。

## 16. 哪些问题需要 v2 评测版本

需要通过 v2 Evaluation 合同解决的有：

- boundary 判定需要区分 candidate 违规与 expected relevant 合同冲突
- 需要在正式实验前先做 case infeasibility 审计
- 需要把 Gold 与 boundary 语义关系说清楚

同样，这不应覆盖 v1 cases，而应建立新的 v2 评测集。

## 17. 哪些问题需要 v2 Retriever 版本

需要通过 v2 Retriever 实验验证的有：

- 修复 taxonomy 后，Vector / Hybrid 的真实 failure profile
- 在更细粒度 metadata 下，Vector / Hybrid 是否还能出现大量 boundary violation
- forbidden hit 是否仍然存在

## 18. v2 实验优先级

建议优先级：

1. 修复技术 Bug：去掉 `empty_query_tokens` 的误分类
2. 建立 v2 metadata：chunk 级 solution scope
3. 建立 v2 evaluation：显式 infeasibility 审计
4. 再做 Retriever v2 正式实验
5. 只有当 v2 中出现 `eligible_for_rag = true` 的方法，才允许考虑接入 Architecture C

## 19. 明确不修改 v1 结果

本分析不会：

- 覆盖任何 v1 正式结果文件
- 重跑正式 Vector / Hybrid 实验
- 修改 v1 配置
- 修改 v1 knowledge base
- 修改 v1 retrieval cases

v1 结果继续保持冻结、可审计、可复现。

## 20. Architecture C 接入条件

在当前 v1 下：

- `selected_method = null`
- `selection_status = no_eligible_method`

所以当前不应把 Retrieval v1 接入 Architecture C。

只有在 v2 中满足以下条件后，才允许进入接入评估：

- 使用 versioned v2 数据与评测集
- 消除 taxonomy 误分类
- 解决 infeasible case 和 metadata 粒度问题
- 至少有一个 retrieval 方法在 v2 下达到 `eligible_for_rag = true`
