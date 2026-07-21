# Observability and Cost

## 1. Why Observability and Cost Matter

Runtime governance needs more than event history. Operators also need a compact summary of how many steps ran, which tool and permission events occurred, whether fallback or human review was triggered, and what the estimated model cost would be for a local demo run.

Batch 3 adds local-first observability and estimated cost reporting. It is not a production monitoring system and not a billing source of truth.

## 2. Run Metrics Schema

`RunMetrics` is defined in `agent/observability/metrics.py`.

Fields include:

- `run_id`
- `trace_id`
- `final_status`
- `model_call_count`
- `input_tokens`
- `output_tokens`
- `estimated_model_cost`
- `tool_call_count`
- `tool_success_count`
- `tool_failure_count`
- `permission_check_count`
- `permission_denied_count`
- `approval_request_count`
- `fallback_count`
- `human_review_count`
- `execution_steps`
- `total_latency_ms`
- `slowest_node_name`
- `slowest_node_latency_ms`
- `task_success`
- `created_at`
- `completed_at`
- `cost_is_estimated`

`cost_is_estimated` is always true in the current local implementation.

## 3. Model Usage Metrics

Current deterministic mode does not call a real model and does not produce real token usage. Batch 3 uses a simple deterministic token estimate for local reporting only. This estimate is stable and testable, but it is not provider billing data.

## 4. Tool and Permission Metrics

Metrics are built from trajectory events:

- `permission_checked` and `permission_denied` increment permission counters.
- `approval_requested` increments approval counters.
- Tool-like events increment tool success/failure counters.
- Events with `fallback_triggered=true` increment fallback counters.
- Events with `human_review_required=true` increment human review counters.

## 5. Estimated Cost Tracking

Model cost policies live in `config/model_costs.yaml`.

Configured providers:

- `deterministic`
- `deepseek`
- `qwen`
- `glm`
- `mock`

Deterministic mode has estimated zero cost because it does not represent real model billing. Other providers use placeholder or `real_config_required` entries unless a future batch connects real provider pricing or billing exports.

## 6. Run Summary Report

`scripts/generate_run_summary_report.py` supports:

- Default mode: run the fixed SaaS demo and print the metrics JSON.
- `--write`: write `reports/latest_run_summary.json` and `reports/latest_cost_summary.md`.
- `--check`: regenerate the fixed demo and validate schema, required fields, estimated-cost labeling, Markdown safety notes, and absence of known sensitive fragments.

The Markdown report is titled `Run Summary and Estimated Cost Report`.

## 7. Relationship to Runtime Governance

Runtime governance records trajectory events. Observability and cost summarize those events into a smaller metrics object that is easier to review in reports, CI checks, and local demos.

The normal `SolutionInsightService` response includes optional `run_metrics` so observability snapshots can show a metrics summary without changing the agent's generation logic.

## 8. What Is Not Implemented Yet

Not implemented in Batch 3:

- Production monitoring.
- Real billing integration.
- Real provider invoice reconciliation.
- Streaming telemetry export.
- Dashboard UI.
- Alerting.
- SLA/SLO tracking.
- Distributed tracing backend.

## 9. Known Limitations

- Token counts may be estimates.
- Costs are estimated for local demo purposes.
- Deterministic mode cost is not real model cost.
- This is not a production billing report.
- This is not a production monitoring system.
- The project does not claim production deployment readiness.
