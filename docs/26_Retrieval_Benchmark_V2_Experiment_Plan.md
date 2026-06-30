# Retrieval Benchmark V2 Experiment Plan

## 1. D4C 目标

本轮只实现 Retrieval Benchmark v2 的 Runner、方法配置和非正式验证能力。

本轮不做：

- 正式 16 条 v2 Lexical 实验
- 正式 16 条 v2 Vector 实验
- 正式 16 条 v2 Hybrid 实验
- 正式 v2 results / summary / comparison 冻结

## 2. 为什么先实现 Runner 再正式实验

在 v2 数据和合同已经冻结后，下一步风险不在算法本身，而在：

- Runtime Context 与 Gold 的隔离
- v2 Scope 的运行时语义
- Failure Taxonomy v2 是否正确落地
- Boundary Evaluation v2 是否与 Retriever 解耦

先把 Runner 打通，才能在不污染正式结果的前提下完成：

- Plan
- Validate
- Fake Smoke
- Offline Model Smoke
- Check 前置能力

## 3. v1 与 v2 的唯一变化

v2 相比 v1，当前只允许以下变化：

- 数据版本切换到 `documents.v2` / `chunks.v2`
- Case 合同切换到 `retrieval_cases.v2`
- Failure Taxonomy 切换到 `v2_method_aware`
- Boundary 合同切换到 `v2`

三种 Retriever 的算法和参数必须保持与 v1 完全一致。

## 4. 三种 Retriever 算法参数保持不变

### Lexical

- 同一 tokenizer
- 同一 BM25
- 同一字段权重
- 同一 `top_k = 5`

### Vector

