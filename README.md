# AI Solution Sales Insight Agent

## Status

This project is currently in Sprint 0.

Sprint 0 only establishes the development environment baseline and the minimal project skeleton.

Full agent functionality has not been implemented yet. This project does not currently include RAG, Streamlit, or multi-agent workflows.

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
- Architecture C design is complete.
- Architecture C minimal Workflow skeleton is implemented.
- Architecture C Batch 1A is implemented with formal Fact Extraction and Explicit Need nodes.
- Architecture C now validates evidence cross-references before downstream workflow steps.
- Architecture C Batch 1B is implemented with Underlying Pain and Business Impact nodes.
- Architecture C Batch 2A is implemented with Buying Intent and Stakeholder nodes.
- Architecture C Batch 2B is implemented with Information Gap.
- Architecture C Batch 3A is implemented with AI Opportunity and Solution Recommendation.
- Architecture C Batch 3B is implemented with deterministic lightweight solution retrieval.
- AI Opportunity can explicitly mark opportunities as not suitable for AI or insufficient information.
- Solution Recommendation can only select from retrieved candidates that originate in `available_solution_library`.
- The current retrieval layer is lexical, in-process, deterministic, and does not use RAG or embeddings.
- Architecture C Batch 4A is implemented with pure-code deterministic Deal Score.
- Deal Score uses fixed seven dimensions and every dimension includes evidence and reasoning.
- Deal Score total is calculated by rules; LLM output cannot directly provide the score.
- Deal Score measures opportunity maturity and does not represent close probability.
- Zero-candidate solution paths still produce a limited Deal Score.
- Deal Score does not increase LLM call count.
- Architecture C currently uses Fake LLM for Batch 4A offline tests.
- Risk, Next Best Action, and final report generation are not implemented yet.
- Architecture C business understanding now reaches Information Gap.
- clarification_only now generates concrete clarification questions before human review.
- Information Gap combines Context Sufficiency, Buying Intent unknown factors, and unconfirmed Stakeholders.
- Architecture C nodes use independent Prompt contracts and Pydantic output contracts.
- Architecture C Evidence references are cross-validated by code before downstream workflow steps.
- Architecture C currently contains an offline graph through solution recommendation and human review.
- Architecture C uses Fake LLM and does not call a real model.
- Architecture C has not implemented RAG, Risk, Next Best Action, or final report generation.
- Architecture C has not connected to a real model or RAG.
- Baseline A and Baseline B are both single model calls.
- Baseline B does not use RAG, Workflow, or Critic.
- Dry Run does not consume API.
- Live results are saved under `data/runtime`, which is ignored by Git.
- RAG and web demo have not been implemented yet.
