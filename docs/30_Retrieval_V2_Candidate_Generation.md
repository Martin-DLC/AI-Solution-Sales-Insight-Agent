# Retrieval V2 Candidate Generation

## 为什么 Candidate Generation 是当前主瓶颈

- best_variant: G2 / vector_v1
- candidate_recall_at_20: 0.96875
- boundary_violation_rate_at_20: 0.3125
- forbidden_hit_rate_at_20: 0.0
- candidate_generation_ready: false

## 为什么后过滤不足

- lexical_v1: postfilter_recall_at_20=0.8072916666666666, prefilter_recall_at_20=0.8385416666666666, improved=true
- vector_v1: postfilter_recall_at_20=0.84375, prefilter_recall_at_20=0.875, improved=true
- hybrid_v1: postfilter_recall_at_20=0.828125, prefilter_recall_at_20=0.875, improved=true

## 当前候选生成实现审计

- retrieval_unit: chunk for lexical, vector, and hybrid
- lexical_scoring_fields: content, citation_label, tags, industries, solution_ids, document_type
- vector_scoring_text: chunk.content only
- vector_query_prefix: query: 
- vector_document_prefix: passage: 
- title_participates_in_lexical_scoring: False
- summary_participates_in_lexical_scoring: False
- title_participates_in_vector_scoring: False
- summary_participates_in_vector_scoring: False
- section_heading_participates_in_lexical_scoring: only through citation_label
- section_heading_participates_in_vector_scoring: False
- parent_document_context_in_chunk_vector_representation: False
- runtime_filter_stage: before scoring, but only with legacy document_types / industries / solution_ids / tags / statuses / effective_on filters
- runtime_scope_metadata_used_before_scoring: False
- hybrid_merge_strategy: lexical top-20 union vector top-20, then fixed RRF dedupe by (document_id, chunk_id)
- candidate_pool_truncation: {'lexical': 'top_k on scored chunk list', 'vector': 'top_k on scored chunk list', 'hybrid': 'lexical_candidate_k=20 and vector_candidate_k=20 before fusion, then output_top_k=5'}

## RET2-005 分析

### lexical_v1

- expected_id=KB-CAP-001#chunk-001-bcb4fc0bf316, current_rank=None, prefilter_rank=None, root_cause=expected_sibling_chunk_substitution

## RET2-010 分析

### lexical_v1

- expected_id=KB-SOL-006, current_rank=None, prefilter_rank=None, root_cause=parent_document_signal_missing

## RET2-015 分析

### lexical_v1

- expected_id=KB-CASE-001, current_rank=None, prefilter_rank=None, root_cause=unknown_candidate_generation_cause

### vector_v1

- expected_id=KB-CASE-001, current_rank=None, prefilter_rank=None, root_cause=vector_semantic_mismatch

### hybrid_v1

- expected_id=KB-CASE-001, current_rank=None, prefilter_rank=None, root_cause=hybrid_candidate_union_gap

## RET2-016 分析

### lexical_v1

- expected_id=KB-CASE-002, current_rank=None, prefilter_rank=None, root_cause=unknown_candidate_generation_cause

### vector_v1

- expected_id=KB-CASE-002, current_rank=None, prefilter_rank=None, root_cause=vector_semantic_mismatch

### hybrid_v1

- expected_id=KB-CASE-002, current_rank=None, prefilter_rank=None, root_cause=hybrid_candidate_union_gap

## Pre-retrieval Filter 结果

- lexical_v1: recall@20=0.8385416666666666, full_recall_case_count_at_20=9, boundary_rate_at_20=0.0
- vector_v1: recall@20=0.875, full_recall_case_count_at_20=11, boundary_rate_at_20=0.0
- hybrid_v1: recall@20=0.875, full_recall_case_count_at_20=11, boundary_rate_at_20=0.0

## Representation Enrichment 结果

- lexical_v1: recall@20=0.96875, full_recall_case_count_at_20=14
- vector_v1: recall@20=0.96875, full_recall_case_count_at_20=14
- hybrid_v1: recall@20=0.96875, full_recall_case_count_at_20=14

## Document Retrieval 结果

- lexical_v1: recall@20=0.96875, full_recall_case_count_at_20=14
- vector_v1: recall@20=0.96875, full_recall_case_count_at_20=14
- hybrid_v1: recall@20=0.96875, full_recall_case_count_at_20=14

