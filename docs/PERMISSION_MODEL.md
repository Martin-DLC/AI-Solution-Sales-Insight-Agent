# Permission Model

## 1. Why Tool Permissions Matter

Runtime governance needs to know which tools an agent is allowed to use, which operations are read-only, which operations are risky, and which actions require human approval. Batch 2 adds the local-first foundation for those controls.

This is not production RBAC. It is a reference implementation layer for permission metadata, default-deny decisions, risk levels, approval request state, and trajectory events.

## 2. Tool Permission Metadata

Tool policies are defined in `config/tool_permissions.yaml`.

Each tool policy includes:

- `tool_name`
- `allowed_actions`
- `permission_scope`
- `risk_level`
- `requires_confirmation`
- `requires_human_review`
- `idempotent`
- `reversible`
- `description`

Configured tools:

- `knowledge_search`
- `crm_read`
- `crm_write`
- `ticket_read`
- `ticket_update`
- `bi_read`
- `email_draft`
- `email_send`
- `delete_record`

## 3. Risk Levels

Supported risk levels:

- `low`
- `medium`
- `high`
- `unknown`

Read-only operations are normally low or medium risk. Write operations are at least medium risk. Delete, send, and external write operations are high risk by default.

## 4. Default Deny Policy

`PermissionChecker` denies by default when:

- The tool is unknown.
- The action is not listed in `allowed_actions`.
- The requested scope exceeds the configured permission scope.

Unknown tools are treated as high risk and denied.

## 5. High-risk Operations

High-risk tools in the current local config:

- `crm_write`
- `ticket_update`
- `email_send`
- `delete_record`

High-risk operations require human review. They are not executed by the normal `SolutionInsightService` flow.

## 6. Approval Request Lifecycle

`ApprovalRequest` supports these statuses:

- `not_required`
- `pending`
- `approved`
- `rejected`
- `expired`

`ApprovalManager` is an in-memory manager with:

- `create_request(...)`
- `approve(...)`
- `reject(...)`
- `expire(...)`
- `get_request(...)`
- `list_requests(...)`
- `can_continue(...)`

Pending, rejected, and expired approvals cannot continue. Approved approvals can continue. Terminal approvals cannot be approved or rejected again.

## 7. Simulated Approval / Rejection

Batch 2 only supports local simulated approval and rejection. There is no real user login, IAM identity, workflow inbox, or enterprise approval service.

## 8. Relationship to Trajectory Events

Permission and approval operations can write trajectory events:

- `permission_checked`
- `permission_denied`
- `approval_requested`
- `approval_approved`
- `approval_rejected`
- `approval_expired`

Events record tool name, permission scope, risk level, status, and whether human review is required. They do not record API keys, tracebacks, full prompts, or benchmark gold.

## 9. What Is Not Implemented Yet

Not implemented in Batch 2:

- Production RBAC.
- Real IAM.
- Real approval system.
- Real CRM write.
- Real email send.
- Immutable audit logs.
- Central policy administration.
- Distributed approval queues.

## 10. Known Limitations

This is a local-first permission and approval foundation. It demonstrates policy shape, risk classification, default-deny behavior, approval state transitions, and event recording. It does not claim production deployment readiness, and high-risk operations cannot be automatically executed.
