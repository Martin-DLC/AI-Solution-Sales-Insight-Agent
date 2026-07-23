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

## 8. Relationship to Existing LLM Evaluation

This abstraction does not modify existing LLM evaluation artifacts or provider comparison reports. Existing eval assets remain source-of-truth for current evaluation history.

## 9. What Is Not Implemented Yet

- Real DeepSeek API calls.
- Production-verified MaaS provider integrations.
- Production model routing.
- Real billing reconciliation.
- Real provider performance claims.

## 10. Known Limitations

Current model fallback is preset and mock-only. It is suitable for local tests and governance design, not production deployment claims.
