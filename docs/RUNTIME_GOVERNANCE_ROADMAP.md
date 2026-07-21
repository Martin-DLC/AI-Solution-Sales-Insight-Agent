# Runtime Governance Roadmap

## Current Milestone: Runtime Governance v0.1

Runtime Governance v0.1 closes the local-first governance foundation for the Solution Insight Agent. It is intended for repository inspection, deterministic demo, CI validation, and enterprise pilot planning.

## Completed Batches

| Batch | Theme | Status | Notes |
| --- | --- | --- | --- |
| Batch 1 | Runtime governance foundation | `completed` | Run IDs, trace IDs, trajectory events, runtime status, and limits. |
| Batch 2 | Permission and approval foundation | `completed` | Tool policies, default deny, high-risk presets, simulated approval states. |
| Batch 3 | Observability and estimated cost | `completed` | Run metrics, estimated token/cost tracking, local summary reports. |
| Batch 4 | Trajectory evaluation and human review trigger | `completed` | Rule-based gate, review queue item, no fake human score boundary. |
| Batch 5 | Fallback, recovery, and model provider strategy | `completed` | Error taxonomy, fallback decisions, idempotency, compensation schema, mock provider fallback. |
| Batch 6 | Enterprise delivery governance | `completed` | Enterprise governance docs, human review policy, delivery blueprint, ROI metric framework, release checklist. |

## v0.1 Trust Boundary

Runtime Governance v0.1 is not a production SaaS release. It does not include real IAM, immutable audit logs, real enterprise writes, completed human scoring, real customer data, or real ROI measurement.

## Recommended Next Milestone

The next milestone should be a controlled pilot readiness phase:

1. Select one read-only enterprise workflow.
2. Define customer-approved data and privacy handling rules.
3. Connect read-only context sources behind explicit permissions.
4. Add durable storage for traces, reviews, and run metrics.
5. Replace simulated approvals with real reviewer identity and workflow state.
6. Collect real reviewer annotations and measured baseline effort.
7. Recalculate ROI metrics only from pilot data.

## Deferred Production Capabilities

- Enterprise IAM, SSO, and RBAC.
- Central policy administration.
- Immutable audit log and retention policy.
- Production tracing and monitoring.
- Billing reconciliation from provider usage exports.
- Real connector writes with approval, idempotency, and compensation.
- Human review SLA, assignment, escalation, and durable writeback.
- Customer-specific privacy, security, legal, and deployment review.
