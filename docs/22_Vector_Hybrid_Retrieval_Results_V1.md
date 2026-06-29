# Vector / Hybrid Retrieval Results V1

## 1. 实验目标

本轮目标是在冻结的 Demo Knowledge Base、冻结的 Retrieval Cases、冻结的 Blocking Gate 下，完成一次可复现的正式离线实验，对比：

- `lexical_v1`
- `vector_v1`
- `hybrid_v1`

并据此给出当前阶段的 `selected_method` 与 `selection_status`。

## 2. 冻结数据范围

本轮实验只覆盖公开合成 Demo 数据：

- 6 个 Demo Solutions
- 20 份 Knowledge Documents
- 40 个固定 Chunks
- 16 条 Retrieval Cases

这不是完整企业知识库，也不是生产主数据目录。

## 3. Attempt 1 技术失败说明

Attempt 1 未形成正式实验结果。

失败根因是正式运行路径虽然检测到了本地缓存模型，但仍然把 Hugging Face repo ID 直接传给 Sentence Transformers，导致底层 `AutoProcessor.from_pretrained(...)` 继续尝试访问远端元数据。该次运行只留下技术失败记录，不纳入正式结果比较。

## 4. 离线加载 Bug 及修复

修复后的正式路径采用三层离线防线：

1. 固定模型：
   - `intfloat/multilingual-e5-small`
2. 固定 revision：
   - `614241f622f53c4eeff9890bdc4f31cfecc418b3`
3. 正式 `run/check` 先解析本地 snapshot，再用本地路径初始化 Sentence Transformers，并显式设置：
   - `local_files_only=True`
   - `trust_remote_code=False`
   - `HF_HUB_OFFLINE=1`
   - `TRANSFORMERS_OFFLINE=1`
   - `HF_HUB_DISABLE_TELEMETRY=1`

因此 Attempt 2 是离线加载修复后的首个有效正式实验。

## 5. Attempt 2 正式实验纪律

Attempt 2 严格遵守以下纪律：

- 不下载或更换模型
- 不访问 Hugging Face 网络
- 不调用任何 LLM API
- 不修改 Vector / Hybrid 参数
- 不修改 Knowledge Base、Retrieval Cases 或 Gold IDs
- 不根据结果调参
- 不重复执行正式 `--run --write`

## 6. 固定模型与 Revision

