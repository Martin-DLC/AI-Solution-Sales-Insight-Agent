# Retrieval Metadata Contract v2.2 Design

## 1. P0失败摘要

- Relevant Retention: `0.96875`
- Boundary Removal: `0.9386666666666666`
- False Exclusion: `2`
- False Inclusion: `23`
- Unique error candidates: `11`

## 2. 为什么不能回改Attempt 1标签

- Blind Attempt 1 标签已经冻结，必须保持不可变。
- v2.2 只能作为新的P1设计假设，不能覆盖 v2.1 的 blind labels、evaluation 或 failure artifact。
- 下一次只能通过新协议版本和 Blind Attempt 2 验证。

## 3. 9个可由现有Mode修正的Candidate

- Existing three-mode schema already has a perfect alternative for `7` candidates that are currently misassigned.
- 这些问题属于 Blind Authoring Misclassification 或 Guide 歧义，不要求扩展 Runtime 合同。

## 4. 两个真正Unsatisfiable Candidate

- `KB-SEC-001#chunk-000-f8c40d662005`
- `KB-SEC-001#chunk-001-d88fdb994b4e`

## 5. 六组Observable State Conflict

- observable_state_conflict_count: `6`

## 6. any_applicable_scope实验

- solves_scope_only_unsatisfiable_candidates: `True`
- relevant_candidate_retention_rate: `1.0`
- boundary_candidate_removal_rate: `1.0`
- false_exclusion_count: `0`
- false_inclusion_count: `0`
- requires_new_enum_chunk_ids: `[]`

## 7. 单字段方案

- D0 perfect_candidate_count: `40` / 40
- D0 unsatisfiable_candidate_count: `0`
- D1 perfect_candidate_count: `40` / 40
- D1 unsatisfiable_candidate_count: `0`
- D2 perfect_candidate_count: `40` / 40
- D2 unsatisfiable_candidate_count: `0`

## 8. 双字段方案

- orthogonal field required for runtime matching: `False`
- evidence_relation changes allow/deny: `False`

## 9. 是否需要Runtime字段

- runtime_only_sufficient: `False`
- candidate_only_sufficient: `False`
- existing_candidate_plus_existing_runtime_sufficient: `True`
- paired_upgrade_required: `False`

## 10. 全40 Chunk可满足性

- all_40_have_perfect_assignment_under_best_variant: `True`
- schema_unsatisfiable_count: `0`
- ambiguous_assignment_count: `35`

## 11. 最小Schema结论

- best_schema_variant: `D0`
- minimum_required_change: `None` on `runtime_scope_match_mode`
- 当前最小结论不是增加第四个枚举，而是保留现有三值Schema，并在 Blind Protocol v2.2 中把现有 runtime filters 一并纳入可满足性验证。

## 12. Authoring定义

### any_applicable_scope（已验证但非必要）

- business_definition: 当 candidate 的 applicable_solution_ids 与当前 operational_solution_scope 存在非空交集时即可复用，只要 excluded_solution_ids 不冲突。
- positive_example: “某安全前置条件适用于方案A和方案B，只要当前场景正在讨论A或B中的任意一个，该前置条件都值得展示。”
- negative_example: “某能力说明只有当A和B同时都在当前范围内时才安全；仅命中其中一个时不能展示。”
- distinguish_from_primary_in_scope: `primary_in_scope` 只看 primary_solution_id；`any_applicable_scope` 允许 primary 之外的适用方案独立触发。
- distinguish_from_full_applicable_scope: `full_applicable_scope` 要求所有 applicable_solution_ids 全部进入当前 scope。

## 13. Document Default + Chunk Override

- document_default_supported: `True`
- chunk_override_supported: `True`

## 14. 向后兼容

- 保留旧三值枚举语义即可满足当前40个Chunk与640个Pair的反事实目标。
- D1 与 D2 都是可行但非必要的更改；D2 仅是更规范的重命名候选，不是当前最小迁移方案。

## 15. 为什么仍是P1设计假设

- evidence_classification: `P1_post_hoc_schema_design_not_blind_validated`
- blind_authoring_validated: `False`
- metadata_v2_2_ready_for_versioning: `False`

## 16. Blind Protocol v2.2条件

- ready_for_blind_protocol_v2_2: `True`
- 允许进入 Blind Protocol v2.2 设计，但不允许直接版本化或部署。

## 17. RET2-015/016独立Recall问题

- retriever_v2_status: `blocked_by_candidate_recall`
- Metadata v2.2 只解决 Boundary 合同，不解决 Candidate Recall。

## 18. Architecture C状态

- architecture_c_status: `blocked`

## 19. 两个Unsatisfiable Candidate逐Case摘要

### KB-SEC-001#chunk-000-f8c40d662005

- generic_business_meaning: A security/compliance evidence chunk centered on controlled-policy retrieval, whose safe visibility depends on both solution scope and existing runtime document-type eligibility.
- primary_mode_failure_reason: Under scope-only analysis it appears to fail, because some deny cases still contain the primary solution in runtime scope. Under the full existing runtime join, those deny cases are already blocked by document-type filters.
- full_mode_failure_reason: Fails because some allow cases only activate one applicable solution, so requiring every applicable solution creates false exclusions.
- global_mode_failure_reason: Under scope-only analysis it over-allows unrelated cases. Under the full existing runtime join it is also blocked by runtime filters, but that would be an unnecessarily weak authoring choice.
- any_applicable_scope_resolves: `True`

### KB-SEC-001#chunk-001-d88fdb994b4e

- generic_business_meaning: A security/compliance evidence chunk centered on controlled-policy retrieval, whose safe visibility depends on both solution scope and existing runtime document-type eligibility.
- primary_mode_failure_reason: Under scope-only analysis it appears to fail, because some deny cases still contain the primary solution in runtime scope. Under the full existing runtime join, those deny cases are already blocked by document-type filters.
- full_mode_failure_reason: Fails because some allow cases only activate one applicable solution, so requiring every applicable solution creates false exclusions.
- global_mode_failure_reason: Under scope-only analysis it over-allows unrelated cases. Under the full existing runtime join it is also blocked by runtime filters, but that would be an unnecessarily weak authoring choice.
- any_applicable_scope_resolves: `True`

