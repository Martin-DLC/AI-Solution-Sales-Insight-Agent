# MaaS Provider Onboarding

## 1. What is a MaaS Provider

A MaaS provider is a model-as-a-service endpoint that can receive model requests over a hosted API. In this repository, MaaS onboarding starts in evaluation mode only. A provider entry is a candidate for smoke tests and model evaluation, not a production integration.

## 2. Why OpenAI-compatible Adapter First

Many MaaS platforms expose an OpenAI-compatible request shape. Starting with an OpenAI-compatible adapter lets the project reuse the existing `BaseModelProvider` protocol, mock provider tests, recovery taxonomy, and evaluation reporting without creating a second provider system.

## 3. Provider Config Fields

Provider candidates live in `config/maas_providers.yaml`.

Core fields:

- `provider_name`
- `adapter_type`
- `model_name` or `model_id`
- `base_url` or `base_url_candidate`
- `api_key_env`
- `timeout_seconds`
- `max_retries`
- `default_headers`
- `supports_tool_calling`
- `supports_structured_output`
- `supports_streaming`
- `supports_long_context`
- `cost_profile`
- `latency_profile`
- `data_policy`
- `verification_status`

Candidate config must not include real API keys, real pricing claims, real latency claims, or real SLA claims.

## 4. API Key Handling

API keys must be read from environment variables named by `api_key_env`. Never write API keys into project files, tests, reports, or documentation. Missing keys are expected during offline development.

## 5. Dry-run and skipped_missing_api_key

Smoke tests default to offline-safe behavior. In dry-run mode, the result is `skipped_dry_run` and no network call is made. Without an API key, non-dry-run smoke tests return `skipped_missing_api_key` with a recovery recommendation instead of raising an unhandled exception.

## 6. Smoke Test Workflow

Use the smoke script in dry-run or check mode first:

```bash
./.venv/bin/python scripts/run_maas_provider_smoke_test.py --provider cubexai --dry-run --check
```

`--check` validates that a structured JSON and Markdown report can be generated. `--write` can write latest smoke reports under `reports/`, but skipped and dry-run results must not be treated as model quality results.

## 7. Error Mapping to RecoveryDecisionEngine

The adapter maps provider failures to the existing recovery taxonomy:

| Provider Condition | Recovery Error Type |
| --- | --- |
| Missing API key | `model_unavailable` |
| Timeout | `model_timeout` |
| Invalid schema | `model_schema_invalid` |
| Provider unavailable or 5xx | `model_unavailable` |
| Unknown exception | `unknown_error` |

These mappings produce recommended actions for evaluation reports. They do not execute production retries or production routing.

## 8. Cost and Usage Boundary

Usage fields are optional because not every provider response returns token counts. Estimated cost is not real billing and must not be reconciled as an invoice. If pricing is unknown, cost should remain unavailable or explicitly estimated.

## 9. Provider Verification Lifecycle

- `not_configured`: Provider is known but missing required local config.
- `configured`: Required local config is present, but no smoke result exists.
- `smoke_test_skipped`: Smoke test was skipped due to dry-run or missing API key.
- `smoke_test_failed`: Smoke test ran and failed.
- `smoke_test_passed`: Smoke test completed successfully in a controlled run.
- `evaluation_ready`: Provider has enough verified smoke behavior to enter evaluation runs.
- `deprecated`: Provider should no longer be used for new evaluation runs.

`not_verified` does not mean unavailable; it means the repository has not verified the provider. Smoke test passed does not mean production available. Estimated cost does not equal real billing. Provider fallback simulation does not equal production routing.
