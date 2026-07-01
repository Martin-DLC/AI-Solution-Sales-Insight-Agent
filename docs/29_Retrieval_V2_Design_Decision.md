# Retrieval V2 Design Decision

## 为什么不能直接实现 Hard Filter

- 当前正式 Recall@5 分别为 Lexical 0.8854166666666666、Vector 0.8697916666666666、Hybrid 0.8854166666666666。
- Top-20 上界显示：Lexical 只有 13/16 个 case 在 Top-20 达到 full recall；Vector 和 Hybrid 也只有 15/16。
- 因此即使在 Top-20 内做完美无 Gold Rerank，也无法让全部方法通过 recall gate。

## Top-20 上界说明

- lexical_v1: best_runtime_safe_recall_at_5=0.8854166666666666, boundary_rate=0.1875, strategy=S0, pool=5, diversity=no_diversity, rerank=original_rank
- vector_v1: best_runtime_safe_recall_at_5=0.8697916666666666, boundary_rate=0.1875, strategy=S0, pool=5, diversity=no_diversity, rerank=original_rank
- hybrid_v1: best_runtime_safe_recall_at_5=0.8854166666666666, boundary_rate=0.125, strategy=S0, pool=5, diversity=no_diversity, rerank=original_rank

## Boundary Runtime 可执行性

- total_boundary_violating_candidates: 24
- runtime_identifiable_boundary_candidates: 24
- evaluation_only_boundary_candidates: 0
- metadata_error_candidates: 0
- ranking_only_boundary_candidates: 0
- cross_cutting_scope_overlap can use applicable_solution_ids + operational_solution_scope only: true
- recommended eligibility semantics: strict_applicable_subset_with_global_policy_exception
- benchmark_has_runtime_inexecutable_boundary: false

## evaluation-only 规则问题

- evaluation_only dependency fields: none
- missing runtime-equivalent fields: none

## Scope 策略 S0-S4

### S0

- oracle_only: false
- summary: Current runtime eligibility: exclude explicit excluded-scope overlap and disjoint non-global candidates.

### S1

- oracle_only: false
- summary: Strict applicable subset with global-policy exception.

### S2

- oracle_only: false
- summary: Primary-solution match for solution-specific/multi-solution plus strict subset for cross-cutting requirements.

### S3

- oracle_only: false
- summary: S1 plus runtime document type, industry, tag, and effective-date checks.

### S4

- oracle_only: true
- summary: Evaluation-only oracle using benchmark gold boundary rules. For theoretical upper bound only.

## Candidate Pool 矩阵

- pool_5: best=hybrid_v1 / S0 / no_diversity / original_rank (recall_at_5=0.8854166666666666, boundary=0.125)
- pool_10: best=hybrid_v1 / S0 / no_diversity / original_rank (recall_at_5=0.8854166666666666, boundary=0.125)
- pool_20: best=hybrid_v1 / S0 / no_diversity / original_rank (recall_at_5=0.8854166666666666, boundary=0.125)

## Document Diversity 矩阵

- no_diversity: best=hybrid_v1 / S0 / pool_5 / original_rank (recall_at_5=0.8854166666666666, boundary=0.125)
- max_2_chunks_per_document: best=hybrid_v1 / S0 / pool_5 / original_rank (recall_at_5=0.8854166666666666, boundary=0.125)
- max_1_chunk_per_document: best=vector_v1 / S0 / pool_10 / runtime_scope_fit (recall_at_5=0.5260416666666666, boundary=0.125)

## Runtime Scope Fit Rerank 结果

- runtime_scope_fit_rerank materially supported: false
- best runtime-safe strategy: hybrid_v1 / S0 / pool_5 / no_diversity / original_rank

## 最佳 Runtime-safe 组合

- recall_at_5: 0.8854166666666666
- solution_boundary_violation_rate: 0.125
- failed_case_ids: RET2-005, RET2-006
- eligible_for_rag: false
- best_zero_boundary_runtime_safe: vector_v1 / S1 / pool_10 / no_diversity / original_rank (recall_at_5=0.84375, boundary=0.0)

## Oracle 上界

- vector_v1 / S4 / pool_10 / no_diversity / original_rank
- recall_at_5: 0.9375
- solution_boundary_violation_rate: 0.0
- eligible_for_rag: false

## 无法通过 Rerank 解决的 Case

### hybrid_v1

- RET2-015: recall_at_20=1.0, missing_items=KB-CASE-001, causes=not_in_top_20
- RET2-016: recall_at_20=1.0, missing_items=KB-CASE-002, causes=not_in_top_20

### lexical_v1

- RET2-005: recall_at_20=0.6666666666666666, missing_items=KB-CAP-001#chunk-001-bcb4fc0bf316, causes=lexical_term_mismatch
- RET2-010: recall_at_20=0.75, missing_items=KB-SOL-006, causes=lexical_term_mismatch
- RET2-015: recall_at_20=1.0, missing_items=KB-CASE-001, causes=lexical_term_mismatch
- RET2-016: recall_at_20=1.0, missing_items=KB-CASE-002, causes=lexical_term_mismatch

### vector_v1

- RET2-015: recall_at_20=1.0, missing_items=KB-CASE-001, causes=vector_semantic_mismatch
- RET2-016: recall_at_20=1.0, missing_items=KB-CASE-002, causes=vector_semantic_mismatch

## 是否需要 Runtime 合同 v2.1

- runtime_contract_upgrade_required: false

## 是否需要 Candidate Generation v2

- candidate_generation_upgrade_required: true

## 是否支持 Document Diversity

- document_diversity_supported: false

## 为什么不换 Embedding

- 当前没有证据表明更换 embedding 模型是跨 case 主瓶颈。
- Top-20 gap 主要由 candidate generation 缺口、同文档拥挤和 boundary 资格控制共同造成。

## Retriever v2 最小实现范围

- recommended_next_step: implement_runtime_safe_scope_control_and_upgrade_candidate_generation
- retriever_v2_ready_for_implementation: false

## Architecture C 仍被阻断

- architecture_c_status: blocked

## 合成数据和小样本限制

- This analysis reuses the frozen v2 benchmark inputs and frozen retriever parameters.
- Top-20 candidates are regenerated offline from the existing diagnostic path because the tracked diagnosis artifact stores summaries instead of full top-20 candidates.
- S4 is an oracle-only upper bound and must not be used as a production recommendation.
- This matrix evaluates deterministic filtering, diversity, and rerank policy only; it does not modify formal results or production retrievers.
