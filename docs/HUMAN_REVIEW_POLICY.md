# Human Review Policy

## Why Human Review Exists

Human review exists to prevent the agent from treating uncertain, high-risk, or weakly grounded outputs as automatically accepted business decisions. It is a governance control, not a quality decoration.

In this project, human review is local-first and policy-oriented. It documents when a reviewer should be involved and how pending review state should be represented.

## Trigger Rules

Human review can be triggered by:

- Fallback or human confirmation required by the service.
- Permission denial or high-risk operation requiring approval.
- Trajectory evaluation gate decision of `human_review`.
- Missing fallback explanation for a risky path.
- High-risk event without a matching review signal.
- Evidence grounding weakness that makes automated acceptance unsafe.

## Review Status Model

The review queue status model supports:

- `not_required`
- `pending`
- `in_review`
- `approved`
- `approved_with_changes`
- `rejected`
- `expired`

`pending` means review is required but has not been completed. It must not be reported as a completed review.

## Review Queue Item

A review queue item should capture:

- Review item ID.
- Run ID and trace ID.
- Trigger source.
- Trigger reason.
- Risk level.
- Current status.
- Created timestamp.
- Optional reviewer notes.
- Optional decision timestamp.

The current implementation is in-memory and local. It is not a production workflow queue.

## Human Evaluation Layer vs Human Review Queue

The Human Evaluation Layer prepares offline evaluation packets and annotation templates. It can remain `not_started` until real annotations are provided.

The Human Review Queue represents runtime review triggers. A pending queue item does not mean that an evaluator has scored the output.

These are related governance concepts, but they are not interchangeable.

## No Fake Human Scores Policy

The project must not fabricate human scores, reviewer identities, approval outcomes, or business validation results.

Specifically:

- Human Eval summary can remain `not_started`.
- Pending review is not completed review.
- Evaluation gate decision is not a human score.
- Simulated review is not real review.
- A generated review packet is not reviewer approval.

## Reviewer Roles Preset

For future pilots, reviewer roles may include:

- Sales solution owner: checks business relevance and actionability.
- Domain expert: checks industry assumptions and evidence fit.
- Risk reviewer: checks permission, privacy, and high-risk action boundaries.
- Delivery lead: checks implementation feasibility and handoff readiness.

These are presets only. The project does not implement real user accounts or reviewer assignment.

## Review Decision Lifecycle

The intended lifecycle is:

1. Runtime governance creates or marks a review trigger.
2. A review queue item enters `pending`.
3. A reviewer moves it to `in_review`.
4. The reviewer chooses `approved`, `approved_with_changes`, `rejected`, or `expired`.
5. The result is written back to a durable workflow system in a future implementation.

Current Batch 6 documentation does not add a real workflow system.

## Result Writeback Preset

Future result writeback should include:

- Decision status.
- Reviewer role or identity.
- Decision notes.
- Changed fields, if approved with changes.
- Evidence or policy reason for rejection.
- Timestamp.
- Idempotency key for any downstream write.

The current project does not perform real writeback.

## Known Limitations

- No real reviewer identity.
- No completed human score by default.
- No SLA, escalation, or assignment logic.
- No persistent queue.
- No enterprise workflow inbox.
- No real approval service.
- No production audit evidence.
