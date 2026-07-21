# Enterprise Delivery Blueprint

## Business Scenario

An AI solution sales team needs to turn early customer discovery notes into a structured, evidence-grounded solution insight. The output should help decide whether a sales opportunity is actionable, what AI scenarios are relevant, and where human confirmation is needed.

## Core Business Problem

Sales and consulting teams often receive incomplete customer context. A simple AI summary can sound convincing while mixing facts, assumptions, and unsupported recommendations. The business problem is not only content generation; it is controllable, explainable decision support.

## Why Agent Instead of Simple RAG

Simple RAG can retrieve context and draft an answer. This project adds workflow boundaries around that answer:

- Requirement understanding before retrieval.
- Formal evidence separation from shadow diagnostics.
- Fallback when evidence is weak.
- Permission checks for tool-like actions.
- Trajectory events for inspectability.
- Evaluation gate and human review triggers.
- Estimated cost and observability summaries.

The agent pattern is justified when the workflow needs governed steps, not just a single retrieval-augmented response.

## Target Workflow

1. User submits customer requirement context.
2. The service structures the requirement.
3. Formal retriever returns evidence.
4. Shadow retrieval optionally produces diagnostics only.
5. Fallback assessor checks evidence and boundary risk.
6. Generator returns structured solution insight.
7. Runtime governance records trajectory and status.
8. Trajectory evaluation checks path quality.
9. Human review is triggered when needed.
10. Observability report summarizes the run and estimated cost.

## Data and Context Sources

Current local sources:

- Synthetic demo solution data.
- Frozen retrieval benchmark artifacts.
- Local enterprise context fixtures.
- Deterministic demo prompts and responses.
- Local evaluation and human evaluation packet artifacts.

Future enterprise sources could include CRM, ticket, knowledge base, BI, call notes, and delivery playbooks. The current project does not connect to real customer systems.

## System Architecture

The implemented architecture has a formal main path and a diagnostic shadow path. The formal path produces evidence-grounded structured output. The shadow path is isolated and does not modify formal answers.

Runtime governance sits beside the service as a trace, permission, evaluation, review, fallback, and metrics layer.

## Governance and Risk Control

Governance controls include:

- Runtime IDs and trajectory events.
- Runtime status and stop reasons.
- Default-deny permission policy.
- High-risk operation presets.
- Simulated approval lifecycle.
- Fallback taxonomy and recovery decisions.
- Human review trigger policy.
- No fake human scores policy.

These controls are local-first and not production compliance controls.

## Evaluation and Human Review

Evaluation has three layers:

- Formal retrieval benchmark for retrieval quality.
- LLM/deterministic output checks for response contract and provider comparison.
- Trajectory evaluation for governance path quality.

Human review is separate from automated evaluation. Pending review does not mean the output has been accepted by a human.

## Deployment and Integration Presets

Current deployment shape:

- Local CLI.
- Lightweight FastAPI wrapper.
- Local web demo.
- Local reports and JSON artifacts.

Future enterprise integration would require authentication, network controls, secret management, durable storage, real connector permissions, monitoring, audit retention, and customer-specific data policies.

## Cost and ROI Metric Framework

The project can estimate run-level model cost and define ROI metrics for a future pilot. It does not measure real enterprise ROI today.

Cost and ROI reporting should remain clearly labeled as estimated, simulated, designed-only, or unavailable until pilot data exists.

## Current Limitations

- Not a production SaaS.
- No real IAM or enterprise approval workflow.
- No immutable audit log.
- No real enterprise writes.
- No real customer data.
- No completed human scoring by default.
- No real business ROI results.
- No production billing or monitoring integration.

## Next Step Pilot Plan

1. Select one low-risk sales insight use case.
2. Freeze customer-approved data handling rules.
3. Connect read-only enterprise context sources.
4. Define reviewer roles and approval workflow.
5. Run a limited pilot with real reviewer annotations.
6. Measure task success, evidence grounding, intervention rate, latency, and cost.
7. Review rejected outputs and update policy gates.
8. Decide whether write actions remain out of scope or require a separate approval system.
