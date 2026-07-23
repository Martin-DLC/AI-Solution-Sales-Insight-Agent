# Provider Selection and Recovery Governance

## 1. Purpose

Provider selection and recovery governance explains evaluation-mode recommendations for Multi-MaaS runs. It answers why a provider/model may be suggested as primary, when retry or fallback is recommended, when human review is recommended, and when stop may be appropriate.

This is not production routing. It does not execute retry, provider fallback, compensation, or live model switching.

## 2. Selection Policies

Policies live in `config/maas_selection_policies.yaml`.

Current policies:

- `conservative_eval_policy`: favors clearer verification posture, dry-run passability, schema validity, and lower error rate.
- `cost_sensitive_eval_policy`: considers estimated cost only after structure and failure metrics are acceptable.
- `reliability_sensitive_eval_policy`: favors lower timeout and provider error rates.

All policies must keep:

- `mode: evaluation_only`
- `not_production_routing: true`
- `recommendations_only: true`

## 3. Candidate Ranking

Candidate ranking is derived from Multi-MaaS evaluation results. If all targets are `skipped_dry_run` or `skipped_missing_api_key`, the recommendation must not declare a strong primary provider. The expected status is `skipped_all_targets` or `insufficient_data`.

Ranking may be shown for transparency, but dry-run and skipped data cannot establish model quality.

## 4. Recovery Summary

Recovery summary counts retry, fallback, human review, and stop recommendations from evaluation results. It also counts provider unavailable, timeout, schema invalid, and unknown error cases.

The summary reuses existing recovery actions and result fields. It does not execute retry, fallback, compensation, or production routing.

## 5. Missing API Key Boundary

`skipped_missing_api_key` can be counted as fallback recommended because another provider may be needed for evaluation continuity. This is not a model quality failure and not proof that the provider is unavailable in production.

## 6. Cost Boundary

Estimated cost is not real billing. Cost-sensitive policy recommendations are evaluation-only and must not be treated as procurement, invoice, or pricing verification.

## 7. Reliability Boundary

Timeout rate and provider error rate in this framework are evaluation-run metrics. They are not SLA, uptime, or production stability claims.

## 8. Human Review and Stop

Human review may be recommended for high-risk cases, schema invalid outputs, provider unavailable results, repeated timeouts, or unknown errors. Stop recommendations are report-level governance signals only and do not stop a production workflow.

## 9. Production Boundary

Provider fallback recommendation is not production routing. A provider with `not_verified` status is not a completed MaaS integration. A selected primary provider is only an evaluation-mode recommendation.

## 10. Release Review

Before release, run the validation commands in `docs/MULTI_MAAS_V0_5_CHECKLIST.md` and confirm that selection recommendations remain evaluation-only and recovery recommendations do not execute retry, fallback, or compensation.
