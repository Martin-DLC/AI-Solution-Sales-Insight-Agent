# Multi-MaaS Evaluation Report Template

## 1. Run Summary

- `run_id`
- `created_at`
- `dry_run`
- `total_cases`
- `total_targets`
- `total_runs`

## 2. Provider / Model Targets

For each target:

- `provider_name`
- `model_name`
- `adapter_type`
- `verification_status`
- `api_key_env`
- `dry_run`

## 3. Evaluation Status Counts

- `success_count`
- `skipped_count`
- `failed_count`
- per-status counts when available

## 4. Metrics Summary

- `schema_valid_rate`
- `usage_available_rate`
- `average_latency_ms`
- `average_estimated_cost`
- `provider_error_rate`
- `timeout_rate`

## 5. Per-provider Summary

Summarize total runs, successful runs, skipped runs, failed runs, schema validity, usage availability, latency, and provider error rate by provider/model target.

## 6. Per-case Results

For each case/provider/model result:

- `case_id`
- `provider_name`
- `model_name`
- `status`
- `schema_valid`
- `expected_fields_present`
- `answer_quality_score`
- `evidence_grounding_score`
- `recommended_recovery_action`

## 7. Recovery Recommendation Summary

- `retry_recommended_count`
- `fallback_recommended_count`
- `human_review_trigger_count`

## 8. Boundary Notes

Every report must state:

- `skipped_missing_api_key` is not a model quality failure conclusion.
- `skipped_dry_run` is not a model quality result.
- Heuristic score does not represent human scoring.
- Estimated cost is not real billing.
- `not_verified` provider status does not mean MaaS integration is complete.
- Provider fallback recommendation is not production routing.

## 9. Release Use

For v0.5 release review, pair this template with:

- `docs/MULTI_MAAS_EVALUATION_PLAYBOOK.md`
- `docs/MULTI_MAAS_V0_5_CHECKLIST.md`
