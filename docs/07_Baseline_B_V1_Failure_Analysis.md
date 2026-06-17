# Baseline B v1 Failure Analysis

## Run Summary

- Run ID: `B-DEV-01-20260617T171842Z-af0704ab`
- Prompt version: `baseline_b_v1`
- JSON parsing: succeeded
- Schema validation: failed
- Pydantic error count: 12

## Error Field Paths

- `explicit_needs.5`
- `underlying_pains.0`
- `underlying_pains.1`
- `underlying_pains.2`
- `deal_score.dimensions.0`
- `deal_score.dimensions.1`
- `deal_score.dimensions.2`
- `deal_score.dimensions.3`
- `deal_score.dimensions.4`
- `deal_score.dimensions.5`
- `deal_score.dimensions.6`
- `next_best_actions.4.objective`

## Error Categories

- Claim type contract violation: one explicit need was not marked as `fact`.
- Claim type contract violation: three underlying pains were not marked as `inference` or `assumption`.
- Deal Score fixed weight violation: all seven `max_score` values failed to match the required dimension weights.
- Next Best Action specificity violation: one action objective was shorter than the required minimum length.

## Prompt Contract Or Schema Issue

The failures are best classified as Prompt contract gaps rather than Schema defects. The Schema correctly rejected outputs that violated the existing business rules. Baseline B v1 did ask for a valid `SalesInsightReport`, but it did not make several high-risk field contracts explicit enough for a live model response:

- exact claim type constraints by section;
- fixed Deal Score dimension weights;
- minimum specificity for `NextBestAction.objective`.

## Why Not Manually Fix The Raw Model Result

The raw model response is part of the experiment record. Manually editing it would break reproducibility and make it unclear whether a later result came from the model, the Prompt, or a human correction. Baseline outputs must remain immutable evidence of what a specific Prompt and model returned at a specific time.

## Why Add v2 Instead Of Overwriting v1

`baseline_b_v1` must remain available for comparison with future runs. Overwriting it would silently change historical experiment meaning and make v1 failure analysis impossible to reproduce. `baseline_b_v2` is therefore introduced as a new Prompt contract version.

## v2 Change Boundary

The only intended variable in v2 is Prompt contract clarity. v2 does not change:

- runtime repair behavior;
- output Schema;
- seed cases;
- reference data;
- model configuration;
- model adapter behavior;
- single-call Baseline B execution.
