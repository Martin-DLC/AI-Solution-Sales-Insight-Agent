# AI Solution Sales Insight Agent

## Status

This project is currently in Sprint 0.

Sprint 0 only establishes the development environment baseline and the minimal project skeleton.

Agent functionality has not been implemented yet. This project does not currently include LangGraph, RAG, Streamlit, or multi-agent workflows.

## Python Requirement

Python 3.11 is required.

## Current Scope

- Minimal project structure
- Environment readiness entry point
- Basic environment tests

## Current Progress

- Input Schema is complete.
- Output Schema is complete.
- Hidden Reference Pack Schema is complete.
- JSONL loader and runtime isolation are complete.
- Three Development seed cases have been converted to official JSONL.
- Runtime Cases and Hidden Reference Pack are isolated.
- Official seed dataset validation script is complete.
- Data sync SOP is complete.
- Next stage is Baseline A/B and the model adapter layer.
- Provider-neutral model adapter layer is complete.
- LLM access uses an OpenAI-compatible interface.
- pytest does not make live API calls.
- Real API calls require explicitly running `./.venv/bin/python scripts/smoke_test_llm.py --live`.
- Baseline A/B has not been implemented yet.
- Baseline A plain Prompt runner is complete.
- Baseline A CLI defaults to Dry Run and does not consume API.
- Only `--live` calls the model.
- Live Baseline A outputs are saved under `data/runtime/baseline_runs`, which is ignored by Git.
- Baseline A does not use the structured Output Schema.
- Baseline A plain text Prompt is complete.
- Baseline B high-quality structured Prompt is complete.
- Baseline B uses the full SalesInsightReport Schema.
- Baseline B saves invalid JSON diagnostics separately from Schema validation errors.
- Baseline B v1 showed JSON and Schema adherence failures in live testing.
- Baseline B v1 is preserved and not overwritten.
- Baseline B v2 only strengthens the Prompt contract.
- Baseline B v2 does not use RAG, Workflow, Critic, or automatic repair.
- Running Baseline B v2 requires explicitly passing `--prompt-version baseline_b_v2`.
- Baseline B v2 reduced the live Schema errors from 12 to 5.
- Baseline B v3 only adds owner enum and text specificity contract rules.
- After Baseline B v3, DEV-01-specific Prompt tuning should stop.
- Baseline B v3 is still one model call without automatic repair, RAG, Workflow, or Critic.
- Baseline A/B experiment phase is frozen.
- Baseline B v3 still has 2 Schema errors in the recorded DEV-01 run.
- No additional Baseline B Prompt versions will be added for DEV-01.
- The next architecture phase is Architecture C stepwise Workflow.
- Baseline A and Baseline B are both single model calls.
- Baseline B does not use RAG, Workflow, or Critic.
- Dry Run does not consume API.
- Live results are saved under `data/runtime`, which is ignored by Git.
- LangGraph, RAG, and web demo have not been implemented yet.
