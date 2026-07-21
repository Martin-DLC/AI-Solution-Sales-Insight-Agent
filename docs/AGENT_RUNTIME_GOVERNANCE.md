# Agent Runtime Governance

## 1. Why Runtime Governance

Runtime governance gives the local agent a minimal, inspectable record of what happened during a run. The v0.3 MVP already had skills, retrieval, fallback, observability, and human review surfaces. Runtime Governance v0.1 adds the first shared layer for run identity, trajectory events, status, limits, and trace summaries.

This is local-first governance. It is designed for reference implementation, testing, demo review, and future enterprise hardening. It is not a production tracing platform.

## 2. Trajectory Event Schema

`TrajectoryEvent` is defined in `agent/governance/models.py`.

The event schema includes:

- `event_id`
- `run_id`
- `trace_id`
- `task_id`
- `node_name`
- `agent_name`
- `step_index`
- `event_type`
- `input_summary`
- `output_summary`
- `tool_name`
- `permission_scope`
- `risk_level`
- `status`
- `error_type`
- `fallback_triggered`
- `human_review_required`
- `stop_reason`
- `created_at`

Input and output fields are summaries only. The recorder does not store full prompts, full customer input, tracebacks, API keys, benchmark gold, or hidden reference pack content.

## 3. Runtime Status Machine

`RuntimeStatus` currently supports:

- `created`
- `running`
- `completed`
- `failed`
- `stopped_by_policy`
- `waiting_for_human`
- `paused`
- `resumed`
- `cancelled`

Batch 1 only uses the basic lifecycle. Pause, resume, cancel, and distributed recovery are reserved states, not fully implemented behavior.

## 4. Runtime Limits

Runtime limits are configured in `config/runtime_limits.yaml`.

Current fields:

- `max_execution_steps: 50`
- `max_consecutive_failures: 3`
- `max_tool_failures: 3`
- `max_task_duration_seconds: 120`

Batch 1 implements minimal checks for:

- `step_limit_exceeded`
- `consecutive_failure_limit_exceeded`

Normal `SolutionInsightService` calls should not hit these limits.

## 5. How Events Are Recorded

`TrajectoryRecorder` is an in-memory recorder. It supports:

- `start_run()`
- `record_event(...)`
- `record_skill_event(...)`
- `record_fallback_event(...)`
- `record_human_review_event(...)`
- `stop_by_policy(...)`
- `complete_run()`
- `fail_run()`
- `export_events()`
- `summary()`

`SolutionInsightService.generate_insight()` starts a recorder for each request, passes it through `SkillInput.context`, records skill events through `SkillRegistry`, then adds domain events for provider context, formal retrieval, shadow retrieval, fallback assessment, human review, generation, and run completion.

## 6. What Is Not Implemented Yet

Runtime Governance v0.1 does not include:

- Production permission system.
- Production approval workflow.
- Production RBAC.
- Immutable audit log.
- External tracing backend.
- Real MCP integration.
- Real CRM writes.
- Real pause/resume recovery.
- Distributed task recovery.
- Production deployment claims.

## 7. Relationship to Observability

Observability now reads the governance summary from the response when present. The snapshot includes run ID, trace ID, event count, final runtime status, stop reason, human review flag, and fallback flag.

The observability report remains local and descriptive. It is not an audit-compliant log.

## 8. Relationship to Human Review

Fallback-driven human confirmation is recorded in the governance summary. If `human_confirmation_required=true`, the recorder emits a `human_review_required` event.

This is separate from Human Evaluation. The project still does not fake human scores. Human evaluation remains incomplete until an actual reviewer supplies annotations.

## 9. Known Limitations

- The recorder is in-memory and per-request.
- Events are not immutable.
- There is no database or external tracing platform.
- Redaction is conservative but not a full enterprise DLP system.
- Runtime limits only cover event count and consecutive failed events in Batch 1.
- The governance layer is intentionally local-first and does not claim production deployment readiness.

## 10. Batch 2 Permission and Approval Foundation

Batch 2 adds a local-first tool permission and approval foundation:

- Tool policies live in `config/tool_permissions.yaml`.
- `PermissionChecker` returns structured allow/deny decisions.
- Unknown tools, unknown actions, and scope-exceeding requests are denied by default.
- High-risk actions such as CRM writes, email sends, ticket updates, and deletes require human review.
- `ApprovalManager` supports local simulated approval requests, approvals, rejections, and expirations.
- Permission and approval actions can emit trajectory events such as `permission_checked`, `permission_denied`, `approval_requested`, `approval_approved`, `approval_rejected`, and `approval_expired`.

This is still not production RBAC, real IAM, or a real approval service. The normal `SolutionInsightService` path only records read-only permission checks for mock tools and does not execute high-risk operations.
