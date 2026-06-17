# Baseline B v2 Failure Analysis

## Run Summary

- Run ID: `B-DEV-01-20260617T173349Z-debe0ce7`
- Prompt version: `baseline_b_v2`
- JSON parsing: succeeded
- Schema validation: failed
- Pydantic error count: 5

## Error Field Paths

- `information_gaps.7.recommended_owner`
- `risks_and_objections.0.impact`
- `risks_and_objections.3.impact`
- `risks_and_objections.5.impact`
- `next_best_actions.3.expected_output`

## Error Categories

- Owner enum mismatch: `InformationGap.recommended_owner` used a value outside its allowed enum.
- Risk impact specificity: multiple `risks_and_objections[*].impact` values were shorter than the Schema minimum.
- Next action output specificity: one `next_best_actions[*].expected_output` value was shorter than the Schema minimum.

## v1 To v2 Improvement

Baseline B v1 failed with 12 Schema errors. Baseline B v2 reduced the failure count to 5. The removed error categories were the Claim Type mistakes and Deal Score fixed-weight mistakes targeted by the v2 Prompt contract.

This suggests Prompt contract strengthening was effective for the targeted generic rules.

## Why Not Manually Fix The Model Output

The raw model response is the experiment artifact. Manually editing it would make the result unreproducible and would hide whether success came from the model, the Prompt, or a human correction.

## v3 Scope

v3 is limited to general Schema contract clarity:

- field-specific owner enum rules;
- minimum length and specificity for risk impact text;
- minimum length and specificity for next action text.

v3 must not add DEV-01-specific answers, hidden reference content, scoring notes, runtime repair, or any Schema change.

## Stop Condition

After v3, Prompt iteration should stop for DEV-01. Further improvement should move to broader test cases and evaluation design rather than repeatedly tuning against one visible development case.