## Dual-granularity 结果

### G4

- lexical_v1: recall@20=0.96875, full_recall_case_count_at_20=14, boundary_rate_at_20=0.3125
- vector_v1: recall@20=0.96875, full_recall_case_count_at_20=14, boundary_rate_at_20=0.3125
- hybrid_v1: recall@20=0.96875, full_recall_case_count_at_20=14, boundary_rate_at_20=0.3125

### G5

- lexical_v1: recall@20=0.8541666666666666, full_recall_case_count_at_20=10, boundary_rate_at_20=0.0
- vector_v1: recall@20=0.875, full_recall_case_count_at_20=11, boundary_rate_at_20=0.0
- hybrid_v1: recall@20=0.96875, full_recall_case_count_at_20=14, boundary_rate_at_20=0.3125

### G6

- lexical_v1: recall@20=0.875, full_recall_case_count_at_20=11, boundary_rate_at_20=0.0
- vector_v1: recall@20=0.875, full_recall_case_count_at_20=11, boundary_rate_at_20=0.0
- hybrid_v1: recall@20=0.96875, full_recall_case_count_at_20=14, boundary_rate_at_20=0.3125

## 各变体 Top-5 / 10 / 20 Candidate Recall

### G0

- lexical_v1: recall@5=0.8854166666666667, recall@10=0.9322916666666667, recall@20=0.9322916666666667
- vector_v1: recall@5=0.8697916666666667, recall@10=0.96875, recall@20=0.96875
- hybrid_v1: recall@5=0.8854166666666667, recall@10=0.96875, recall@20=0.96875

### G1

- lexical_v1: recall@5=0.8072916666666666, recall@10=0.8385416666666666, recall@20=0.8385416666666666
- vector_v1: recall@5=0.84375, recall@10=0.875, recall@20=0.875
- hybrid_v1: recall@5=0.828125, recall@10=0.875, recall@20=0.875

### G2

- lexical_v1: recall@5=0.9010416666666667, recall@10=0.96875, recall@20=0.96875
- vector_v1: recall@5=0.921875, recall@10=0.96875, recall@20=0.96875
- hybrid_v1: recall@5=0.9166666666666667, recall@10=0.96875, recall@20=0.96875

### G3

- lexical_v1: recall@5=0.9166666666666667, recall@10=0.96875, recall@20=0.96875
- vector_v1: recall@5=0.9166666666666667, recall@10=0.96875, recall@20=0.96875
- hybrid_v1: recall@5=0.9010416666666667, recall@10=0.96875, recall@20=0.96875

### G4

- lexical_v1: recall@5=0.9166666666666667, recall@10=0.96875, recall@20=0.96875
- vector_v1: recall@5=0.9166666666666667, recall@10=0.96875, recall@20=0.96875
- hybrid_v1: recall@5=0.9010416666666667, recall@10=0.96875, recall@20=0.96875

### G5

- lexical_v1: recall@5=0.8229166666666666, recall@10=0.8541666666666666, recall@20=0.8541666666666666
- vector_v1: recall@5=0.859375, recall@10=0.875, recall@20=0.875
- hybrid_v1: recall@5=0.9010416666666667, recall@10=0.96875, recall@20=0.96875

### G6

- lexical_v1: recall@5=0.84375, recall@10=0.875, recall@20=0.875
- vector_v1: recall@5=0.859375, recall@10=0.875, recall@20=0.875
- hybrid_v1: recall@5=0.9010416666666667, recall@10=0.96875, recall@20=0.96875

## 是否达到 Candidate Recall@20 = 1

- candidate_generation_ready: false

## 是否需要 Rerank

- rerank_required: false

## 是否需要 Query Rewrite

- query_rewrite_required: true

## 是否支持 Embedding 变化

- embedding_change_supported: false

## 推荐最小方案

- recommended_next_step: continue_candidate_generation_diagnosis_before_query_rewrite

## Architecture C 仍为 blocked

- architecture_c_status: blocked

## 合成数据和小样本限制

- This analysis is diagnostic-only and does not modify formal retrieval results or production retrievers.
- All experiments reuse the frozen v2 dataset and frozen model configuration in strict offline mode.
- Gold is used only for evaluation; candidate generation and ranking variants do not consume gold IDs.
- Document-level retrieval and dual-granularity union are non-formal experiments for candidate-pool diagnosis only.
