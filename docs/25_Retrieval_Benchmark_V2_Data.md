# Retrieval Benchmark V2 Data

## 1. 本轮目标

本轮冻结的是 Retrieval Benchmark v2 的公开数据层，而不是 Retriever 算法结果。

输出包括：

- `data/knowledge_base/solution_scope_migration.v2.json`
- `data/knowledge_base/documents.v2.jsonl`
- `data/knowledge_base/chunks.v2.jsonl`
- `data/knowledge_base/manifest.v2.json`
- `data/evaluation/retrieval/retrieval_case_migration.v2.json`
- `data/evaluation/retrieval/retrieval_cases.v2.jsonl`
- `data/evaluation/retrieval/retrieval_case_feasibility.v2.json`
- `data/evaluation/retrieval/retrieval_benchmark_config.v2.json`

本轮不重写任何 v1 文件，也不运行新的 Retriever 正式实验。

## 2. 三层 Solution 范围

### 2.1 Case-local Available Solution Library

Development Case 中的 `available_solution_library` 是单个 Evaluation Case 的输入约束。

它回答的是：

> 当前这个 case 当次允许模型看到或推荐哪些候选方案。

它不是正式企业主数据，也不是 Retrieval Benchmark 的知识库主目录。

### 2.2 Demo Enterprise Solution Scope

当前公开 Demo 只覆盖 6 个选定 solution_id。

这 6 个 solution_id 来自既有 63 个 case-local solution_id 的可审计子集，用于构建：

- 20 份合成 KnowledgeDocument
- 40 个确定性 Chunk
- 16 条 Retrieval Evaluation Cases

这是有意控制范围，不是遗漏。

### 2.3 Future Enterprise Master Catalog

真实生产环境中的正式方案主数据应由产品、交付、商业和合规团队维护。

本项目当前没有实现这层正式主目录，因此：

- 63 个 case-local solution_id 不等于企业正式产品数量；
- 当前 6 个 Demo solution 也不等于企业最终方案全集。

后续扩容应通过新版本增加 Solution，而不是直接改写 v1/v2 已冻结数据。

## 3. 为什么使用 6 个 Demo Solution 而不是 63 个 ID

原因有三点：

1. 63 个 ID 是 case-local 候选集合，不是统一、治理完成的企业目录。
2. 当前阶段更重要的是建立高质量、可解释、可校验的 Retrieval 合同，而不是追求目录数量。
3. 先冻结一个公开、可复现的小范围 Benchmark，能让后续 Feasibility、Boundary 和 Failure Taxonomy 有稳定基线。

因此：

- `source_solution_id_count = 63`
- `selected_solution_id_count = 6`
- `excluded_solution_ids = 57`

这 57 个 excluded ID 只记录在范围与迁移元数据中，不进入 v2 知识文档，也不会成为 v2 Retrieval Gold 的可推荐方案。

## 4. Knowledge Base v2 冻结结果

### 4.1 文档与 Chunk 数量

- KnowledgeDocument: 20
- KnowledgeChunk: 40
- Demo Solution: 6

### 4.2 文档类型覆盖

共覆盖 10 类文档：

- `solution`: 6
- `capability`: 2
- `case_study`: 2
- `implementation_playbook`: 2
- `integration_requirement`: 2
- `readiness_requirement`: 2
- `security_compliance`: 1
- `delivery_constraint`: 1
- `commercial_rule`: 1
- `unsupported_scenario`: 1

### 4.3 Scope 迁移结果

`solution_scope_migration.v2.json` 记录了完整的 v1 -> v2 Scope 决策。

关键统计：

- `document_count = 20`
- `chunk_count = 40`
- `multi_solution_document_count = 14`
- `inherited_scope_chunk_count = 36`
- `narrowed_scope_chunk_count = 4`

其中：

- `KB-COM-001` 被重新表达为 `global_policy`
- 4 个 chunk 采用了比文档更窄的 Scope
- 所有 chunk 仍然满足“不得宽于父文档”的约束

### 4.4 对 6 个 Demo Solution 的覆盖

每个 selected solution 都满足：

- 至少 1 份 `solution` 文档
- 至少 2 份非 `solution` 文档引用

实际覆盖如下：

- `合规政策RAG检索助手`：1 份 solution 文档，6 份非 solution 文档引用
- `客户身份统一与数据集成方案`：1 份 solution 文档，6 份非 solution 文档引用
- `商品知识库RAG方案`：1 份 solution 文档，5 份非 solution 文档引用
- `客服辅助回复方案`：1 份 solution 文档，5 份非 solution 文档引用
- `服务工单系统集成方案`：1 份 solution 文档，7 份非 solution 文档引用
- `私有化大模型部署方案`：1 份 solution 文档，6 份非 solution 文档引用

## 5. Retrieval Cases v2

### 5.1 总量

- Retrieval Cases: 16
- v2 Case ID: `RET2-001` 到 `RET2-016`
- 每条 case 都保留 `source_case_id`

### 5.2 迁移原则

v2 保持：

- query 不变
- 原业务问题不变
- source_case_id 不变

但将原先混在一起的 case 信息拆分为：

- Runtime Context
- Evaluation Gold

### 5.3 特殊审计 Case

本轮明确审计了：

- `RET-001`
- `RET-002`
- `RET-005`
- `RET-006`
- `RET-009`

结果：

- `RET-001`：在 v2 Scope 下自然可达，无需改 query
- `RET-002`：在 v2 Scope 下自然可达，无需改 query
- `RET-005`：调整 gold，使其不再依赖 forbidden multi-solution 证据
- `RET-006`：重写为可达的 product-knowledge / assistive-reply 边界证据
- `RET-009`：重写为可达的 compliance-only 证据组合

## 6. Feasibility 结果

`retrieval_case_feasibility.v2.json` 的冻结结果为：

- `case_count = 16`
- `feasible_case_count = 16`
- `infeasible_case_count = 0`

这意味着 v2 正式 Benchmark 数据层已经满足：

- expected IDs 存在
- runtime filters 不排除 expected
- boundary-safe expected items 足够
- `minimum_relevant_hits` 可满足

## 7. Benchmark Config v2

`retrieval_benchmark_config.v2.json` 冻结了以下关键合同：

- `benchmark_version = retrieval_benchmark_v2`
- `knowledge_contract_version = v2`
- `retrieval_contract_version = v2_method_aware`
- `failure_taxonomy_version = v2_method_aware`
- `boundary_contract_version = v2`
- `document_count = 20`
- `chunk_count = 40`
- `case_count = 16`
- `demo_solution_count = 6`
- `all_cases_feasible = true`

Blocking Gate 保持与 v1 同等级严格性：

- `recall_at_5 == 1.0`
- `forbidden_hit_rate == 0.0`
- `solution_boundary_violation_rate == 0.0`
- `request_error_count == 0`
- `all_cases_pass_blocking_gate == true`

## 8. v1 与 v2 的关系

v2 是新增版本，不覆盖 v1。

保持不变的内容包括：

- v1 Knowledge Base
- v1 Retrieval Cases
- v1 Lexical / Vector / Hybrid 正式结果
- v1 Failure Analysis

因此当前仓库同时保留：

- v1 冻结实验结果
- v2 冻结数据合同

这样后续可以在不破坏旧审计结果的前提下，为 v2 开展新的正式 Retrieval 实验。
