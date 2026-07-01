# Retrieval Benchmark V2 Results

## 1. 实验目标

本次冻结的是 Retrieval Benchmark v2 的唯一一次正式结果集，用于回答三个问题：

1. 在 v2 的知识范围、边界合同和可达性合同下，Lexical / Vector / Hybrid 三种方法的正式指标分别是多少。
2. 在冻结的 Blocking Gate 下，是否存在可进入 Demo 级 RAG 默认候选的方法。
3. v1 与 v2 的指标变化中，哪些来自评测合同与数据治理，哪些才可能反映 Retriever 的真实排序差异。

## 2. Benchmark 范围

- 数据类型：合成 Demo 数据
- Demo Solution 范围：6 个 Solution
- Knowledge Base：20 份 Documents
- Chunk 数量：40
- Retrieval Cases：16
- 当前没有 Vector Database
- 当前没有 Reranker
- 当前没有 Query Rewrite
- 当前没有生产流量验证

重要边界：

- Retrieval 指标不是 Agent 端到端准确率。
- 当前结果不能宣称生产级准确率或生产级 RAG 能力。
- 即便未来出现 `eligible_for_rag=true` 的方法，也只能作为 Demo 默认 Retriever 候选，不代表生产可用。

## 3. Attempt 记录

### Attempt 1

- 状态：`technical_failure`
- 正式结果是否发布：`false`
- 失败原因：Summary 聚合使用 `statistics.mean(...)`，staging 重算使用 `sum(...) / count`，导致 `recall_at_5` 出现约 `1.11e-16` 的浮点差异。

### Metrics 单一真源修复

- Runner、staging 校验和 post-publish `--check` 统一复用 `aggregate_summary_metrics_v2(...)`
- 该修复只统一 Summary 重算路径，不修改数据、配置、算法或正式结果。

### Attempt 2

- 正式命令只执行了一次：`python scripts/run_retrieval_benchmark_v2.py --run --write`
- 7 个正式结果文件成功通过 staging 校验并原子发布

### post-publish Check 控制流修复

Attempt 2 发布后第一次 `--check` 的失败原因不是结果不一致，而是 CLI 控制流错误地复用了“首次正式运行前正式结果必须不存在”的前置条件。后续修复做了三层语义拆分：

1. Core Validation
2. Formal Readiness
3. Post-publish Formal Check

该修复没有修改任何正式结果内容。修复后 `--check` 返回：

- `status = formal_results_match`
- `differences = []`

## 4. 冻结输入与结果 Hash

### 4.1 输入与配置

- `data/knowledge_base/solution_scope_migration.v2.json`
  - `8a702857b5a7fbe1029f4316a95fd67a3f2892c0bd122d9678f55fb8a29aa10c`
- `data/knowledge_base/documents.v2.jsonl`
  - `81b3cd9de38eb654600dcea68ca9bb98c53ce7340e56438a01ceb3f4be7203f3`
- `data/knowledge_base/chunks.v2.jsonl`
  - `cab598740630873cb69c3b79020f64ae4cb34ced0fc42973884463bea2fea070`
- `data/knowledge_base/manifest.v2.json`
  - `716539d6a5c9211d7f379698ed63d81a34a7800719f1bb5f7a8c477885b27483`
- `data/evaluation/retrieval/retrieval_case_migration.v2.json`
  - `dfc05f839e20918e88e5d660da01c91403d8df42032f1858fb26c97b7a3c6935`
- `data/evaluation/retrieval/retrieval_cases.v2.jsonl`
  - `1cd3f830fe62b41f55dcfcc61da763bb92a3fc6ca1f651e5c4eb194901c29804`
- `data/evaluation/retrieval/retrieval_case_feasibility.v2.json`
  - `5473bbc01ce188217502201ac84e3ce716efaccae9ef50dbcb893e9cf06829b2`
- `data/evaluation/retrieval/retrieval_benchmark_config.v2.json`
  - `ca2aed9590fc0fef39cd3b478e50874933cc74d9e13921edb619de63e1f8afd8`
- `data/evaluation/retrieval/lexical_baseline_config.v2.json`
  - `efda4f10066732fed8d516a1bffc878ca247a86eac77b694978c6d142d12bf73`
- `data/evaluation/retrieval/vector_baseline_config.v2.json`
  - `e0572aa9bb2b99fd18c354cede23752904b4e2bc7d15052006f18d9003a14785`
