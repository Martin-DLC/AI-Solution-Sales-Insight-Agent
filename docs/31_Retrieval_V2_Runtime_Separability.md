# Retrieval V2 Runtime Separability

## Runtime可识别与可分离的区别

- `24/24` 个违规候选可由 Runtime 字段识别，并不自动意味着 Relevant Gold 可以零误伤保留。
- runtime_contract_upgrade_required: true

## Strict Filter误伤分析

- S1: total_filtered=42, correctly_filtered_boundary=24, incorrectly_filtered_relevant=18, retention=0.90625, boundary_removal=1.0
- S2: total_filtered=0, correctly_filtered_boundary=0, incorrectly_filtered_relevant=0, retention=1.0, boundary_removal=0.0
- S3: total_filtered=36, correctly_filtered_boundary=6, incorrectly_filtered_relevant=30, retention=0.84375, boundary_removal=0.25

## 通用Runtime规则R0-R5

- R0 / lexical_v1: recall@20=0.96875, boundary=0.1875, forbidden=0.0, false_positive=0, false_negative=0
- R0 / vector_v1: recall@20=0.96875, boundary=0.1875, forbidden=0.0, false_positive=0, false_negative=0
- R0 / hybrid_v1: recall@20=0.96875, boundary=0.1875, forbidden=0.0, false_positive=0, false_negative=0
- R1 / lexical_v1: recall@20=0.875, boundary=0.0, forbidden=0.0, false_positive=6, false_negative=0
- R1 / vector_v1: recall@20=0.875, boundary=0.0, forbidden=0.0, false_positive=6, false_negative=0
- R1 / hybrid_v1: recall@20=0.875, boundary=0.0, forbidden=0.0, false_positive=6, false_negative=0
- R2 / lexical_v1: recall@20=0.96875, boundary=0.3125, forbidden=0.0, false_positive=0, false_negative=8
- R2 / vector_v1: recall@20=0.96875, boundary=0.3125, forbidden=0.0, false_positive=0, false_negative=8
- R2 / hybrid_v1: recall@20=0.96875, boundary=0.3125, forbidden=0.0, false_positive=0, false_negative=8
- R3 / lexical_v1: recall@20=0.8125, boundary=0.25, forbidden=0.0, false_positive=10, false_negative=6
- R3 / vector_v1: recall@20=0.8125, boundary=0.25, forbidden=0.0, false_positive=10, false_negative=6
- R3 / hybrid_v1: recall@20=0.8125, boundary=0.25, forbidden=0.0, false_positive=10, false_negative=6
- R4 / lexical_v1: recall@20=0.96875, boundary=0.3125, forbidden=0.0, false_positive=0, false_negative=8
- R4 / vector_v1: recall@20=0.96875, boundary=0.3125, forbidden=0.0, false_positive=0, false_negative=8
- R4 / hybrid_v1: recall@20=0.96875, boundary=0.3125, forbidden=0.0, false_positive=0, false_negative=8
- R5 / lexical_v1: recall@20=0.96875, boundary=0.1875, forbidden=0.0, false_positive=0, false_negative=0
- R5 / vector_v1: recall@20=0.96875, boundary=0.1875, forbidden=0.0, false_positive=0, false_negative=0
- R5 / hybrid_v1: recall@20=0.96875, boundary=0.1875, forbidden=0.0, false_positive=0, false_negative=0

## RET2-015语义可分离性

- classification: unknown
- expected_ranks_by_method: {'lexical_v1': {'KB-CASE-001': None, 'KB-CASE-001#chunk-000-d5868a3597d2': 1, 'KB-CASE-001#chunk-001-77cb36877788': 2, 'KB-SOL-003': 3}, 'vector_v1': {'KB-CASE-001': None, 'KB-CASE-001#chunk-000-d5868a3597d2': 1, 'KB-CASE-001#chunk-001-77cb36877788': 2, 'KB-SOL-003': 3}, 'hybrid_v1': {'KB-CASE-001': None, 'KB-CASE-001#chunk-000-d5868a3597d2': 1, 'KB-CASE-001#chunk-001-77cb36877788': 2, 'KB-SOL-003': 3}}
- top_non_gold_candidate_ids: {'lexical_v1': ['KB-SOL-004#chunk-000-a8e1467e7923'], 'vector_v1': ['KB-SOL-004#chunk-001-d15a10f713d4'], 'hybrid_v1': ['KB-SOL-004#chunk-000-a8e1467e7923']}

## RET2-016语义可分离性

