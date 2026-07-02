# Retrieval Metadata Blind Failure Analysis v2.1

## 1. Why This Failure Is Still Valuable

- The frozen blind labels remain immutable and now serve as permanent failure evidence.
- The analysis separates label quality, guide ambiguity, static-schema sufficiency, and runtime-matching limits.

## 2. Frozen Labels and No-Retroactive-Edit Policy

- source_blind_label_hash: `58729c71ba03adce96f7e89170a9bc52bf637a028a7cfb33f1acd1b504327e92`
- No frozen blind label, packet, guide, mapping, KB, case, or gold file is modified in this phase.

## 3. Technical Fix Audit

- pre_metric_technical_failure_occurred: `True`
- metrics_generated_before_fix: `True`
- labels_modified_during_fix: `False`
- mapping_content_changed: `False`

## 4. False Exclusions

- false_exclusion_count: `2`
- unique_false_exclusion_candidate_count: `2`
- affected_chunk_ids: `['KB-PLAY-001#chunk-000-0015819a0dd7', 'KB-PLAY-001#chunk-001-e90933b01fb0']`

## 5. False Inclusions

- false_inclusion_count: `23`
- unique_false_inclusion_candidate_count: `9`
- unique_candidates_with_existing_perfect_alternative: `['KB-CAP-001#chunk-000-4a0d2db10fea', 'KB-READY-001#chunk-000-c25bf83f023f', 'KB-READY-001#chunk-001-3b055dc87afd', 'KB-READY-002#chunk-000-be9fffe3ad6d', 'KB-READY-002#chunk-001-a9c933dcf327', 'KB-UNS-001#chunk-000-29c7c8c2317d', 'KB-UNS-001#chunk-001-6221cccec3f8']`
- unique_candidates_with_no_existing_perfect_mode: `['KB-SEC-001#chunk-000-f8c40d662005', 'KB-SEC-001#chunk-001-d88fdb994b4e']`

## 6. Unique Error Candidates

- unique_error_candidate_count: `11`

## 7. Three-mode Satisfiability

- candidates_with_alternative_perfect_existing_mode: `9`
- candidates_with_no_existing_mode_is_perfect: `2`

## 8. Authoring Misclassification

- count: `9`
- candidate_ids: `['KB-CAP-001#chunk-000-4a0d2db10fea', 'KB-PLAY-001#chunk-000-0015819a0dd7', 'KB-PLAY-001#chunk-001-e90933b01fb0', 'KB-READY-001#chunk-000-c25bf83f023f', 'KB-READY-001#chunk-001-3b055dc87afd', 'KB-READY-002#chunk-000-be9fffe3ad6d', 'KB-READY-002#chunk-001-a9c933dcf327', 'KB-UNS-001#chunk-000-29c7c8c2317d', 'KB-UNS-001#chunk-001-6221cccec3f8']`

## 9. Missing Chunk Override

- count: `0`

## 10. Schema Unsatisfiable Candidates

- count: `2`
- candidate_ids: `['KB-SEC-001#chunk-000-f8c40d662005', 'KB-SEC-001#chunk-001-d88fdb994b4e']`

## 11. Observable-state Conflicts

- count: `6`

## 12. Document Default and Chunk Heterogeneity

- documents_with_semantically_heterogeneous_chunks: `['KB-CAP-001', 'KB-INT-001', 'KB-PLAY-002']`
- chunk_override_rate_needed_for_perfect_existing_schema: `0.0`

## 13. Does Metadata v2.2 Need Design Work?

- metadata_v2_2_design_required: `True`
- metadata_v2_1_schema_status: `unsatisfiable_for_security_cross_cutting_candidates`

## 14. Guide-only Improvement or Schema Redesign?

- recommended_next_step: `design_metadata_contract_v2_2_then_run_new_blind_attempt`
- Most failing candidates have a perfect existing alternative mode, so the current blind labeling/guide layer is still a real problem.
- However, two security-compliance chunks remain unsatisfiable under all three frozen modes, so guide-only refinement is not enough.

## 15. Benchmark Contract Review

- benchmark_case_review_required: `False`
- Benchmark conflict count stays at 0; current evidence points to metadata expressiveness limits rather than direct gold contradiction.

## 16. Conditions for the Next Blind Attempt

- A new blind attempt is only appropriate after deciding whether v2.1 can be retained or v2.2 metadata design is required.
- Because unsatisfiable chunks exist, the recommended sequence is: diagnose contract gap -> define v2.2 candidate metadata direction -> then run a new blind attempt.

## 17. RET2-015 / RET2-016

- Candidate recall remains a separate unresolved issue and is not addressed by this metadata-only diagnosis.

## 18. Architecture C

- architecture_c_status: `blocked`