- Model: `intfloat/multilingual-e5-small`
- Revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`
- Embedding Dimension: `384`
- Device: `cpu`
- Query Prefix: `query: `
- Document Prefix: `passage: `

## 7. Corpus Embedding 与缓存统计

Attempt 2 正式运行结果：

- Corpus Embedding Count: `40`
- Cache Hit Count: `0`
- Cache Miss Count: `40`
- Corpus Embedding Build Time: `46855 ms`

本次是首个有效正式实验，因此 Corpus Embedding 全量首次构建，Vector 与 Hybrid 共享同一批 40 个语料向量。

## 8. Lexical 真实指标

- recall@1: `0.25`
- recall@3: `0.703125`
- recall@5: `0.921875`
- precision@3: `0.9375`
- precision@5: `0.796875`
- MRR: `1.0`
- forbidden_hit_rate: `0.0`
- solution_boundary_violation_rate: `0.4375`
- average_latency_ms: `0.9375`
- eligible_for_rag: `false`

失败 Case：

- `RET-001`
- `RET-002`
- `RET-003`
- `RET-004`
- `RET-005`
- `RET-006`
- `RET-009`

## 9. Vector 真实指标

- recall@1: `0.234375`
- recall@3: `0.71875`
- recall@5: `0.90625`
- precision@3: `0.9583333333333334`
- precision@5: `0.775`
- MRR: `0.96875`
- forbidden_hit_rate: `0.0625`
- solution_boundary_violation_rate: `0.625`
- average_latency_ms: `217.8125`
- eligible_for_rag: `false`

失败 Case：全部 16 条

- `RET-001` 至 `RET-016`

## 10. Hybrid 真实指标

- recall@1: `0.25`
- recall@3: `0.71875`
- recall@5: `0.90625`
- precision@3: `0.9583333333333334`
- precision@5: `0.775`
- MRR: `1.0`
- forbidden_hit_rate: `0.0`
- solution_boundary_violation_rate: `0.5`
- average_latency_ms: `136.5625`
- eligible_for_rag: `false`

失败 Case：全部 16 条

- `RET-001` 至 `RET-016`

## 11. 三种方法对比表

| Method | recall@5 | forbidden_hit_rate | boundary_violation_rate | MRR | avg_latency_ms | eligible_for_rag |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| lexical_v1 | 0.921875 | 0.0 | 0.4375 | 1.0 | 0.9375 | false |
| vector_v1 | 0.90625 | 0.0625 | 0.625 | 0.96875 | 217.8125 | false |
| hybrid_v1 | 0.90625 | 0.0 | 0.5 | 1.0 | 136.5625 | false |

## 12. 各方法失败 Case

- `lexical_v1`：7 条失败
- `vector_v1`：16 条失败
- `hybrid_v1`：16 条失败

说明：Vector 与 Hybrid 虽然在部分排序指标上可比，但在冻结 Blocking Gate 下没有任何方法达标。

## 13. Failure Taxonomy

### lexical_v1

- `solution_boundary_violation`: 7

### vector_v1

- `empty_query_tokens`: 16
- `solution_boundary_violation`: 10
- `forbidden_document_hit`: 1

### hybrid_v1

- `empty_query_tokens`: 16
- `solution_boundary_violation`: 8

说明：这里的 Failure Taxonomy 使用的是当前冻结评测实现输出的正式 failure reasons，反映的是当前评测框架的阻断原因，不等于用户业务价值判断。

## 14. Blocking Gate 结果

冻结 Gate 要求：

- `recall_at_5 == 1.0`
- `forbidden_hit_rate == 0`
- `solution_boundary_violation_rate == 0`
- `request_error_count == 0`
- 所有 Case 均通过 blocking gate

Attempt 2 中三种方法均未满足以上条件，因此没有任何方法 `eligible_for_rag=true`。

## 15. selected_method 与 selection_status

- `selected_method = null`
- `selection_status = no_eligible_method`

理由：

1. 没有任何方法通过冻结 Blocking Gate
2. 选择规则不默认偏向 Hybrid
3. 也不会因为 Vector 或 Hybrid 更复杂而被优先选择

## 16. 选择或未选择的理由

当前未选择任何方法，不是因为运行失败，而是因为冻结规则下没有合格方法：

- `lexical_v1` 的主要问题是 solution boundary violation
- `vector_v1` 的 boundary violation 更高，并且出现 forbidden hit
- `hybrid_v1` 比纯 Vector 稳定一些，但 boundary violation 仍未降到可接受范围

因此当前最合理的正式结论是：

> 当前 Retrieval V1 结果尚不足以宣布任何方法“可用于 RAG 路由默认方案”。

## 17. 平均延迟和工程复杂度

- `lexical_v1`
  - latency: `0.9375 ms`
  - complexity: `low`
- `vector_v1`
  - latency: `217.8125 ms`
  - complexity: `medium`
- `hybrid_v1`
  - latency: `136.5625 ms`
  - complexity: `medium_high`

在当前 40-chunk 规模下，Lexical 仍然是最轻量、最容易解释的方法。

## 18. Gold 隔离与无网络证明

- Gold IDs 仅在检索完成后进入 Metrics
- 正式结果文件中不保存 Gold 字段副本
- 正式结果文件中不保存 Embedding
- 不保存知识文档全文
- 不保存本机绝对路径
- Attempt 2 使用固定本地 snapshot 与强制离线环境完成

## 19. 当前适用边界

必须明确：

- 当前数据全部为合成 Demo 数据
- 当前只覆盖 6 个 Demo Solutions
- 当前没有 Vector Database
- 当前没有 Reranker
- 当前尚未接入 Architecture C
- Retrieval 指标不是 Agent 端到端准确率
- Vector 或 Hybrid 不一定优于 Lexical

## 20. Architecture C 接入计划

后续如果要接入 Architecture C，建议按以下顺序推进：

1. 保持当前 Retrieval Benchmark 冻结不变
2. 先解决 boundary violation 和 blocking gate 合格率问题
3. 只有出现 `eligible_for_rag=true` 的候选方法后，再讨论接入 Workflow
4. 接入时仍需保持：
   - Gold 隔离
   - 无在线调参
   - Retrieval 与 Agent 评估分层

在那之前，当前 Retrieval 结果更适合作为：

- 离线基准线
- 工程可行性对比
- Architecture C 后续接入前的冻结参考
