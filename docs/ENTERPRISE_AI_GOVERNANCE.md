# Enterprise AI Governance

## Governance Goal

Runtime Governance v0.1 describes how this local Solution Insight Agent records, limits, evaluates, reviews, and reports a run. The goal is to make an AI sales insight workflow easier to inspect before it is considered for an enterprise pilot.

This is a local-first reference implementation. It is not a production SaaS platform, not a regulated audit system, and not a claim of production deployment readiness.

## Current Project Boundary

The project supports a deterministic local demo, formal retrieval evidence, shadow retrieval diagnostics, runtime trajectory events, permission metadata, estimated cost summaries, trajectory evaluation, review queue triggers, fallback classification, and mock model provider fallback.

The project does not include real IAM, real enterprise writes, real CRM mutation, real ticket updates, real email sends, immutable audit logs, real human scores, real customer data, or real business ROI.

## Runtime Trace and Auditability

Each governed run can carry a `run_id`, `trace_id`, runtime status, and trajectory events. Events summarize node execution, permission checks, fallback, human review triggers, provider context, and run completion.

Trace content is intentionally summarized. The recorder avoids storing full prompts, full customer input, API keys, traceback dumps, benchmark gold data, or hidden reference pack content.

Current auditability is suitable for local inspection and CI checks. It is not an immutable audit log and does not provide tamper-proof retention.

## Permission and Approval

Tool permission metadata is defined in `config/tool_permissions.yaml`. The permission layer supports allow/deny decisions, default deny behavior, risk levels, and approval request states.

High-risk presets include write, send, update, and delete style operations. The normal Solution Insight path remains read-only and does not perform real enterprise writes.

Approval is simulated in memory. There is no real enterprise approval workflow, IAM identity, SSO, RBAC, or workflow inbox.

## Trajectory Evaluation

Trajectory evaluation checks whether the runtime path respected governance rules. It can flag policy stops, permission denials, high-risk review gaps, fallback explanation gaps, missing core nodes, and shadow retrieval boundary violations.

This is rule-based and local-first. It does not use an LLM judge and does not replace business acceptance testing.

## Human Review

Human review is triggered when fallback, permission, or trajectory evaluation indicates that a result should not be treated as automatically accepted.

The review queue is in-memory and can represent pending review states. Pending review is not a completed review. The existing Human Evaluation summary may remain `not_started` until a real reviewer provides annotations.

The project has a no fake human scores policy. Simulated review state is not real human validation.

## Fallback and Recovery

The recovery layer defines an error taxonomy, retry/fallback/stop/human-review decisions, fallback types, idempotency keys, and compensation plan schemas.

Current recovery is design-first. It does not execute real retries against live services, real rollback, real compensation, or real external side effects.

## Observability and Estimated Cost

Observability summarizes run status, model calls, tool calls, permission checks, fallback, human review flags, latency, token estimates, and estimated cost.

Cost values are estimated. Deterministic mode does not represent real model billing, and generated reports are not production monitoring or billing reports.

## Model Provider Strategy

The model provider abstraction documents capabilities such as structured output, tool calling, context length, streaming, cost profile, latency profile, data policy, health checks, and fallback provider selection.

Current provider fallback is preset and mock-only. It does not claim real provider routing, real latency benchmarks, or real billing reconciliation.

## Data and Privacy Presets

The project uses synthetic demo inputs, local fixtures, frozen retrieval artifacts, and local reports. Privacy-oriented presets include summarized trajectory fields, no real API keys in source, no real customer data requirement, and local deterministic operation.

These presets are not a full enterprise privacy program. There is no DLP engine, no retention policy enforcement, no customer-specific legal review, and no enterprise data residency guarantee.

## What Is Implemented

- Local `run_id` and `trace_id` propagation.
- Runtime trajectory event model and in-memory recorder.
- Runtime status and basic execution limits.
- Tool permission metadata and default-deny checks.
- Simulated approval request lifecycle.
- Run metrics and estimated cost summaries.
- Trajectory evaluation rules and gate decisions.
- Review queue item schema and pending status.
- Fallback taxonomy and recovery decision objects.
- Local idempotency key generation.
- Mock model provider abstraction and fallback selection.
- Enterprise governance, delivery blueprint, and ROI metric framework documentation.

## What Is Mocked or Preset

- Approval decisions are simulated.
- Human review queue state is local and in-memory.
- Model provider fallback uses mock/preset providers.
- Cost and token usage are estimated unless future integrations provide real usage.
- Enterprise context is fixture-based.
- Compensation plans are schemas, not executed operational rollback.

## What Is Not Implemented Yet

- Production SaaS deployment.
- Real IAM, SSO, RBAC, or enterprise approval workflow.
- Immutable audit logs or audit-compliant retention.
- Real CRM, ticket, email, or BI writes.
- Real human scoring or completed human evaluation.
- Real customer data processing.
- Real enterprise ROI measurement.
- Production monitoring, alerting, tracing backend, or billing reconciliation.
- Production data privacy, DLP, and residency enforcement.

## Known Limitations

Runtime Governance v0.1 is intended to make the local prototype easier to inspect, discuss, and pilot. It is not sufficient by itself for regulated production operation. Any enterprise rollout would need security review, privacy review, legal review, integration testing, human workflow design, monitoring, incident response, and measured pilot outcomes.
