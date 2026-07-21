# ROI Metric Framework

## Scope

This framework defines metrics for a future enterprise pilot of the Solution Insight Agent. It does not report real enterprise ROI, real customer outcomes, or real business results.

Current project data is local, synthetic, estimated, or designed for future measurement. Cost is estimated. Human scoring is incomplete until real reviewers provide annotations.

Allowed current status values:

- `implemented`
- `estimated`
- `simulated`
- `designed_only`
- `not_available`

## Metrics

| Metric Name | Definition | Formula | Data Source | Current Status | Notes |
| --- | --- | --- | --- | --- | --- |
| `task_success_rate` | Share of runs that complete with a usable governed response. | Successful tasks / total tasks. | Run metrics and response status. | `implemented` | Measures local task completion, not real business success. |
| `human_intervention_rate` | Share of runs requiring human review or confirmation. | Runs with human review required / total runs. | Runtime governance summary and review queue trigger. | `implemented` | High values may indicate healthy risk control or poor automation readiness. |
| `evidence_grounding_rate` | Share of outputs with sufficient formal evidence. | Outputs meeting evidence threshold / total outputs. | Formal retrieval result and fallback assessment. | `implemented` | Formal retriever limitations still apply. |
| `fallback_rate` | Share of runs where fallback is triggered. | Runs with fallback / total runs. | Runtime events and run metrics. | `implemented` | Indicates boundary, evidence, model, or tool uncertainty. |
| `average_task_latency` | Average elapsed runtime per task. | Sum task latency / total tasks. | Run metrics. | `implemented` | Local latency only; not production SLO. |
| `estimated_cost_per_run` | Estimated model cost per run. | Estimated model cost / total runs. | Cost tracker and model cost config. | `estimated` | Not provider billing data. |
| `estimated_cost_per_successful_task` | Estimated model cost for successful governed tasks. | Estimated model cost / successful tasks. | Cost tracker and task success flag. | `estimated` | Undefined when successful task count is zero. |
| `review_rejection_rate` | Share of reviewed items rejected by humans. | Rejected review items / completed review items. | Future human review workflow. | `not_available` | No real human review outcomes yet. |
| `business_actionability_score` | Human score for whether the output can drive a next sales action. | Average reviewer actionability score. | Future human annotation. | `not_available` | No fake human scores are allowed. |
| `time_saved_per_task` | Estimated manual effort avoided per completed task. | Baseline manual minutes - agent-assisted minutes. | Future pilot time study. | `designed_only` | Requires measured baseline. |
| `manual_review_workload` | Human review load created by the agent. | Review items per period or review minutes per period. | Future review queue and reviewer logs. | `designed_only` | Queue trigger exists, but no real staffing data. |
| `automation_coverage_rate` | Share of target workflow steps handled without manual execution. | Automated governed steps / total target workflow steps. | Future pilot workflow mapping. | `designed_only` | Must exclude high-risk writes unless separately approved. |

## Interpretation Rules

- Do not present these metrics as real customer results.
- Do not infer revenue lift without pilot data.
- Do not convert estimated cost into ROI without measured business impact.
- Do not treat pending review as accepted output.
- Do not treat deterministic demo success as production success.

## Pilot Data Needed

A future pilot should collect:

- Real task volume.
- Reviewer decisions and notes.
- Manual baseline effort.
- Agent-assisted effort.
- Real provider token usage and cost.
- Business action outcomes.
- Rejection reasons and policy gate outcomes.
