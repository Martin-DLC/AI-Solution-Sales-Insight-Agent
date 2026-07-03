# Retrieval Metadata Blind Evaluation v2.1

## 1. P1 Contract Hypothesis Background

- Blind labels were authored from KB-only packet content in an isolated workspace and frozen before any effectiveness evaluation.
- This document records the first post-freeze independent validation pass and does not modify the frozen labels.

## 2. Blind Packet, Authoring, and Freeze Process

- Packet SHA-256: `314135ac2e1d73dc12980bc097fbbb1e58bf9117b044a47c5cbc19e44ac927a9`
- Guide SHA-256: `738a2afc587090de35b302a5575f23f66ac66119bf1e812b02e53138eecf16e7`
- Template SHA-256: `acd9ed60e0f945071f859f6b0f6d8f28dedd3ce23e9f8b2abf45e22d9428d79f`
- Labels SHA-256: `58729c71ba03adce96f7e89170a9bc52bf637a028a7cfb33f1acd1b504327e92`
- Authoring report SHA-256: `13fce4a4793b3854daeeba0f1d4786ffa72dbe64d9c6b7c6066b8333899ebbc3`

## 3. Why This Is the First Valid Evaluation

- Freeze status: `frozen_before_evaluation`
- Evaluation status before run: `not_started`
- Provenance gate passed: `True`

## 4. Input Hashes and Provenance

- Mapping SHA-256: `f271a15bb6ccce131374a3b7ccfedb107abfa0e2afad6aa4a5a739dc3cfc8518`
- Provenance blind-to-cases-and-gold: `True`
- Labels frozen before evaluation: `True`
- Labels modified after authoring: `False`

## 5. Opaque ID Mapping Integrity

- Opaque document coverage: `20` / `20`
- Opaque chunk coverage: `40` / `40`
- Mapping passed: `True`

## 6. Document Default + Chunk Override Results

- Document default mode counts: `{"full_applicable_scope": 8, "global_reusable": 1, "primary_in_scope": 11}`
- Effective chunk mode counts: `{"full_applicable_scope": 13, "global_reusable": 2, "primary_in_scope": 25}`
- Chunk override count: `3`

## 7. 640 Pair Evaluation Scope

- Case count: `16`
- Chunk count: `40`
- Pair count: `640`

## 8. Relevant Retention

- relevant_pair_count: `64`
- relevant_allowed_count: `62`
- relevant_denied_count: `2`
- relevant_candidate_retention_rate: `0.96875`

## 9. Boundary Removal

- boundary_violating_pair_count: `375`
- boundary_denied_count: `352`
- boundary_allowed_count: `23`
- boundary_candidate_removal_rate: `0.9386666666666666`

## 10. False Exclusion

- false_exclusion_count: `2`

## 11. False Inclusion

- false_inclusion_count: `23`

## 12. Benchmark Contract Conflict

- benchmark_contract_conflict_count: `0`

## 13. Per-Mode Results

### full_applicable_scope

- relevant retention: `0.8333333333333334`
- boundary removal: `1.0`
- pair_count: `208`

### global_reusable

- relevant retention: `None`
- boundary removal: `None`
- pair_count: `32`

### primary_in_scope

- relevant retention: `1.0`
- boundary removal: `0.9128787878787878`
- pair_count: `400`

## 14. Per-Scope-Type Results

### cross_cutting_requirement

- relevant retention: `1.0`
- boundary removal: `0.8198198198198198`
- pair_count: `192`

### global_policy

- relevant retention: `None`
- boundary removal: `None`
- pair_count: `32`

### multi_solution

- relevant retention: `0.8`
- boundary removal: `0.9651162790697675`
- pair_count: `160`

### solution_specific

- relevant retention: `1.0`
- boundary removal: `1.0`
- pair_count: `256`

## 15. P1 Counterfactual vs Blind Result

