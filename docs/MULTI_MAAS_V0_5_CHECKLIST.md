# Multi-MaaS v0.5 Checklist

## 1. Provider Config Readiness

- [ ] `config/maas_providers.yaml` exists.
- [ ] Provider candidates use environment variable names for API keys.
- [ ] Provider candidates are not marked as production integrated.
- [ ] `verification_status` reflects available evidence.

## 2. Adapter Readiness

- [ ] OpenAI-compatible adapter exists.
- [ ] Dry-run path does not access network.
- [ ] Missing API key path returns structured skipped result.
- [ ] Error mapping uses existing recovery taxonomy.

## 3. Smoke Test Readiness

- [ ] Smoke script supports `--provider`.
- [ ] Smoke script supports `--dry-run`.
- [ ] Smoke script supports `--check`.
- [ ] Smoke script can write JSON / Markdown reports when requested.

## 4. Evaluation Runner Readiness

- [ ] `evaluation/multi_maas/cases.jsonl` exists.
- [ ] Runner reads provider config and cases.
- [ ] Runner defaults to dry-run.
- [ ] Runner separates success, skipped, failed, schema invalid, provider unavailable, and timeout statuses.

## 5. Selection Policy Readiness

- [ ] `config/maas_selection_policies.yaml` exists.
- [ ] Policies are `evaluation_only`.
- [ ] Policies are `recommendations_only`.
- [ ] Policies set `not_production_routing: true`.
- [ ] All-skipped results do not produce a strong primary recommendation.

## 6. Recovery Governance Readiness

- [ ] Recovery summary exists.
- [ ] Retry recommendation count is reported.
- [ ] Fallback recommendation count is reported.
- [ ] Human review recommendation count is reported.
- [ ] No real retry, fallback, or compensation is executed.

## 7. Report Readiness

- [ ] JSON report can be generated.
- [ ] Markdown report can be generated.
- [ ] Report includes selection recommendation.
- [ ] Report includes recovery summary.
- [ ] Report includes boundary notes.

## 8. Boundary Check

- [ ] No real API keys are stored in the project.
- [ ] Skipped/dry-run results are not described as model quality results.
- [ ] Heuristic score is not described as human score.
- [ ] Estimated cost is not described as billing.
- [ ] Provider recommendation is not described as production routing.
- [ ] Provider candidates are not described as completed production integrations.

## 9. Validation Commands

```bash
./.venv/bin/python -m pytest tests/test_openai_compatible_maas_provider.py -q
./.venv/bin/python -m pytest tests/test_multi_maas_model_eval.py -q
./.venv/bin/python -m pytest tests/test_maas_provider_selection_recovery.py -q
./.venv/bin/python -m pytest tests/test_fallback_recovery_and_model_provider.py -q
./.venv/bin/python -m pytest tests/test_observability_and_cost.py -q

./.venv/bin/python scripts/run_maas_provider_smoke_test.py --provider cubexai --dry-run --check
./.venv/bin/python scripts/run_multi_maas_model_eval.py --dry-run --check
./.venv/bin/python scripts/run_multi_maas_model_eval.py --dry-run --check --selection-policy conservative_eval_policy
./.venv/bin/python scripts/run_multi_maas_model_eval.py --provider cubexai --dry-run --check --selection-policy conservative_eval_policy

git diff --check
git status --short
```

## 10. Release Commands

Suggested commands only. Do not run them until the release owner approves:

```bash
git tag v0.5.0-multi-maas-evaluation
git push origin v0.5.0-multi-maas-evaluation
```
