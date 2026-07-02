# Retrieval Runtime Boundary Contract V2.1

## 证据等级

- evidence_classification: P1_content_explainable_not_blind_validated
- contract_status: feasible_contract_hypothesis
- blind_authoring_validated: false
- independent_validation_completed: false
- deployment_validated: false
- ready_for_blind_authoring: true

## 证据等级与设计阶段泄漏限制

- `runtime_scope_match_mode` 的推导函数当前不直接读取 Gold。
- 同一 Candidate 的 mode 在当前实现中跨 Case 静态，不依赖 case_id 或 Candidate ID 硬编码。
- 但本提案的规则形成过程读取了 Cases、Evaluation Gold、Boundary 标签和 Separability conflict clusters。
- 因此当前结果属于 post-hoc design 风险下的反事实支持证据，不构成盲标验证或独立部署验证。
- 下一步需要仅基于 KB 内容的 Blind Authoring Packet、标签冻结和独立评估。
- RET2-015 / RET2-016 仍是独立的 Recall 工作流问题。
- Architecture C 继续 blocked。

## 为什么Runtime可识别不等于可分离

- Strict Filter 能识别并过滤部分或全部违规候选，但现有字段组合会误伤合法 Relevant。
- 误伤的根因不是单一排序问题，而是缺少“候选如何与局部 solution scope 匹配”的静态合同。

## 当前字段Joinability

- comparable_pairs: 9 / 66
- 现有最强可比链路：solution scope -> primary/applicable/excluded，document types -> document_type，industry -> industries，tags -> tags。
- 缺失链路：没有字段表达 candidate 对“部分 operational scope”是可复用还是必须全量命中。

## Strict Filter误伤原因

- S1误伤18个 Relevant Candidate。
- S3误伤30个 Relevant Candidate。
- cross-cutting 与 multi-solution 证据中，部分记录应允许 primary solution in scope 即可复用，部分记录则必须 full applicable scope 才安全。

## Cross-cutting证据语义

- 不是所有 applicable_solution_ids 包含 scope 外 solution 的 cross-cutting 证据都应视为越界。
- 安全与合规类 shared prerequisite 证据可以服务单一 solution scope。
- unsupported / readiness 类跨方案约束如果需要依赖全部适用方案共同成立，则 partial overlap 不安全。

## Multi-solution证据语义

- multi-solution 证据至少分成两类：
  - `primary_in_scope` 即可复用：实施 Playbook、参考案例。
  - `full_applicable_scope` 才安全：需要所有列出方案共同成立的能力说明或边界说明。

## 冲突簇

- CC-001: requires_both_sides=false, missing_runtime_signal=False, missing_candidate_signal=True
- CC-002: requires_both_sides=false, missing_runtime_signal=False, missing_candidate_signal=True
- CC-003: requires_both_sides=false, missing_runtime_signal=False, missing_candidate_signal=True

## Runtime-only方案

- C1 retention=1.0, boundary_removal=0.25, deployable=false

## Metadata-only方案

- C2 retention=1.0, boundary_removal=1.0, candidate_recall_at_20=0.96875, deployable=false, validated_contract=false, hypothesis_supported=true

## Paired方案

- C3 retention=1.0, boundary_removal=1.0, deployable=false

## Oracle上界

- C4 retention=1.0, boundary_removal=1.0, runtime_rule_uses_gold=true

## 推荐合同字段

- runtime_scope_match_mode (candidate): values=primary_in_scope, full_applicable_scope, global_reusable
- requested_evidence_roles (runtime): values=solution_capability, shared_prerequisite, integration_dependency, reference_case, readiness_gate, unsupported_boundary

## 字段来源和维护责任

- 当前拟议的最小升级范围仍是 candidate/knowledge metadata 字段，不新增 runtime schema 字段。
- 推荐粒度：document_default_with_chunk_override。
- Document 层提供默认值，Chunk 层允许覆盖；`KB-CAP-001` 已显示 document-only 粒度可能过粗。
- Chunk override 必须是静态 Knowledge Metadata，不得随 Case 变化。
- 当前不要求新增 runtime 字段。

## Migration设计

- Author runtime_scope_match_mode for candidate records using knowledge-authoring review of cross-cutting and multi-solution documents/chunks.
- Preserve a single static metadata value per candidate; do not vary the field by retrieval case.
- Backfill v2.1 metadata without touching frozen v2 benchmark data or formal result artifacts.

## 向后兼容策略

- backward_compatibility_status: design_incomplete
- default_behavior_status: pending_blind_authoring_design
- runtime: No new runtime field is required in the recommended variant; existing runtime_context remains backward compatible.
- candidate: Migration defaults are not finalized. Partial-overlap records, multi-solution evidence, and cross-cutting requirements still require blind authoring design before production rollout.
- manual_review_required_for: multi_solution, cross_cutting_requirement, ambiguous_document_chunk_semantics

## RET2-015/016为何仍是独立问题

- boundary_contract_resolves_ret2_015: false
- boundary_contract_resolves_ret2_016: false
- recall_workstream_still_required: true

## 是否可进入Retriever v2实现

- boundary_contract_ready_for_versioning: false
- proposed_upgrade_scope: knowledge_metadata_only_v2_1
- final_upgrade_scope_decision: pending_blind_authoring_validation
- recommended_next_step: build_blind_authoring_packet_freeze_labels_and_evaluate
- retriever_v2_ready_for_implementation: false

## Architecture C状态

- architecture_c_status: blocked
