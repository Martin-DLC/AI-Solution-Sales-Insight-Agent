# Trajectory Evaluation and Human Review

## 1. Why Trajectory-level Evaluation

Output-level evaluation checks whether a final response looks valid. Trajectory-level evaluation checks whether the agent reached that response through an acceptable runtime path: permissions were respected, high-risk events were reviewed, fallback was explained, and core runtime events were present.

Batch 4 adds a local-first, rule-based evaluation gate over trajectory events.

## 2. Difference from Output-level Evaluation

Output-level evaluation scores response content, schema validity, grounding, fallback alignment, and hallucination risk. Trajectory-level evaluation looks at event history and governance signals. It does not judge writing quality or business usefulness.

## 3. Rule-based Evaluation

Rules are configured in `config/trajectory_evaluation_rules.yaml` and implemented in `evaluation/trajectory/rules.py`.

Current rules:

- `no_policy_stop`
- `no_permission_denied`
- `high_risk_requires_review`
- `fallback_requires_explanation`
- `human_review_event_consistency`
- `no_excessive_failures`
- `required_core_nodes_present`
- `shadow_does_not_override_formal`

This implementation does not use an LLM judge.

## 4. Evaluation Gate Decisions

`EvaluationGate` supports:

- `pass`
- `retry`
- `human_review`
- `stop`

Critical failures stop. Excessive failures can recommend retry. Permission denial or high-risk review gaps trigger human review. Passing rules produce `pass`, unless the runtime trace already indicates human review is required.

## 5. Human Review Trigger

When the gate requires human review, the service can create a local `ReviewQueueItem` with `pending` status. This is a trigger, not a completed human review.

## 6. Review Queue Status

`ReviewQueueManager` is in-memory and supports:

- `not_required`
- `pending`
- `in_review`
- `approved`
- `approved_with_changes`
- `rejected`
- `expired`

Pending review is not treated as completed.

## 7. Relationship to Human Evaluation Layer

The existing Human Evaluation Layer remains separate. Batch 4 does not fill annotation scores, does not mark human evaluation completed, and does not modify human eval summary artifacts.

Human evaluation status may still be `not_started` until a real reviewer provides annotations.

## 8. What Is Not Implemented Yet

Not implemented in Batch 4:

- Production review workflow.
- Real reviewer identity.
- SLA or escalation.
- LLM judge.
- Automatic retry.
- Automatic stop of the current demo response.
- Completed human scoring.
- Production audit compliance.

## 9. Known Limitations

This is local-first trajectory evaluation. It is a reference implementation for explaining runtime quality gates and review triggers. It is not a production-grade review system and does not claim real human validation is complete.