- P1 hypothesis retention: `1.0`
- P0 blind retention: `0.96875`
- P1 hypothesis removal: `1.0`
- P0 blind removal: `0.9386666666666666`
- hypothesis_replicated: `False`

## 16. Did P0 Pass?

- p0_validation_status: `failed`
- evidence_classification: `P1_content_explainable_not_blind_validated`

## 17. Can Metadata v2.1 Enter Migration Design?

- metadata_v2_1_versioning_status: `blocked_blind_validation_failed`

## 18. Why Retriever v2 Is Still Blocked by Recall

- This evaluation does not run any retriever and does not address RET2-015 / RET2-016 candidate recall gaps.
- retriever_v2_status: `blocked`

## 19. RET2-015 / RET2-016 Status

- ret2_015_016_status: `candidate_recall_unresolved`

## 20. Architecture C Status

- architecture_c_status: `blocked`

## 21. Failure Policy

- If P0 fails, the current frozen blind label snapshot must remain immutable. Any correction requires a new protocol version or a new blind authoring attempt.

## 22. Limitations

- This evaluation covers 16 cases x 40 chunks and does not run any retriever or alter ranking.
- RET2-015 and RET2-016 candidate recall limitations remain unresolved in this phase.
- full_runtime_eligible is reported separately so non-scope filters are not miscounted as scope-contract gains.
- If P0 fails, the current frozen blind label snapshot must remain immutable; any correction requires a new protocol version or new blind authoring attempt.

---

# Retrieval Metadata Blind Evaluation v2.2

## Attempt 2 Protocol Changes

- Attempt 2 keeps the same schema and mode enum, but changes the guide and protocol to isolate Solution Scope Dependency from other runtime filters.
- runtime_scope_match_mode now expresses only solution-scope dependency, while document_type, industries, tags, effective_on, and excluded_solution remain runtime filter responsibilities.
- Boundary research ends after this evaluation regardless of pass or fail, and Attempt 3 is not allowed.

## Freeze and Provenance

- protocol_version: `2.2`
- blind_attempt_number: `2`
- provenance_gate_passed: `True`
- labels_frozen_before_evaluation: `True`
- labels_modified_after_authoring: `False`
- authoring_process_was_blind_to_cases_and_gold: `True`

## Scope-only Metrics

- relevant_retention: `0.96875`
- boundary_removal: `0.7226666666666667`
- false_exclusion_count: `2`
- false_inclusion_count: `104`

## Full-runtime Metrics

- relevant_retention: `0.96875`
- boundary_removal: `0.9786666666666667`
- false_exclusion_count: `2`
- false_inclusion_count: `8`
- benchmark_contract_conflict_count: `0`

## Attempt 1 Comparison

- attempt_1_full_runtime_retention: `0.96875`
- attempt_2_full_runtime_retention: `0.96875`
- attempt_1_full_runtime_removal: `0.984`
- attempt_2_full_runtime_removal: `0.9786666666666667`
- guide_clarified_scope_runtime_responsibility: `True`
- guide_changed_assignment_distribution: `True`
- blind_performance_improved: `False`
- attempt_2_outperformed_attempt_1: `False`
- independent_reproducibility_improvement: `not_demonstrated`

The Attempt 2 guide is clearer about separating `runtime_scope_match_mode` from the other runtime filters, but the measured full-runtime metrics do not improve. Clearer process semantics do not imply better retrieval effectiveness, and independent reproducibility improvement is not demonstrated.

## P0 Conclusion

- p0_validation_status: `failed`
- evidence_classification: `P1_blind_attempt_2_failed`
- boundary_contract_validation_status: `failed`

## Boundary Research Final Status

- boundary_research_status: `closed_after_attempt_2_failed`
- further_blind_attempts_allowed: `False`
- labels_remain_immutable: `True`

## Retriever and Architecture C Status

- metadata_versioning_status: `blocked_with_known_limitations`
- retriever_v2_status: `blocked`
- ret2_015_016_status: `candidate_recall_unresolved`
- architecture_c_status: `blocked`