- `intfloat/multilingual-e5-small`
- frozen revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`
- dimension `384`
- `query: `
- `passage: `
- CPU
- exact cosine
- local offline loading

### Hybrid

- 同一 lexical
- 同一 vector
- 同一 `RRF k = 60`
- lexical/vector 权重均为 1

## 5. Runtime Context 与 Gold 隔离

Retriever 运行时只允许接收：

- `query`
- `operational_filters`
- `operational_solution_scope`
- `allowed_document_types`
- `industries`
- `tags`
- `effective_on`
- `top_k`

Retriever 不得看到：

- `expected_relevant_document_ids`
- `expected_relevant_chunk_ids`
- `forbidden_document_ids`
- `forbidden_solution_ids`
- `minimum_relevant_hits`

Gold 只在候选返回后进入 Evaluation 阶段。

## 6. v2 Scope 过滤语义

Runner v2 使用：

- Chunk Scope 优先
- 缺失时才回退 Document Scope
- `global_policy` 不因覆盖全部 6 个 Demo Solutions 自动违规
- `excluded_solution_ids` 仍然是有效边界

## 7. Failure Taxonomy v2

Runner v2 使用 method-aware 分类器：

- `empty_query`
- `missing_required_debug`
- `no_relevant_hit_at_5`
- `insufficient_relevant_hits`
- `forbidden_document_hit`
- `solution_boundary_violation`
- `operational_filter_excluded_all`
- `retrieval_error`

它修复了 v1 中把 Vector / Hybrid 误判为空 Query 的问题。

## 8. Boundary Evaluation v2

Boundary Evaluation v2 与 Retriever 本身分离：

- Retriever 只做 Runtime 可见过滤
- Boundary 违规在候选返回后判断
- Feasibility Gate 保证 Expected 本身可达

## 9. Metrics 与 Blocking Gate

Runner v2 继续产出与 v1 可比的指标：

- `recall_at_1`
- `recall_at_3`
- `recall_at_5`
- `precision_at_3`
- `precision_at_5`
- `reciprocal_rank`
- `mean_reciprocal_rank`
- `forbidden_hit_rate`
- `solution_boundary_violation_rate`
- `request_error_count`
- `failed_case_ids`
- `eligible_for_rag`

Blocking Gate 维持与 v1 同等级：

- `recall_at_5 == 1.0`
- `forbidden_hit_rate == 0`
- `solution_boundary_violation_rate == 0`
- `request_error_count == 0`
- 所有 case 通过 blocking gate

## 10. 正式结果路径

正式实验未来一次性发布 7 个固定文件：

- `lexical_baseline_results.v2.jsonl`
- `lexical_baseline_summary.v2.json`
- `vector_baseline_results.v2.jsonl`
- `vector_baseline_summary.v2.json`
- `hybrid_baseline_results.v2.jsonl`
- `hybrid_baseline_summary.v2.json`
- `retrieval_method_comparison.v2.json`

Runner 会先在 Git 忽略的 Runtime 临时目录生成候选文件，完成结构校验与一致性校验后，再一次性发布到这些正式路径。

## 11. 原子写入与失败恢复

正式 `--run --write` 使用两阶段发布：

1. 先在 Runtime staging 目录生成 7 个候选文件
2. 对候选文件重新执行条数、顺序、Summary 重算、Comparison 一致性与安全字段检查
3. 全部通过后发布到正式路径

如果中途任一环节失败：

- 不覆盖已存在的正式结果
- 不保留部分正式文件
- 只在 Git 忽略的 Runtime Attempt 审计目录留下技术失败元数据

## 12. 一次性正式实验纪律

正式 v2 实验开始前必须先通过：

- Validate
- Fake Smoke
- Offline Model Smoke
- Formal Readiness
- Check 前置

正式实验开始后：

- 不得中途调参
- 不得修改 Gold
- 不得修改 Scope
- 不得修改 Blocking Gate

## 13. Formal Readiness

`python scripts/run_retrieval_benchmark_v2.py --formal-readiness` 只检查：

- 数据与配置 Hash
- 20 / 40 / 16 数量
- 16 条 Case 全部 Feasible
- 7 个正式结果文件尚不存在
- 本地固定 Embedding Snapshot 可用
- 网络被禁用
- Runtime 目录与 Embedding Cache 目录可写

它不运行正式 Case，也不生成正式结果。

## 14. Attempt 审计语义

未来正式运行会在 Git 忽略的 Runtime 审计目录记录：

- `attempt_id`
- `attempt_number`
- `status`
- `started_at`
- `completed_at`
- `technical_failure`
- `formal_results_published`

技术失败允许在不发布正式结果的前提下进入下一次 Attempt；指标不好不属于技术失败，也不允许重跑。

## 15. 技术失败与算法失败

技术失败示例：

- 缺失本地模型
- 缺失必需 debug 字段
- 请求执行异常

算法失败示例：

- Recall 不足
- Forbidden hit
- Boundary violation

两者必须在结果中分开记录。

## 16. Check 语义

正式结果不存在时，`--check` 必须明确返回：

- `formal_results_not_generated`

正式结果存在时，`--check` 会重新执行确定性评测路径，并严格比较：

- Case 结果顺序、ID、rank、score、boundary 标记与 metrics
- Summary metrics、Failure Taxonomy、Eligibility 与模型修订信息
- Comparison 的选择结果与限制说明

只允许忽略显式声明的运行时字段：

- `generated_at`
- `latency_ms`
- `average_latency_ms`
- `corpus_embedding_build_ms`
- `cache_hit_count`
- `cache_miss_count`

## 17. 当前状态

当前尚未运行正式 v2 实验，也不能据此声称 v2 性能提升。

Runner 只提供：

- 计划能力
- 结构验证
- 假烟测试
- 离线模型探测
- Formal Readiness
- 正式结果缺失状态检查
- 正式结果发布后的严格 Check 能力

## 18. 与 Architecture C 的关系

Architecture C 当前仍未接入 Retrieval Benchmark v2。

在正式 v2 结果冻结并完成方法选择之前，不应把 v2 Retriever 结论直接接入 Architecture C。