- `data/evaluation/retrieval/hybrid_baseline_config.v2.json`
  - `7c4ba5f2568becc44e8e040ee6aa3ed3a8a6050e3e18cae7beaf851b035dc2bb`

### 4.2 冻结正式结果

- `lexical_baseline_results.v2.jsonl`
  - `41bfa53dda9a65e78f82eeab064e0a9436b47bb423b3c52d995e3b661e552bad`
- `lexical_baseline_summary.v2.json`
  - `c5a48e917a897bd3ab76b2f815fdc07796e69ff0c9117534e50d0b13058f67e0`
- `vector_baseline_results.v2.jsonl`
  - `9db04530b0240d00175dd5f386b7cc4cea030266ba90bb3180063a5c320244c4`
- `vector_baseline_summary.v2.json`
  - `766801ae928598de3e9ed23097f497764eeeac84e09da56ad6ee60b61cc8d585`
- `hybrid_baseline_results.v2.jsonl`
  - `c5a3ace3ce08914fc7af7426e2c20143863d123b9e5ea3cfff314c0cd8dc5c46`
- `hybrid_baseline_summary.v2.json`
  - `d9543f66c64ff065ba5be0e6cc80a1a97dcafc1caa3fcb4622b6704052679d74`
- `retrieval_method_comparison.v2.json`
  - `92c405e623246dacc154d935f31069f4e31b96e55c8886eea9ec9d314aea618d`

## 5. 算法与参数冻结说明

v1 与 v2 的 Retriever 算法和参数保持逐字段一致：

- Lexical：`weighted_bm25`
- Vector：`dense_cosine`
- Hybrid：`lexical_vector_rrf`

v2 的变化不来自 Retriever 调参，也不来自 Embedding 模型更换。Vector / Hybrid 继续使用：

- model name：`intfloat/multilingual-e5-small`
- resolved revision：`614241f622f53c4eeff9890bdc4f31cfecc418b3`
- embedding dimension：`384`

## 6. Lexical v2 正式指标

- recall_at_1: `0.2552083333333333`
- recall_at_3: `0.6822916666666666`
- recall_at_5: `0.8854166666666666`
- precision_at_3: `0.8958333333333334`
- precision_at_5: `0.771875`
- mean_reciprocal_rank: `1.0`
- forbidden_hit_rate: `0.0`
- solution_boundary_violation_rate: `0.1875`
- request_error_count: `0`
- failed_case_ids: `RET2-005`, `RET2-006`, `RET2-009`
- failure_taxonomy: `{"solution_boundary_violation": 3}`
- eligible_for_rag: `false`
- disqualification_reasons: `["solution_boundary_violation"]`
- average_latency_ms: `0.0625`

## 7. Vector v2 正式指标

- recall_at_1: `0.23958333333333334`
- recall_at_3: `0.6979166666666666`
- recall_at_5: `0.8697916666666666`
- precision_at_3: `0.9166666666666666`
- precision_at_5: `0.75`
- mean_reciprocal_rank: `0.96875`
- forbidden_hit_rate: `0.0`
- solution_boundary_violation_rate: `0.1875`
- request_error_count: `0`
- failed_case_ids: `RET2-005`, `RET2-006`, `RET2-009`
- failure_taxonomy: `{"solution_boundary_violation": 3}`
- eligible_for_rag: `false`
- disqualification_reasons: `["solution_boundary_violation"]`
- average_latency_ms: `1048.1875`
- model_name: `intfloat/multilingual-e5-small`
- resolved_model_revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`
- embedding_dimension: `384`
- corpus_embedding_count: `40`
- corpus_embedding_build_ms: `56`
- cache_hit_count: `40`
- cache_miss_count: `0`

## 8. Hybrid v2 正式指标

- recall_at_1: `0.2552083333333333`
- recall_at_3: `0.7135416666666666`
- recall_at_5: `0.8854166666666666`
- precision_at_3: `0.9375`
- precision_at_5: `0.7625`
- mean_reciprocal_rank: `1.0`
- forbidden_hit_rate: `0.0`
- solution_boundary_violation_rate: `0.125`
- request_error_count: `0`
- failed_case_ids: `RET2-005`, `RET2-006`
- failure_taxonomy: `{"solution_boundary_violation": 2}`
- eligible_for_rag: `false`
- disqualification_reasons: `["solution_boundary_violation"]`
- average_latency_ms: `53.625`
- model_name: `intfloat/multilingual-e5-small`
- resolved_model_revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`
- embedding_dimension: `384`
- corpus_embedding_count: `40`
- corpus_embedding_build_ms: `56`
- cache_hit_count: `40`
- cache_miss_count: `0`

