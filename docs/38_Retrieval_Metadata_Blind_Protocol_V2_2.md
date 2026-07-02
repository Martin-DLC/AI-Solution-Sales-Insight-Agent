# Retrieval Metadata Blind Authoring Protocol v2.2

## 1. Why v2.2 Exists

- Blind Attempt 1 failed and remains permanently frozen.
- Metadata Contract v2.2 analysis concluded that we do not need a new enum or a new runtime field.
- The minimum change is guide-and-protocol clarification only.
- This phase builds the blind packet for Attempt 2, but does not perform any labeling or evaluation.

## 2. What Changes Relative to v2.1

- Keep the same three modes: `primary_in_scope`, `full_applicable_scope`, `global_reusable`.
- Do not add `any_applicable_scope`.
- Do not add runtime fields.
- Tighten the guide so annotators judge only solution-scope dependency, not topic or document class.

## 3. Blind Boundary

- Packet generation reads only KB documents, KB chunks, demo solution scope, and schema structure.
- Packet generation must not read retrieval cases, queries, gold, formal results, Attempt 1 labels, Attempt 1 evaluation, or failure pairs.
- The blind bundle must not expose mapping, original IDs, Attempt 1 opaque IDs, or any failure evidence.

## 4. Opaque ID Design

- Salt label: `retrieval-metadata-blind-v2.2-attempt-2`
- Document opaque IDs use prefix `DOC-AUTH2-...`.
- Chunk opaque IDs use prefix `CHUNK-AUTH2-...`.
- Opaque IDs are deterministic but carry no business meaning.
- Mapping stays in tracked artifacts only and never enters the blind bundle.

## 5. Solution Scope Dependency Only

Annotators must answer exactly one question:

> This evidence, at the solution-scope layer, depends on the primary solution only, all applicable solutions together, or no specific solution at all?

This question must be answered without using:

- document_type
- industries
- tags
- effective_on
- security / compliance / readiness topic names
- the fact that a candidate is labeled `cross_cutting_requirement`
- the fact that a candidate is labeled `multi_solution`

Those conditions are handled by existing runtime filters and are not encoded into `runtime_scope_match_mode`.

## 6. Allowed Modes

### primary_in_scope

- Use when the core conclusion is anchored to the primary solution.
- Other solutions may appear as context, optional integration, downstream dependency, or affected system.
- Mentioning multiple solutions does not automatically force `full_applicable_scope`.

### full_applicable_scope

- Use only when the core conclusion requires every applicable solution to be present together.
- Typical semantics: joint delivery, end-to-end dependency, combined implementation, or a relationship claim that breaks if one participating solution is missing.
- Do not choose this mode merely because the candidate is about security, readiness, multi-solution, or cross-cutting requirements.

### global_reusable

- Use when the core conclusion is independent of which solution is currently in operational scope.
- Runtime filters may still restrict use by document type, industry, tags, date, or excluded solutions.

## 7. Required Decision Order

Annotators must follow this order exactly:

1. Ignore document_type, industries, tags, and effective_on.
2. Judge only solution-scope dependency.
3. If the conclusion is independent of specific solutions, choose `global_reusable`.
4. Else, if the conclusion remains valid when only the primary solution is in scope, choose `primary_in_scope`.
5. Else, if the conclusion requires all applicable solutions together, choose `full_applicable_scope`.
6. Else, mark `manual_review_required = true` and do not guess.

## 8. Document Default + Chunk Override

- Continue using `document_default_with_chunk_override`.
- Document Default captures the majority dependency across the document.
- Any chunk with a different dependency must override.
- Override count must not be artificially minimized.

## 9. Abstract Examples

### primary_in_scope example

> An order assistant must complete identity verification before calling a refund API. An identity system can provide the verification capability.

The core conclusion constrains the order assistant. The identity system is context or dependency, not a jointly required scope condition.

### full_applicable_scope example

> A joint workflow is reliable only after both the service platform and order platform finish two-way event synchronization.

The core conclusion depends on both solutions together.

### global_reusable example

> All production knowledge documents must preserve a version number and effective date.

The rule does not depend on a specific solution being in operational scope.

### Common traps

- Security requirements are not automatically `full_applicable_scope`.
- Mentioning multiple solutions is not automatically `full_applicable_scope`.
- `cross_cutting_requirement` is not automatically `global_reusable`.
- `readiness_requirement` is not automatically `full_applicable_scope`.

## 10. Label Template Rules

- All mode fields remain null until a human author fills them.
- Rationales must explain:
  - what the core conclusion is anchored to,
  - whether the conclusion still holds without other applicable solutions,
  - why the other two modes were rejected.

## 11. Why This Session Must Not Label Attempt 2

- The current session already knows Attempt 1 outcomes and v2.2 design conclusions.
- Therefore it may build the packet, but it cannot act as an independent blind labeler.

## 12. Next Step After This Packet

1. Move the blind bundle into an isolated labeling workflow.
2. Complete Attempt 2 labels without reading cases, gold, or results.
3. Freeze labels.
4. Run the one and only Attempt 2 evaluation.
5. Stop boundary-contract research after Attempt 2, regardless of pass or fail.

