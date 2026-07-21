# Fallback and Recovery

## 1. Why Fallback and Recovery Matter

Runtime governance needs a clear answer when something fails: retry, fall back, stop, ask for human review, or plan compensation. Batch 5 adds a local-first recovery foundation without executing real external side effects.

## 2. Error Taxonomy

Error categories:

- `model_error`
- `tool_error`
- `permission_error`
- `retrieval_error`
- `evaluation_error`
- `human_review_error`
- `runtime_error`
- `unknown`

Error types:

- `model_timeout`
- `model_schema_invalid`
- `model_unavailable`
- `tool_timeout`
- `tool_failed`
- `permission_denied`
- `retrieval_empty`
- `retrieval_boundary_failed`
- `evaluation_gate_failed`
- `human_review_timeout`
- `step_limit_exceeded`
- `consecutive_failure_limit_exceeded`
- `unknown_error`

## 3. Retry vs Fallback vs Stop vs Human Review

Retry is reserved for configured transient errors. Fallback is used when retry is exhausted or unsafe output should be replaced by a safer path. Stop is used for runtime policy limits and some critical failures. Human review is used for permission, evaluation, and high-risk cases.

## 4. Fallback Taxonomy

Fallback types:

- `retrieval_fallback`
- `model_fallback`
- `tool_fallback`
- `workflow_fallback`
- `human_fallback`
- `safe_response_fallback`

## 5. Recovery Decision Engine

`RecoveryDecisionEngine` returns a structured `RecoveryDecision` with error type, category, decision, fallback type, retry/stop/human flags, idempotency/compensation flags, reason, and safe-to-continue status.

It does not actually retry, switch live models, or execute compensation in this batch.

## 6. Idempotency Key

`IdempotencyKeyGenerator` can generate and validate local idempotency keys. Future write operations must carry an idempotency key. Batch 5 does not provide a database or deduplication store.

## 7. Rollback and Compensation

`CompensationPlan` is a schema and planning object only. It does not execute rollback. Since the current service does not perform real writes, compensation remains design-first.

## 8. What Is Not Implemented Yet

- Real retry execution.
- Real backoff sleep.
- Real rollback.
- Real external writes.
- Real compensation execution.
- Production incident workflow.
- Persistent idempotency store.

## 9. Known Limitations

This is a local-first recovery foundation. It does not claim production deployment, real billing, real provider reliability, or real operational recovery.
