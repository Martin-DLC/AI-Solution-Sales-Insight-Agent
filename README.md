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
- Baseline B has not been implemented yet.
- LangGraph, RAG, and web demo have not been implemented yet.
