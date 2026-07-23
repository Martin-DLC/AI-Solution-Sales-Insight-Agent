# Multi-MaaS Evaluation Playbook

## 1. Purpose

This playbook explains how to prepare, smoke test, evaluate, report, and govern multiple MaaS providers and models without breaking the existing Agent Runtime Governance boundary.

It is for evaluation readiness. It does not modify the formal answer path, does not call real APIs by default, and does not create production routing.

## 2. Evaluation Principles

- Default offline / dry-run first.
- API keys must come from environment variables only.
- A skipped result is not a model quality result.
- A heuristic score is not a human score.
- Estimated cost is not billing.
- A provider recommendation is not production routing.
- A `not_verified` provider is not an integrated provider.

## 3. Provider Onboarding Flow

1. Add provider candidate to `config/maas_providers.yaml`.
2. Keep `verification_status` as `not_verified`.
3. Run dry-run smoke test.
4. Configure API key through an environment variable.
5. Run explicit smoke test.
6. Inspect response, usage, latency, and error mapping.
7. Mark provider as `smoke_test_passed` only after real evidence exists.
8. Add provider/model to evaluation target.
9. Run Multi-MaaS evaluation.
10. Review selection and recovery recommendation.

## 4. Smoke Test Workflow

Use:

```bash
./.venv/bin/python scripts/run_maas_provider_smoke_test.py --provider cubexai --dry-run --check
```

Smoke test modes:

- Dry-run mode returns a skipped dry-run result and does not access the network.
- Missing API key mode returns `skipped_missing_api_key` and does not fail the run.
- `--write` can write JSON and Markdown reports under `reports/`.
- `--check` validates structure only.

A smoke test pass is not production availability.

## 5. Multi-MaaS Evaluation Workflow

Use:

```bash
./.venv/bin/python scripts/run_multi_maas_model_eval.py --dry-run --check
```

The runner reads:

- `evaluation/multi_maas/cases.jsonl`
- `config/maas_providers.yaml`

It defaults to dry-run and can emit JSON / Markdown reports. Result statuses are separated:

- `success`
- `skipped_missing_api_key`
- `skipped_dry_run`
- `failed`
- `schema_invalid`
- `provider_unavailable`
- `timeout`

Skipped and dry-run statuses must not be interpreted as model quality outcomes.

## 6. Selection Policy Workflow

Selection policies live in `config/maas_selection_policies.yaml`:

- `conservative_eval_policy`
- `cost_sensitive_eval_policy`
- `reliability_sensitive_eval_policy`

All policies are:

- `evaluation_only`
- `recommendations_only`
- `not_production_routing`

If all results are skipped, the runner should not generate a strong primary recommendation.

## 7. Recovery Governance Workflow

The recovery summary reuses existing recovery concepts and maps evaluation results into recommended actions:

- `retry`
- `fallback`
- `human_review`
- `stop`

It does not execute real retry. It does not execute real provider fallback. It does not execute real compensation.

## 8. Report Interpretation Guide

Read reports in this order:

- Status counts show how many runs succeeded, skipped, or failed.
- `schema_valid_rate` is meaningful only for successful structured outputs.
- `usage_available_rate` shows whether usage metadata was returned.
- `estimated_cost` is optional and is not billing.
- Latency is an evaluation-run metric, not an SLA claim.
- `provider_error_rate` and `timeout_rate` are evaluation-run indicators.
- Recovery recommendation explains what action would be recommended.
- Selection recommendation explains evaluation-only candidate ranking.
- Boundary notes define what the report does not prove.

## 9. Before Real API Test Checklist

- API key is configured through an environment variable.
- `base_url` comes from official or platform-provided documentation.
- `model_id` is confirmed by the platform or operator.
- Timeout is set.
- Test case count is limited.
- Cost risk is explicit.
- `--write` is enabled only when a report should be persisted.
- Formal / LLM / human artifacts are not overwritten.
- Provider verification status is recorded.
- Smoke test and full evaluation are kept separate.

## 10. What This Playbook Does Not Prove

- It does not prove which model is best.
- It does not prove which MaaS platform is most stable.
- It does not prove production SLA.
- It does not prove real billing.
- It does not prove real ROI.
- It does not prove production automatic routing capability.