## 9. 失败 Case 与 Failure Taxonomy

### 9.1 failed_case_ids

- Lexical：`RET2-005`, `RET2-006`, `RET2-009`
- Vector：`RET2-005`, `RET2-006`, `RET2-009`
- Hybrid：`RET2-005`, `RET2-006`

### 9.2 失败原因

- 三种方法的正式 taxonomy 都只保留 `solution_boundary_violation`
- 共同失败的 Case：`RET2-005`, `RET2-006`
- 仅 Lexical / Vector 失败、Hybrid 通过的 Case：`RET2-009`
- 没有只被单一方法失败的 Case

### 9.3 Blocking Gate 结果

三种方法都未通过冻结 Blocking Gate，因此：

- `eligible_for_rag = false`
- `selected_method = null`

## 10. selected_method 与 selection_status

来自 `retrieval_method_comparison.v2.json` 的冻结结论：

- selected_method: `null`
- selection_status: `no_eligible_method`
- selection_reasons:
  - `No retrieval method passed the frozen blocking gate.`
- rejected_methods:
  - `lexical_v1`
  - `vector_v1`
  - `hybrid_v1`

因此，当前 **不允许把 Retrieval Benchmark v2 直接接入 Architecture C**。

## 11. Blocking Gate 语义与原因字段限制

必须区分两个层级：

1. `eligible_for_rag` 使用完整 Summary Gate：
   - `recall_at_5 == 1.0`
   - `forbidden_hit_rate == 0`
   - `solution_boundary_violation_rate == 0`
   - `request_error_count == 0`
   - `all cases pass blocking gate`
2. `disqualification_reasons` 当前不是完整 Gate 失败列表。
3. 当前 Artifact 中的 `disqualification_reasons` 只汇总 case-level failure taxonomy。
4. 因此正式 Artifact 里只看到 `solution_boundary_violation`，**不代表 Recall Gate 已经通过**。

三种方法的完整 Gate 判定如下。

### Lexical

- recall gate：失败
- forbidden gate：通过
- boundary gate：失败
- request error gate：通过
- eligible：`false`

### Vector

- recall gate：失败
- forbidden gate：通过
- boundary gate：失败
- request error gate：通过
- eligible：`false`

### Hybrid

- recall gate：失败
- forbidden gate：通过
- boundary gate：失败
- request error gate：通过
- eligible：`false`

即使未来只把 Boundary 清零，按当前正式 Recall：

- Lexical：`0.8854166666666666`
- Vector：`0.8697916666666666`
- Hybrid：`0.8854166666666666`

三种方法仍然都**不能**通过冻结 Gate。  
所以当前不允许接入 Architecture C，并不只是因为 Boundary 没有清零，也因为 Recall@5 没有达到 `1.0`。

当前 v2 正式结果文件保持不变；本节只是把 Gate 语义补充解释完整。未来如果要改进结果 Schema，应通过新版本增加完整的 summary-level gate failure 字段，不能覆盖当前 v2 Artifact。

## 12. v1 与 v2 逐方法对比

### 12.1 Lexical

- recall_at_1: `0.25 -> 0.2552083333333333` (`+0.005208333333333315`)
- recall_at_3: `0.703125 -> 0.6822916666666666` (`-0.02083333333333337`)
- recall_at_5: `0.921875 -> 0.8854166666666666` (`-0.03645833333333337`)
- precision_at_3: `0.9375 -> 0.8958333333333334` (`-0.04166666666666663`)
- precision_at_5: `0.796875 -> 0.771875` (`-0.025000000000000022`)
- MRR: `1.0 -> 1.0` (`0.0`)
- forbidden_hit_rate: `0.0 -> 0.0` (`0.0`)
- solution_boundary_violation_rate: `0.4375 -> 0.1875` (`-0.25`)
- failed_case_count: `7 -> 3`
- eligible_for_rag: `false -> false`

### 12.2 Vector

- recall_at_1: `0.234375 -> 0.23958333333333334` (`+0.005208333333333343`)
- recall_at_3: `0.71875 -> 0.6979166666666666` (`-0.02083333333333337`)
- recall_at_5: `0.90625 -> 0.8697916666666666` (`-0.03645833333333337`)
- precision_at_3: `0.9583333333333334 -> 0.9166666666666666` (`-0.04166666666666674`)
- precision_at_5: `0.775 -> 0.75` (`-0.025000000000000022`)
- MRR: `0.96875 -> 0.96875` (`0.0`)
- forbidden_hit_rate: `0.0625 -> 0.0` (`-0.0625`)
- solution_boundary_violation_rate: `0.625 -> 0.1875` (`-0.4375`)
- failed_case_count: `16 -> 3`
- eligible_for_rag: `false -> false`

