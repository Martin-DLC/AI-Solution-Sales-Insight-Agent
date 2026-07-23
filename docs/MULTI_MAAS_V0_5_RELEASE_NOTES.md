# Multi-MaaS v0.5 Release Notes

## 1. Release Summary

v0.5 adds an offline-first Multi-MaaS Evaluation Foundation. It introduces an OpenAI-compatible MaaS adapter foundation, candidate provider config, dry-run smoke testing, a Multi-MaaS evaluation runner, evaluation-only provider selection, recovery recommendation summaries, and governance documentation.

No real MaaS API was accessed as part of this release note. Providers must not be described as production integrated. Selection recommendations are evaluation-only. Recovery recommendations do not execute real retry or fallback.

## 2. What Changed from Runtime Governance v0.1

Runtime Governance v0.1 provided local trace, recovery, observability, model provider abstraction, and evaluation boundaries. v0.5 builds on that foundation by adding a Multi-MaaS evaluation layer for provider/model readiness analysis.

The main agent workflow remains unchanged.

## 3. v0.5A Summary

- Added OpenAI-compatible MaaS adapter foundation.
- Added `config/maas_providers.yaml`.
- Added provider smoke test script.
- Added MaaS onboarding documentation.
- Added offline adapter tests.

## 4. v0.5B Summary

- Added `evaluation/multi_maas/`.
- Added seed evaluation cases.
- Added deterministic heuristic scoring.
- Added JSON / Markdown report generation.
- Added Multi-MaaS evaluation CLI.
- Added evaluation governance docs and tests.

## 5. v0.5C Summary

- Added selection policies in `config/maas_selection_policies.yaml`.
- Added evaluation-only candidate ranking.
- Added recovery recommendation summary.
- Added provider selection and recovery governance docs.
- Added selection/recovery tests.

## 6. New Files

- `agent/model_providers/openai_compatible.py`
- `config/maas_providers.yaml`
- `config/maas_selection_policies.yaml`
- `evaluation/multi_maas/`
- `scripts/run_maas_provider_smoke_test.py`
- `scripts/run_multi_maas_model_eval.py`
- `docs/MAAS_PROVIDER_ONBOARDING.md`
- `docs/MODEL_EVALUATION_GOVERNANCE.md`
- `docs/MULTI_MAAS_EVALUATION_REPORT_TEMPLATE.md`
- `docs/PROVIDER_SELECTION_AND_RECOVERY_GOVERNANCE.md`
- `docs/MULTI_MAAS_EVALUATION_PLAYBOOK.md`
- `docs/MULTI_MAAS_V0_5_CHECKLIST.md`
- `tests/test_openai_compatible_maas_provider.py`
- `tests/test_multi_maas_model_eval.py`
- `tests/test_maas_provider_selection_recovery.py`

## 7. Updated Files

- `README.md`
- `docs/ARCHITECTURE_OVERVIEW.md`
- `docs/MODEL_PROVIDER_STRATEGY.md`
- `docs/MULTI_MAAS_EVALUATION_PLAN.md`
- `docs/MAAS_PROVIDER_ONBOARDING.md`
- `docs/MODEL_EVALUATION_GOVERNANCE.md`
- `docs/MULTI_MAAS_EVALUATION_REPORT_TEMPLATE.md`
- `docs/PROVIDER_SELECTION_AND_RECOVERY_GOVERNANCE.md`

## 8. New CLI Commands

```bash
./.venv/bin/python scripts/run_maas_provider_smoke_test.py --provider cubexai --dry-run --check
./.venv/bin/python scripts/run_multi_maas_model_eval.py --dry-run --check
./.venv/bin/python scripts/run_multi_maas_model_eval.py --dry-run --check --selection-policy conservative_eval_policy
./.venv/bin/python scripts/run_multi_maas_model_eval.py --provider cubexai --dry-run --check --selection-policy conservative_eval_policy
```

## 9. Evaluation Metrics

- status counts
- schema_valid_rate
- usage_available_rate
- estimated_cost
- latency_ms
- provider_error_rate
- timeout_rate
- retry_recommended_count
- fallback_recommended_count
- human_review_trigger_count
- selection recommendation status

## 10. Boundary Notes

- Current commands are offline-first and dry-run by default.
- Current providers are not production integrated.
- Skipped and dry-run results are not model quality results.
- Heuristic scoring is not human scoring.
- Estimated cost is not real billing.
- Provider selection recommendation is not production routing.
- Recovery recommendation does not execute real retry or fallback.

## 11. Validation Results Placeholder

Latest reported local validation for v0.5A-C included passing adapter, Multi-MaaS runner, selection/recovery, fallback/recovery, and observability tests, plus dry-run CLI checks. Re-run the checklist commands before tagging a release and record fresh results in the release checklist.
