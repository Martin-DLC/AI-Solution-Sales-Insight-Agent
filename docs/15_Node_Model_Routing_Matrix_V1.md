# Node Model Routing Matrix V1

## Scope

This document summarizes the formal Node Model Pilot using exactly four audited 12-call runs:

- `fact_extraction`: `MB-20260626T174835Z-25d3d6a0`
- `underlying_pain`: `MB-20260626T172704Z-70afe0ec`
- `information_gap`: `MB-20260626T175832Z-371b721f`
- `solution_recommendation`: `MB-20260626T173701Z-d68a9f15`

Smoke runs and interrupted runs are intentionally excluded from all totals and routing decisions.

## Formal Pilot Totals

- Planned runs: `48`
- Completed runs: `48`
- Passed runs: `43`
- Failed runs: `5`
- Request errors: `0`
- Unknown-cost runs: `0`
- Estimated total cost (CNY): `0.893536`

## Failure Taxonomy

- Total failed runs: `5`
- Failed nodes:
  - `fact_extraction`: `2`
  - `solution_recommendation`: `3`
- Failed model configs:
  - `ds-v4-pro-non-thinking`: `5`
- Error types:
  - `LLMJSONDecodeError`: `1`
  - `schema_validation_error`: `1`
  - `business_rule_error`: `3`
- Failed assertion types:
  - `schema_validation_success`: `2`
  - `evidence_reference_valid`: `1`
  - `candidate_boundary_valid`: `1`
- Blocking assertion failures: `4`
- Non-blocking assertion failures: `0`

## Model-Level Summary

- `ds-v4-flash-non-thinking`
  - Total cases: `16`
  - Passed: `16`
  - Failed: `0`
  - Total tokens: `62738`
  - Total cost (CNY): `0.090388`
  - Average latency (ms): `16718.938`
- `ds-v4-pro-non-thinking`
  - Total cases: `16`
  - Passed: `11`
  - Failed: `5`
  - Total tokens: `82524`
  - Total cost (CNY): `0.389880`
  - Average latency (ms): `32366.312`
- `ds-v4-pro-thinking-high`
  - Total cases: `16`
  - Passed: `16`
  - Failed: `0`
  - Total tokens: `86422`
  - Total cost (CNY): `0.413268`
  - Average latency (ms): `33604.625`

## Routing Matrix

- `fact_extraction`
  - Primary: `ds-v4-flash-non-thinking`
  - Fallback: `ds-v4-pro-thinking-high`
  - Disqualified:
    - `ds-v4-pro-non-thinking` due to `schema_validation_failure`, `blocking_assertion_failure`, `evidence_reference_failure`
- `underlying_pain`
  - Primary: `ds-v4-flash-non-thinking`
  - Fallback: `ds-v4-pro-non-thinking`
  - All three model configs remain eligible
- `information_gap`
  - Primary: `ds-v4-flash-non-thinking`
  - Fallback: `ds-v4-pro-non-thinking`
  - All three model configs remain eligible
- `solution_recommendation`
  - Primary: `ds-v4-flash-non-thinking`
  - Fallback: `ds-v4-pro-thinking-high`
  - Disqualified:
    - `ds-v4-pro-non-thinking` due to `blocking_assertion_failure`, `candidate_boundary_failure`

## Interpretation

- The current routing gate already rejects weak configurations without introducing any new benchmark-specific relaxation.
- `ds-v4-flash-non-thinking` is the default primary for all four nodes because it clears the existing gate while also winning on cost and latency.
- `ds-v4-pro-thinking-high` stays viable as a fallback for higher-risk nodes where the non-thinking Pro variant failed benchmark gates.
- `ds-v4-pro-non-thinking` should not be routed into `fact_extraction` or `solution_recommendation` until its blocking failures are resolved.

## Reproducible Artifacts

- Formal run mapping: [formal_pilot_runs.v1.json](/Users/baba/AI-Projects/AI-Solution-Sales-Insight-Agent/data/evaluation/model_benchmark/formal_pilot_runs.v1.json)
- Formal pilot summary: [formal_pilot_summary.v1.json](/Users/baba/AI-Projects/AI-Solution-Sales-Insight-Agent/data/evaluation/model_benchmark/formal_pilot_summary.v1.json)
- Routing matrix: [node_model_routing_matrix.v1.json](/Users/baba/AI-Projects/AI-Solution-Sales-Insight-Agent/data/evaluation/model_benchmark/node_model_routing_matrix.v1.json)
