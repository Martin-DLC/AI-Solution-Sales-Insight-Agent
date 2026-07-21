# Governance Gap Matrix

## Scope

This matrix tracks the 41 Runtime Governance capabilities used to close Runtime Governance v0.1. Status values are limited to:

- `implemented`
- `partially_implemented`
- `documented_only`
- `missing`
- `not_applicable`

The matrix describes current repository state after Batches 1-6. It does not claim production readiness.

## Capability Matrix

| # | Capability | Current Status | Current Evidence | Remaining Gap |
| --- | --- | --- | --- | --- |
| 1 | `run_id` / `trace_id` | `implemented` | Runtime governance models and service response summaries. | Persistent trace store is not implemented. |
| 2 | `trajectory_events` schema | `implemented` | `TrajectoryEvent` schema documents run, node, tool, permission, fallback, and review fields. | Schema is local-first and not standardized for external tracing. |
| 3 | Trajectory event recorder | `implemented` | In-memory `TrajectoryRecorder`. | No durable event backend. |
| 4 | Workflow node event logging | `implemented` | Skill and service events record requirement, retrieval, fallback, generation, and completion. | Coverage is scoped to the current local service. |
| 5 | Tool call event logging | `partially_implemented` | Permission/tool-like events can be represented in trajectory events. | No real external tool execution log. |
| 6 | Skill trace integration | `implemented` | Skills registry emits skill trace and governance events. | No third-party agent framework trace integration. |
| 7 | Provider trace integration | `partially_implemented` | Mock enterprise context and model provider metadata can be surfaced. | No real provider telemetry integration. |
| 8 | Fallback event logging | `implemented` | Fallback events and flags are included in governance summaries. | No persistent incident workflow. |
| 9 | Human review required event | `implemented` | Human review required events can be emitted from fallback and gate decisions. | No real reviewer action. |
| 10 | Runtime status machine | `implemented` | Created, running, completed, failed, stopped, waiting, paused, resumed, cancelled states documented. | Pause/resume/cancel are reserved states, not full distributed behavior. |
| 11 | Max execution step limit | `implemented` | Runtime limits config and policy stop support. | Local checks only. |
| 12 | Consecutive failure stop | `implemented` | Runtime limits include consecutive failure threshold. | No production incident workflow. |
| 13 | Tool permission metadata | `implemented` | `config/tool_permissions.yaml`. | No central policy administration. |
| 14 | Permission check interface | `implemented` | Permission checker returns structured decisions. | No enterprise policy engine. |
| 15 | Default deny policy | `implemented` | Unknown tools/actions/scopes are denied. | No external policy sync. |
| 16 | High-risk operation definition | `implemented` | Write, send, update, and delete presets require human review. | No customer-specific risk taxonomy. |
| 17 | Approval request schema | `implemented` | Local approval request model. | No durable approval record. |
| 18 | Approval state machine | `implemented` | Pending, approved, rejected, expired states. | No workflow inbox or IAM identity. |
| 19 | Simulated approval / rejection | `implemented` | In-memory approval manager. | Simulation only; not real approval. |
| 20 | Audit log schema | `partially_implemented` | Trajectory events provide audit-style summaries. | No immutable audit log or retention policy. |
| 21 | Audit log redaction | `partially_implemented` | Event summaries avoid full prompts, keys, hidden gold, and tracebacks. | No enterprise DLP or formal redaction certification. |
| 22 | Output-level evaluation | `implemented` | Existing deterministic baseline and LLM evaluation checks. | Not a human business-quality score. |
| 23 | Node-level evaluation | `partially_implemented` | Required core node presence and skill events are checked. | No rich per-node quality scoring. |
| 24 | Trajectory-level evaluation | `implemented` | Rule-based trajectory evaluator and gate. | No LLM judge or production policy engine. |
| 25 | Evaluation gate | `implemented` | Gate can return pass, retry, human review, or stop. | Does not execute production workflow decisions. |
| 26 | Model call metrics | `implemented` | Run metrics summarize model call count. | Deterministic mode does not represent real calls. |
| 27 | Token usage metrics | `partially_implemented` | Cost tracker uses stable token estimates. | No real provider usage export. |
| 28 | Estimated cost tracking | `partially_implemented` | Model cost config and estimated cost reports. | No billing reconciliation. |
| 29 | Tool success / failure metrics | `implemented` | Run metrics derive tool-like success/failure counts from events. | No real connector execution metrics. |
| 30 | Run summary report | `implemented` | `generate_run_summary_report.py` and report artifacts. | Local report only. |
| 31 | Retry policy | `partially_implemented` | Recovery policy and decision objects. | No real retry executor or backoff runtime. |
| 32 | Fallback taxonomy | `implemented` | Recovery docs and fallback type schema. | No production incident taxonomy mapping. |
| 33 | Rollback / compensation design | `partially_implemented` | Compensation plan schema exists. | No real rollback or compensation execution. |
| 34 | Idempotency key support | `implemented` | Local idempotency key generator. | No persistent deduplication store. |
| 35 | Model provider abstraction | `implemented` | Base provider interface and registry. | No new real provider integration in this batch. |
| 36 | Model fallback | `partially_implemented` | Mock provider fallback strategy. | Preset/mock only; no live routing. |
| 37 | Human review policy | `implemented` | `docs/HUMAN_REVIEW_POLICY.md`. | No production reviewer workflow. |
| 38 | Review queue schema | `implemented` | In-memory review queue item and statuses. | No persistent queue or assignment. |
| 39 | Enterprise governance document | `implemented` | `docs/ENTERPRISE_AI_GOVERNANCE.md`. | Document only; not a compliance certification. |
| 40 | Enterprise delivery blueprint | `implemented` | `docs/ENTERPRISE_DELIVERY_BLUEPRINT.md`. | Needs future customer-specific pilot design. |
| 41 | ROI metric framework | `implemented` | `docs/ROI_METRIC_FRAMEWORK.md`. | No real enterprise ROI data. |

## Summary

Runtime Governance v0.1 has enough local foundations to explain traceability, permission boundaries, review triggers, fallback, estimated cost, and enterprise delivery planning. The largest remaining gaps are production identity, durable audit, real connector writes, real human review completion, live provider billing, and measured enterprise ROI.
