# Retrieval Benchmark V2 Design

## 1. 为什么需要 Benchmark v2

Retrieval v1 已经成功冻结了三种方法的正式结果：

- `lexical_v1`
- `vector_v1`
- `hybrid_v1`

这批结果仍然有效，因为它们忠实记录了当时的数据、知识库、Boundary 规则和 Blocking Gate 组合下的真实表现。但 v1 的失败归因分析同时证明，当前基准中混杂了三类不同问题：

1. Failure Taxonomy 的技术误分类；
2. Knowledge Metadata 过宽导致的 Solution Boundary 歧义；
3. Retrieval Evaluation Case 自身不可达的约束冲突。

因此，v2 的第一目标不是立刻换 Retriever，而是先把合同、数据语义和可达性校验建立清楚。

## 2. v1 中发现的问题

### 2.1 `empty_query_tokens` 误分类

v1 使用了 Lexical 专属的 `query_tokens` Debug 字段判断 Query 是否为空。  
这会让 `vector_v1` 和 `hybrid_v1` 在 Query 实际非空时，也因为没有提供 Lexical Debug 字段而被误标为 `empty_query_tokens`。

### 2.2 Knowledge Metadata 范围过宽

v1 中有 14 份 multi-solution 文档。  
其中 `KB-COM-001` 还覆盖了全部 6 个 Demo Solutions。  
Chunk 默认完全继承 Document 级 `solution_ids`，无法表达“文档广、片段窄”的真实适用范围。

### 2.3 Benchmark Case 可达性缺陷

`RET-006` 和 `RET-009` 在 v1 合同下不可达：

- Expected Relevant 项本身与 Forbidden Scope 冲突；
- `safe_expected_item_count < minimum_relevant_hits`；
- 这种 Case 不应该进入正式 Benchmark。

## 3. v1 结果为何仍然有效

v1 结果仍然是有效的冻结审计产物，因为它们回答的是：

> 在 v1 数据合同和 v1 基准语义下，这三种方法的正式表现是什么？

因此：

- 不修改任何 v1 文件；
- 不改变 v1 `--check` 行为；
- 不回写 v1 结果；
- 不用 v2 逻辑反向覆盖 v1 结论。

## 4. v1 Legacy 与 v2 Method-Aware 隔离

v2 显式保留两套语义：

- `v1_legacy`
- `v2_method_aware`

`v1_legacy` 用于：

- 重现冻结结果；
- 保持 Hash 稳定；
- 维持现有正式实验可审计。

`v2_method_aware` 用于：

- 新 Failure Taxonomy；
- 新 Knowledge Scope；
- 新 Boundary Evaluation；
- 新 Feasibility Gate；
- 后续 v2 正式重跑。

## 5. Failure Taxonomy v2

v2 采用 method-aware 失败分类器，至少支持：

- `empty_query`
- `no_relevant_hit_at_5`
- `insufficient_relevant_hits`
- `forbidden_document_hit`
- `solution_boundary_violation`
- `operational_filter_excluded_all`
- `retrieval_error`
- `missing_required_debug`

### v2 如何修复 `empty_query_tokens`

v2 中只有以下情况才允许标记为空 Query：

1. 原始 `query` 为空；
2. 原始 `query` 只有空白；
3. 经过通用 Unicode 规范化后为空。

以下条件 **不得** 推断 Query 为空：

- `query_tokens` 缺失；
- `query_tokens=[]`；
- `matched_terms=[]`；
- Vector Candidate 没有 `matched_terms`；
- Hybrid Debug 不包含 Lexical 专属字段。

## 6. 通用与方法专属 Debug 合同

### 通用字段

- `raw_query_present`
- `normalized_query_present`
- `candidate_count`
- `retrieval_method`

### Lexical 专属字段

- `lexical_query_tokens`
- `lexical_matched_terms`

### Vector 专属字段

- `query_embedding_generated`
- `embedding_dimension`

### Hybrid 专属字段

- `lexical_candidate_count`
- `vector_candidate_count`
- `fused_candidate_count`

Runner 不得再要求所有方法都提供 Lexical 专属 Debug 字段。

## 7. Knowledge Scope v2

v2 在 Document 和 Chunk 层都引入独立 Scope 字段：

- `primary_solution_id`
- `applicable_solution_ids`
- `excluded_solution_ids`
- `scope_type`
- `scope_notes`

其中 `scope_type` 支持：

- `solution_specific`
- `multi_solution`
- `global_policy`
- `cross_cutting_requirement`

## 8. Document 与 Chunk 级 Scope

v2 允许 Chunk 比 Document 更窄，但不允许更宽：

- Chunk 可以收窄 `applicable_solution_ids`
- Chunk 必须保留 Document 的 `excluded_solution_ids`
- Chunk 不得扩展到 Document 未授权的 Solution

这正是为了解决 v1 中 Chunk 机械继承 Document 范围的问题。

### 完整载荷合同

v2 的 `KnowledgeDocumentV2` 和 `KnowledgeChunkV2` 必须承载完整的业务载荷，而不只是 Scope 元数据。

这意味着：

- `documents.v2.jsonl` 保留 v1 的标题、摘要、正文、来源、状态、日期、标签、行业等业务字段；
- `chunks.v2.jsonl` 保留 v1 的 chunk 正文、chunk_index、citation_label、metadata 等业务字段；
- v2 正式对象继续使用 `extra="forbid"`；
- 但不再把 v1 的 legacy `solution_ids` 作为正式边界真源持久化到 v2 对象中。

