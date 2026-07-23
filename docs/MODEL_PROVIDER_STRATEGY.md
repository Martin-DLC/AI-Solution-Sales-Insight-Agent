# Model Provider Strategy

## 1. Why Model Provider Abstraction

An enterprise agent should describe model capabilities and fallback options without hard-coding all logic into the service. Batch 5 adds a minimal provider interface and mock provider registry.

## 2. Provider Interface

`BaseModelProvider` exposes:

- `provider_name`
- `model_name`
- `supports_tool_calling`
- `supports_structured_output`
- `supports_long_context`
- `supports_streaming`
- `cost_profile`
- `latency_profile`
- `data_policy`
- `health_check()`
- `generate(prompt, **kwargs)`
- `estimate_cost(input_text, output_text)`

## 3. Capability Metadata

Provider metadata explains structured output, tool calling, context, streaming, cost profile, latency profile, and data policy. This supports provider selection without calling external services.

## 4. Cost and Latency Profiles

Batch 5 uses descriptive local metadata only. It does not provide real billing data or real latency benchmarks.

## 5. Mock Provider

`MockModelProvider` is deterministic and does not access the network. It can simulate:

- `model_timeout`
- `model_schema_invalid`
- `model_unavailable`

## 6. Fallback Provider Strategy

`ModelProviderRegistry` can register providers, select a healthy primary provider, select a fallback provider, and run health checks.

## 7. OpenAI-compatible MaaS Adapter

v0.5A adds `OpenAICompatibleModelProvider` as an offline-safe adapter foundation under the existing `BaseModelProvider` protocol. It supports MaaS provider metadata, dry-run smoke tests, skipped-missing-key results, and error mapping into the existing recovery taxonomy.

Candidate MaaS providers live in `config/maas_providers.yaml` with `verification_status: not_verified`. These entries are evaluation candidates only. Dry-run or skipped smoke results are not model quality results, estimated cost is not real billing, and provider fallback simulation is not production routing.

## 8. Multi-MaaS Evaluation Runner

v0.5B adds an offline-safe Multi-MaaS evaluation runner under `evaluation/multi_maas/`. It reads seed evaluation cases and MaaS provider config, defaults to dry-run, separates skipped/dry-run/failed/success statuses, and writes optional reports under `reports/multi_maas_model_eval.latest.*`.

The runner does not modify the agent's main flow, does not call real APIs by default, and does not treat dry-run or missing-key results as model quality outcomes.

## 9. Provider Selection and Recovery Governance

v0.5C adds evaluation-only provider selection policies and recovery summaries. The selection module can rank provider/model candidates when successful evaluation data exists, but returns `skipped_all_targets` or `insufficient_data` when only skipped/dry-run data is available.

Fallback provider recommendations are report guidance only. They do not execute live fallback and do not create production routing.

## 10. Relationship to Existing LLM Evaluation

This abstraction does not modify existing LLM evaluation artifacts or provider comparison reports. Existing eval assets remain source-of-truth for current evaluation history.

## 11. What Is Not Implemented Yet

- Real DeepSeek API calls.
- Production-verified MaaS provider integrations.
- Production model routing.
- Real billing reconciliation.
- Real provider performance claims.

## 12. Known Limitations

Current model fallback is preset and mock-only. It is suitable for local tests and governance design, not production deployment claims.
