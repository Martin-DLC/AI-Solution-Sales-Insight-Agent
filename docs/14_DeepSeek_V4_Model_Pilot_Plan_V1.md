# DeepSeek V4 Model Pilot Plan V1

## 目标

本轮是 Node Model Benchmark 的单 Provider Pilot，只增加 DeepSeek V4 的真实运行能力和安全护栏，不改变 Workflow 节点逻辑、Prompt、Schema、业务 Validator 或 Benchmark 数据。

## 为什么先做单 Provider Pilot

先用单一 Provider 建立 Live Benchmark 闭环，可以把变量控制在模型规格、Thinking 模式、成本和运行稳定性上，避免把跨 Provider 差异和节点质量判断混在一起。

## 三档配置

- `ds-v4-flash-non-thinking`
- `ds-v4-pro-non-thinking`
- `ds-v4-pro-thinking-high`

这样可以同时比较规模差异和推理方式差异。本轮结论只用于 Pilot，不代表最终市场模型选型。

## 价格快照

- `flash-v4-2026-06`
- `pro-v4-2026-06`
- 价格检查日期：`2026-06-26`

成本估算统一按 cache miss 保守计算。如果 API 没有返回 cache hit 细项，就不猜测 cache hit。

## Live Client 与现有节点关系

Live Benchmark 复用现有 OpenAI-compatible 访问层和 Workflow JSON 返回契约。节点继续使用原有 messages、JSON 输出方式和业务校验逻辑，不做 Prompt 定制。

## Smoke Test步骤

```bash
./.venv/bin/python scripts/run_node_model_benchmark.py \
  --live \
  --configs data/evaluation/model_benchmark/model_configs.deepseek_v4.json \
  --case NB-FE-01 \
  --confirm-live \
  --max-budget-cny 5
```

本轮只实现该能力，不自动执行。

## 48次 Pilot步骤

后续正式 Pilot 使用 16 个 Benchmark Case 和 3 条模型配置，总计 48 次调用。只有 Smoke 路径通过后，才进入完整 Pilot。

## 预算护栏

- `--live` 必须和 `--confirm-live`、`--configs`、`--max-budget-cny` 同时出现
- 达到或超过预算后，在下一次请求前停止
- unknown-cost 请求默认最多允许 1 次，之后停止
- 预算停止会保留已完成结果和 manifest

## Runtime 产物

Live manifest 额外记录：

- `execution_mode`
- `provider_names`
- `pricing_snapshot_ids`
- `max_budget_cny`
- `estimated_cost_cny`
- `unknown_cost_run_count`
- `stopped_by_budget`
- `live_confirmed`
- `selected_model_details`

默认不保存 `reasoning_content`。只有 `capture_debug_artifacts=true` 时才会把它写到运行目录中的调试文件。

## Secret 与数据隔离

- API Key 只使用现有 `LLM_API_KEY`
- 只在显式 `--live --confirm-live` 时延迟加载 `.env`
- Plan、Validate、Replay、测试和 Client 初始化都不读取 `.env`
- 不在日志、异常、artifact 或测试快照中保存密钥

## 当前局限

- Replay 通过不等于 Live 质量通过
- Smoke 通过不等于 48 次 Pilot 通过
- 价格快照未来可能变化
- 不能根据模型品牌预设节点优劣
- 只有真实 Benchmark 结果才能支持后续路由建议

## 后续 Cross-provider 计划

完成单 Provider Pilot 之后，再在同一 Benchmark 契约下扩展更多 Provider，保持 Prompt、数据和业务 Validator 不变，避免为单个模型定制行为。