因此，v2 采用“完整业务载荷 + 新 Scope 真源”的平面结构，而不是“继承 v1 并继续暴露 legacy scope”。

### Legacy Scope 处理

v1 中的 `solution_ids` 仍然是迁移输入的重要参考，但它在 v2 中只用于：

- `from_v1(...)` 转换输入；
- `solution_scope_migration.v2.json` 审计记录；
- 投影一致性和内容对比的迁移上下文。

它**不是** v2 正式 Boundary 的真源。

v2 正式 Boundary 只由以下字段表达：

- `primary_solution_id`
- `applicable_solution_ids`
- `excluded_solution_ids`
- `scope_type`
- `scope_notes`

## 9. Global Policy 语义

`global_policy` 用于表达全局约束、商业规则或跨 Solution 通用政策。

它的关键规则是：

- 允许 `applicable_solution_ids` 覆盖全部 6 个 Demo Solutions；
- 这本身 **不自动构成** Boundary Violation；
- 只有以下情况才违规：
  - Candidate 命中 `excluded_solution_ids`
  - Candidate 命中 Case 明确禁止的 Document

## 10. Runtime Context 与 Gold 隔离

v2 显式区分两类信息：

### Runtime 可见上下文

- `operational_filters`
- `operational_solution_scope`
- `allowed_document_types`
- `industries`
- `tags`
- `effective_on`

### Evaluation-only Gold

- `expected_relevant_document_ids`
- `expected_relevant_chunk_ids`
- `forbidden_document_ids`
- `forbidden_solution_ids`
- `minimum_relevant_hits`

Gold 不得传给 Retriever。  
特别是不得从 `forbidden_solution_ids` 反推运行时过滤条件。

## 11. Boundary Evaluation v2

v2 将 Boundary 语义拆成三层：

### Candidate 级

根据 Chunk 级 Scope 判断：

- 是否命中 Case 禁止 Document；
- 是否超出 Runtime `operational_solution_scope`；
- 是否触发 Candidate 自身 `excluded_solution_ids`。

### Case 级

对 Top-K 中 Candidate 级违规进行聚合。

### Benchmark 级

如果 Expected Relevant 本身违反 Boundary，则不计为 Retriever 失败，而是在正式运行前由 Feasibility Gate 拦下。

## 12. Feasibility Gate

v2 在正式 Benchmark 前必须执行可达性校验。至少检查：

- Expected IDs 存在；
- Expected 文档 Active；
- 日期有效；
- Operational Filters 不排除 Expected；
- Expected 自身不违反 Boundary；
- `minimum_relevant_hits` 可满足；
- Expected 与 Forbidden 不存在隐性 Metadata 冲突。

只有通过 Feasibility Gate 的 Case 才能进入正式 v2 Benchmark。

## 13. RET-006 和 RET-009 如何在迁移阶段处理

这两个 Case 在迁移阶段必须被标记为“重写合同”，而不是保留后重跑。

原因：

- Expected Relevant 与 Forbidden Scope 冲突；
- `safe_expected_item_count = 0`；
- 继续保留只会让正式实验混入不可达样本。

迁移建议：

- 重写 Gold；
- 重新确认 Runtime Operational Scope；
- 让 Expected Relevant 与 Boundary 合同一致。

## 14. KB-COM-001 如何重新表达

`KB-COM-001` 不应继续用 v1 那种“覆盖全部 Solution 的宽 `solution_ids`”方式表达。

迁移建议：

- 在 v2 中显式改写为 `global_policy`；
- 保留对全部 Demo Solution 的适用性；
- 如某些 Chunk 只约束部分 Solution，则在 Chunk 层收窄 Scope；
- 不再把“覆盖多 Solution”直接等价为 Boundary 风险。

## 15. v2 数据文件规划

本轮只生成迁移计划，不生成正式 v2 数据。后续必须新建：

- `data/knowledge_base/documents.v2.jsonl`
- `data/knowledge_base/chunks.v2.jsonl`
- `data/knowledge_base/manifest.v2.json`
- `data/evaluation/retrieval/retrieval_cases.v2.jsonl`
- `data/evaluation/retrieval/retrieval_benchmark_config.v2.json`
- 各 Retriever 的 v2 结果文件

不得覆盖任何 v1 文件。

## 16. 后续实验纪律

v2 进入正式实验前必须满足：

1. v2 数据文件创建完成；
2. 所有 v2 Case 通过 Feasibility Gate；
3. 原 Lexical / Vector / Hybrid 算法先原样重跑；
4. 只有原算法仍不合格，才进入 Retriever v2。

## 17. 为什么暂时不修改 Retriever 算法

当前主要问题还不是算法本身：

- Failure Taxonomy 有技术误分类；
- Knowledge Metadata 过宽；
- Case 合同存在不可达样本。

如果在这些问题未修正前就升级 Retriever，会把算法改动和数据合同改动混在一起，无法归因。

## 18. Architecture C 接入条件

当前尚未创建正式 v2 数据；
当前尚未运行 v2 实验；
当前也没有任何合格 Retriever。

因此，现阶段 **不得** 接入 Architecture C。

只有满足以下条件后才允许讨论接入：

1. v2 合同和数据冻结；
2. v2 正式实验完成；
3. 至少一个方法通过 v2 Blocking Gate；
4. 失败归因能明确区分数据、合同和 Retriever 本身。
