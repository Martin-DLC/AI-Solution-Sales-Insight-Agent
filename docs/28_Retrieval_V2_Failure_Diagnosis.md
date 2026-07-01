# Retrieval Benchmark V2 Failure Diagnosis

## 为什么不能直接调参

- 当前诊断严格复用冻结的 v2 数据、算法和参数，只做诊断性 Top-20 扩展。
- 正式结果仍以冻结的 Top-5 正式 Artifact 为准。
- 任何改动建议都必须由本次证据链支持，不能先改再解释。

## 正式结果摘要

### lexical_v1

- recall_at_5: 0.8854166666666666
- solution_boundary_violation_rate: 0.1875
- eligible_for_rag: False
- failed_case_ids: RET2-005, RET2-006, RET2-009

### vector_v1

- recall_at_5: 0.8697916666666666
- solution_boundary_violation_rate: 0.1875
- eligible_for_rag: False
- failed_case_ids: RET2-005, RET2-006, RET2-009

### hybrid_v1

- recall_at_5: 0.8854166666666666
- solution_boundary_violation_rate: 0.125
- eligible_for_rag: False
- failed_case_ids: RET2-005, RET2-006

## Recall Gate 与 Boundary Gate

- 冻结 Gate 同时要求 summary recall_at_5 == 1.0、boundary violation rate == 0、forbidden hit rate == 0、request_error_count == 0，以及所有 case-level gate 通过。
- 本次诊断重点区分三类问题：候选召回不足、Top-5 排序 / 拥挤、以及 runtime scope 未提前拦截的 boundary 违规。

## 每条 Case Recall 可达性

- RET2-001: relevant_items=4, max_possible_recall_at_5=1.0, recall_gate_feasible=true, minimum_hits_gate_feasible=true
- RET2-002: relevant_items=4, max_possible_recall_at_5=1.0, recall_gate_feasible=true, minimum_hits_gate_feasible=true
- RET2-003: relevant_items=4, max_possible_recall_at_5=1.0, recall_gate_feasible=true, minimum_hits_gate_feasible=true
- RET2-004: relevant_items=4, max_possible_recall_at_5=1.0, recall_gate_feasible=true, minimum_hits_gate_feasible=true
- RET2-005: relevant_items=3, max_possible_recall_at_5=1.0, recall_gate_feasible=true, minimum_hits_gate_feasible=true
- RET2-006: relevant_items=4, max_possible_recall_at_5=1.0, recall_gate_feasible=true, minimum_hits_gate_feasible=true
- RET2-007: relevant_items=4, max_possible_recall_at_5=1.0, recall_gate_feasible=true, minimum_hits_gate_feasible=true
- RET2-008: relevant_items=4, max_possible_recall_at_5=1.0, recall_gate_feasible=true, minimum_hits_gate_feasible=true
- RET2-009: relevant_items=4, max_possible_recall_at_5=1.0, recall_gate_feasible=true, minimum_hits_gate_feasible=true
- RET2-010: relevant_items=4, max_possible_recall_at_5=1.0, recall_gate_feasible=true, minimum_hits_gate_feasible=true
- RET2-011: relevant_items=4, max_possible_recall_at_5=1.0, recall_gate_feasible=true, minimum_hits_gate_feasible=true
- RET2-012: relevant_items=4, max_possible_recall_at_5=1.0, recall_gate_feasible=true, minimum_hits_gate_feasible=true
- RET2-013: relevant_items=4, max_possible_recall_at_5=1.0, recall_gate_feasible=true, minimum_hits_gate_feasible=true
- RET2-014: relevant_items=4, max_possible_recall_at_5=1.0, recall_gate_feasible=true, minimum_hits_gate_feasible=true
- RET2-015: relevant_items=4, max_possible_recall_at_5=1.0, recall_gate_feasible=true, minimum_hits_gate_feasible=true
- RET2-016: relevant_items=4, max_possible_recall_at_5=1.0, recall_gate_feasible=true, minimum_hits_gate_feasible=true

## 三方法 Top-5 / Top-10 / Top-20 分析

### lexical_v1

- cases_recall_1_at_5: 9
- cases_recall_1_at_10: 13
- cases_recall_1_at_20: 13
- missing_items_not_in_top20: 0
- cases_affected_by_duplicate_crowding: 16
- cases_affected_by_scope_filter: 0

### vector_v1

