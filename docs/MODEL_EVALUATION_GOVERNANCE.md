# Model Evaluation Governance

## 1. Scope

Multi-MaaS evaluation is an evaluation-mode framework for comparing provider/model execution status, schema behavior, usage availability, latency, estimated cost, and recovery recommendations. It is not production model routing and not a formal benchmark replacement.

## 2. Result Classes

- `success`: A provider returned a structured response through an explicit evaluation path.
- `skipped_missing_api_key`: The provider was not run because the required API key environment variable was absent.
- `skipped_dry_run`: The provider was intentionally not run because offline dry-run mode was enabled.
- `failed`: The evaluation path failed for a non-timeout, non-schema, non-unavailability reason.
- `schema_invalid`: The provider response did not satisfy the expected structured output shape.
- `provider_unavailable`: The provider was unavailable or live calls were disabled.
- `timeout`: The provider path timed out.

Skipped results and dry-run results must not be reported as model quality conclusions.

## 3. Artifact Separation

Multi-MaaS reports should be written to:

- `reports/multi_maas_model_eval.latest.json`
- `reports/multi_maas_model_eval.latest.md`

They must not overwrite formal retrieval artifacts, LLM deterministic baseline artifacts, provider comparison artifacts, or human evaluation artifacts.

## 4. Scoring Boundary

Current scoring is deterministic and heuristic. It checks schema parseability, expected field presence, output length, and risk-warning hints. It does not represent real human judgment, real business outcome, or formal evidence grounding.

When formal evidence is unavailable, evidence grounding must be treated as unavailable or heuristic only.

## 5. Provider Verification Boundary

`not_verified` does not mean a provider is unavailable. It means this repository has not completed verification for that provider. A smoke test pass does not prove production readiness. Evaluation-ready status must require explicit governance review in a later batch.

## 6. Recovery Boundary

Recovery recommendations reuse `RecoveryDecisionEngine` where possible. They are recommendations for evaluation reports only. They do not execute retry, fallback, compensation, or production routing.

## 7. Provider Selection Boundary

Provider selection policies are evaluation-only. Candidate ranking may explain why one provider/model looks preferable within a dry-run or evaluation report, but skipped and dry-run data cannot establish model quality. Fallback provider recommendations are not production routing.

## 8. Cost Boundary

Estimated cost is not real billing. Usage may be missing or provider-specific. Reports must keep usage availability and cost estimate status explicit.

## 9. Release Documentation

Use `docs/MULTI_MAAS_EVALUATION_PLAYBOOK.md` for the operating workflow and `docs/MULTI_MAAS_V0_5_CHECKLIST.md` before tagging a v0.5 release.