### 12.3 Hybrid

- recall_at_1: `0.25 -> 0.2552083333333333` (`+0.005208333333333315`)
- recall_at_3: `0.71875 -> 0.7135416666666666` (`-0.00520833333333337`)
- recall_at_5: `0.90625 -> 0.8854166666666666` (`-0.02083333333333337`)
- precision_at_3: `0.9583333333333334 -> 0.9375` (`-0.02083333333333337`)
- precision_at_5: `0.775 -> 0.7625` (`-0.012500000000000067`)
- MRR: `1.0 -> 1.0` (`0.0`)
- forbidden_hit_rate: `0.0 -> 0.0` (`0.0`)
- solution_boundary_violation_rate: `0.5 -> 0.125` (`-0.375`)
- failed_case_count: `16 -> 2`
- eligible_for_rag: `false -> false`

## 13. 如何解释 v1 与 v2 的变化

必须明确，这不是“相同数据集上的纯算法 A/B”。

### 12.1 保持不变的部分

- Retriever 算法不变
- Retriever 参数不变
- Embedding 模型与 revision 不变

### 12.2 改变的部分

- Knowledge Scope v2
- Boundary 合同 v2
- Case 可达性合同 v2
- Failure Taxonomy v2
- Runtime Context 与 Gold 的严格隔离

### 12.3 因此能得出的结论

- 指标变化不能归功于 Embedding 模型或 Retriever 调参
- 更合理的解释是：数据治理、边界元数据和评测合同改变了“什么算合理检索、什么算违规、什么算不可达”
- `empty_query_tokens` 在 v1 中会被误分类；在 v2 正式 taxonomy 中已消除

## 14. Knowledge Scope v2 与 Feasible Case 合同的影响

v2 的主要收益不是“让模型更聪明”，而是让评测对象更清楚：

- Solution Scope 被明确限制在 6 个 Demo Solutions
- Chunk 级 Scope 收窄后，违规命中更容易被识别
- 16 条 Case 都先经过 Feasibility 审计，减少了 v1 中“Gold 自身不可达”的混杂因素

这提升了评测解释性，但不意味着 Retriever 本身已经达到了可接入 Architecture C 的稳定水平。

## 15. Runtime Context 与 Gold 隔离

v2 继续保持：

- Retriever 只接收 Runtime Context
- Gold 只在候选返回后进入 Evaluation
- 正式结果文件中不暴露完整 Query、Gold、知识正文或 Embedding 向量

## 16. 延迟与工程成本

- Lexical 平均延迟最低：`0.0625 ms`
- Hybrid 平均延迟：`53.625 ms`
- Vector 平均延迟最高：`1048.1875 ms`

在三种方法都不合格的前提下，当前没有理由为了更高工程成本接入 Vector 或 Hybrid。

## 17. 当前限制

- 数据仍是合成 Demo 数据
- 只覆盖 6 个 Solutions
- 只覆盖 20 Documents / 40 Chunks / 16 Cases
- 没有生产流量验证
- 没有 Query Rewrite
- 没有 Reranker
- 没有 Vector Database
- Retrieval 指标不是 Agent 端到端准确率

## 18. 是否允许进入 Architecture C

结论：**当前不允许接入 Architecture C。**

原因：

- 三种方法 `eligible_for_rag` 全部为 `false`
- `selected_method = null`
- 当前 case-level taxonomy 集中暴露的是 boundary 问题
- 但完整 Summary Gate 同时没有通过 Recall@5 和 Boundary 两项条件
- `selection_status = no_eligible_method`

## 19. 下一阶段建议

下一阶段应继续在 Retrieval Benchmark 内做版本化治理，而不是直接接入 Agent：

1. 优先分析 `RET2-005`、`RET2-006`、`RET2-009` 的 boundary 失败根因
2. 在不放宽冻结 Gate 的前提下，同时推进：
   - recall improvement
   - boundary-safe candidate control
3. 保持算法冻结前提下，继续修正知识范围与评测合同的可解释性
4. 只有当至少一个方法通过冻结 Blocking Gate，才考虑进入 Architecture C 的 Demo 接入评估