- cases_recall_1_at_5: 9
- cases_recall_1_at_10: 15
- cases_recall_1_at_20: 15
- missing_items_not_in_top20: 0
- cases_affected_by_duplicate_crowding: 16
- cases_affected_by_scope_filter: 0

### hybrid_v1

- cases_recall_1_at_5: 9
- cases_recall_1_at_10: 15
- cases_recall_1_at_20: 15
- missing_items_not_in_top20: 2
- cases_affected_by_duplicate_crowding: 16
- cases_affected_by_scope_filter: 0

## Missing Gold 分布

- lexical_v1: duplicate_document_competition=2, lexical_term_mismatch=4, same_document_chunk_crowding=1
- vector_v1: duplicate_document_competition=5, same_document_chunk_crowding=1, vector_semantic_mismatch=2
- hybrid_v1: duplicate_document_competition=3, not_in_top_20=2, same_document_chunk_crowding=2

## 重复 Chunk 和 Document 拥挤

- lexical_v1: duplicate_document_case_count=16, same_document_chunk_crowding_case_count=16
- vector_v1: duplicate_document_case_count=16, same_document_chunk_crowding_case_count=16
- hybrid_v1: duplicate_document_case_count=16, same_document_chunk_crowding_case_count=16

## RET2-005 分析

- failing_methods: lexical_v1, vector_v1, hybrid_v1
- dominant_causes: cross_cutting_scope_overlap, evaluation_only_boundary_rule
- lexical_v1: 3 violating candidates
- vector_v1: 3 violating candidates
- hybrid_v1: 3 violating candidates

## RET2-006 分析

- failing_methods: lexical_v1, vector_v1, hybrid_v1
- dominant_causes: cross_cutting_scope_overlap
- lexical_v1: 4 violating candidates
- vector_v1: 4 violating candidates
- hybrid_v1: 4 violating candidates

## RET2-009 分析

- failing_methods: lexical_v1, vector_v1, hybrid_v1
- dominant_causes: evaluation_only_boundary_rule
- lexical_v1: 1 violating candidates
- vector_v1: 1 violating candidates
- hybrid_v1: 1 violating candidates

## Scope-aware Filter + Backfill 反事实

### lexical_v1

- counterfactual_summary_recall_at_5: 0.9166666666666667
- counterfactual_boundary_violation_rate: 0.1875
- counterfactual_failed_case_ids: RET2-005, RET2-006, RET2-009, RET2-010, RET2-011, RET2-014
- counterfactual_eligible_for_rag: false

### vector_v1

- counterfactual_summary_recall_at_5: 0.9010416666666667
- counterfactual_boundary_violation_rate: 0.1875
- counterfactual_failed_case_ids: RET2-005, RET2-006, RET2-009, RET2-010, RET2-014, RET2-016
- counterfactual_eligible_for_rag: false

### hybrid_v1

- counterfactual_summary_recall_at_5: 0.9166666666666667
- counterfactual_boundary_violation_rate: 0.125
- counterfactual_failed_case_ids: RET2-005, RET2-006, RET2-010, RET2-011, RET2-014, RET2-016
- counterfactual_eligible_for_rag: false

## 哪些 Boundary 可以运行时提前阻断

- runtime_preventable_cases: none

## 哪些问题属于排序

- ranking_dominated_case_ids: RET2-005, RET2-006, RET2-009, RET2-010, RET2-011, RET2-014, RET2-015, RET2-016

## 哪些问题属于候选召回

- candidate_recall_gap_case_ids: RET2-005, RET2-006, RET2-010, RET2-011, RET2-014, RET2-015, RET2-016

## 最小改进建议

- recommended_minimum_change: scope_aware_hard_filter_plus_candidate_pool_or_rerank
- secondary_change_if_needed: embedding_or_query_strategy_review_if_top20_gaps_persist

## 不建议立即实施的改动

- change_bm25_parameters
- change_embedding_model_or_revision
- change_rrf_parameters
- introduce_reranker_before_runtime_scope_control_is_evaluated
- modify_gold_or_benchmark_contracts

## Architecture C 仍被阻断

- architecture_c_status: blocked
- 当前没有方法通过冻结 Gate，因此仍不得接入 Architecture C。

## 数据规模与合成数据限制

- This diagnosis reuses the frozen v2 dataset and frozen retriever parameters.
- Top-20 runs are diagnostic-only and are not formal benchmark results.
- Vector and hybrid diagnostics require the frozen local embedding snapshot in strict offline mode.
- Counterfactual scope-aware filtering uses runtime context plus candidate scope metadata only.
