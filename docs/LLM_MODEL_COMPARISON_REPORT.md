# LLM Model Comparison Report

## Purpose

这个报告说明 Solution Insight Agent 的 LLM Evaluation Harness v0.2 如何在不破坏 deterministic baseline 的前提下，扩展到可选的真实模型 provider 横评。

## Evaluation Set

- 12 条 `solution_insight_eval_cases`
- 复用现有 rule-based evaluator
- 不使用 LLM-as-judge

评分维度保持不变：

- `schema_validity`
- `section_completeness`
- `evidence_grounding`
- `hallucination_risk`
- `fallback_alignment`
- `chinese_business_clarity`
- `overall_score`

## Deterministic Baseline

`data/evaluation/llm/solution_insight_deterministic_baseline.v1.json` 仍然是唯一冻结的 CI 合同。

它的职责是：

- 保证本地和 CI 可复现
- 保证默认 pytest / preflight 不依赖外部 API
- 作为 provider comparison 的稳定参照系

真实 provider comparison 不会覆盖这份 baseline。

## Supported Providers

当前 comparison harness 支持以下 provider 入口：

- `deterministic`
- `deepseek`
- `qwen`
- `glm`

环境变量约定：

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_MODEL`（可选）
- `QWEN_API_KEY`
- `QWEN_MODEL`（可选）
- `GLM_API_KEY`
- `GLM_MODEL`（可选）

如果 API key 缺失：

- provider 状态记为 `skipped_missing_api_key`
- 不报错
- 不伪造任何真实结果

如果 provider 调用失败：

- provider 状态记为 `failed` 或 `completed_with_case_errors`
- 只记录安全错误摘要
- 不输出 traceback

## Commands

Provider 可用性规划：

```bash
python scripts/run_solution_insight_llm_eval.py \
  --providers deterministic,deepseek,qwen,glm
```

写入 comparison artifact：

```bash
python scripts/run_solution_insight_llm_eval.py \
  --providers deterministic,deepseek,qwen,glm \
  --comparison-write
```

只检查 comparison artifact schema：

```bash
python scripts/run_solution_insight_llm_eval.py --comparison-check
```

## Artifact

comparison artifact 写入：

`data/evaluation/llm/solution_insight_model_comparison.v1.json`

它包含：

- provider 状态
- 各 provider aggregate scores
- per-case scores
- latency summary
- optional token / cost summary
- hallucination / fallback / schema invalid case 列表
- 推荐 provider 字段
- 局限性说明

## Current Interpretation Rules

- 如果只有 deterministic 可运行，那么 artifact 会明确包含 `no_external_provider_results`
- 如果真实 provider 缺 key 或失败，不会伪造成已跑通
- `--comparison-check` 只验证 artifact 可解析和 schema 正确，不要求 byte-for-byte reproducibility

## Next Steps

当前 comparison harness 解决的是“如何安全对接真实 provider”，还没有完成：

- 多模型完整横评
- 人工评分集
- 线上 A/B

因此当前最稳妥的结论仍然是：

- demo 默认使用 deterministic mode
- 真正的 provider 选择要等后续真实对比结果补齐后再下结论