- classification: unknown
- expected_ranks_by_method: {'lexical_v1': {'KB-CASE-002': None, 'KB-CASE-002#chunk-000-2c2107739c83': 1, 'KB-CASE-002#chunk-001-036ea7b824d0': 2, 'KB-SOL-005': 3}, 'vector_v1': {'KB-CASE-002': None, 'KB-CASE-002#chunk-000-2c2107739c83': 1, 'KB-CASE-002#chunk-001-036ea7b824d0': 2, 'KB-SOL-005': 3}, 'hybrid_v1': {'KB-CASE-002': None, 'KB-CASE-002#chunk-000-2c2107739c83': 1, 'KB-CASE-002#chunk-001-036ea7b824d0': 2, 'KB-SOL-005': 3}}
- top_non_gold_candidate_ids: {'lexical_v1': ['KB-SOL-002#chunk-000-7c0d6600d6d0'], 'vector_v1': ['KB-SOL-002#chunk-000-7c0d6600d6d0'], 'hybrid_v1': ['KB-SOL-002#chunk-000-7c0d6600d6d0']}

## Query Clause Decomposition结果

- Q0: best_method=hybrid_v1, recall@20=0.8125, boundary=0.25
- Q1: best_method=vector_v1, recall@20=0.8125, boundary=0.25
- Q2_scope: best_method=lexical_v1, recall@20=0.8125, boundary=0.25
- Q2_document_types: best_method=lexical_v1, recall@20=0.8125, boundary=0.25
- Q2_all: best_method=lexical_v1, recall@20=0.8125, boundary=0.25
- Q3: best_method=hybrid_v1, recall@20=0.8125, boundary=0.25

## Runtime Context Augmentation结果

- Q2_scope: best_method=lexical_v1, RET2-015_rank={'lexical_v1': None, 'vector_v1': None, 'hybrid_v1': None}, RET2-016_rank={'lexical_v1': None, 'vector_v1': None, 'hybrid_v1': None}
- Q2_document_types: best_method=lexical_v1, RET2-015_rank={'lexical_v1': None, 'vector_v1': None, 'hybrid_v1': None}, RET2-016_rank={'lexical_v1': None, 'vector_v1': None, 'hybrid_v1': None}
- Q2_all: best_method=lexical_v1, RET2-015_rank={'lexical_v1': None, 'vector_v1': None, 'hybrid_v1': None}, RET2-016_rank={'lexical_v1': None, 'vector_v1': None, 'hybrid_v1': None}
- Q3: best_method=hybrid_v1, RET2-015_rank={'lexical_v1': None, 'vector_v1': None, 'hybrid_v1': None}, RET2-016_rank={'lexical_v1': None, 'vector_v1': None, 'hybrid_v1': None}

## Field-aware检索结果

- F0: best_method=hybrid_v1, recall@20=0.8125, boundary=0.25
- F1: best_method=vector_v1, recall@20=0.8125, boundary=0.25
- F2: best_method=lexical_v1, recall@20=0.8125, boundary=0.25
- F3: best_method=lexical_v1, recall@20=0.8125, boundary=0.25
- F4: best_method=vector_v1, recall@20=0.8125, boundary=0.25

## Parent-child / Sibling扩展结果

- F3 best_method=lexical_v1, RET2-015_rank={'lexical_v1': None, 'vector_v1': None, 'hybrid_v1': None}, RET2-016_rank={'lexical_v1': None, 'vector_v1': None, 'hybrid_v1': None}

## Document-type Partition结果

- F4 best_method=vector_v1, recall@20=0.8125, boundary=0.25

## 最佳通用组合

- R2 + Q0 + F1 / vector_v1: recall@20=0.96875, boundary=0.3125, forbidden=0.0

## 是否达到Candidate Recall@20=1

- retriever_v2_ready_for_implementation: false

## 是否Boundary=0

- best boundary rate: 0.3125

## 是否需要Metadata v2.1

- knowledge_metadata_upgrade_required: false

## 是否需要Benchmark Case v2.1

- benchmark_case_upgrade_required: false

## 是否支持确定性Query策略

- deterministic_query_strategy_supported: false

## 是否支持LLM Query Rewrite

- llm_query_rewrite_supported: true

## 为什么仍不更换Embedding

- 当前没有跨 case 证据表明 embedding model / revision 是主瓶颈。
- 当前主要矛盾仍是 runtime separability、query under-specification 和 field representation gap。

## Retriever v2是否可实现

- recommended_next_step: upgrade_runtime_or_knowledge_metadata_contracts_before_retriever_v2

## Architecture C状态

- architecture_c_status: blocked
