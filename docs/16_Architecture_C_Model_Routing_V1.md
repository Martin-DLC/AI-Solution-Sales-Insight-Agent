# Architecture C Model Routing V1

## 1. 为什么需要节点级模型路由

Architecture C 的不同节点对模型能力、延迟和成本的敏感度并不相同。把所有节点固定到单一模型，会把高成本节点和低复杂度节点绑在一起，也会让局部技术故障影响整条链路。V1 路由的目标，是在不改变 Prompt、Schema 和业务校验规则的前提下，把已经完成正式 Pilot 的节点接到受控的模型选择策略上。

## 2. 48 次 Pilot 如何产生 Routing Matrix

当前 Routing Matrix 只来自正式 Node Model Pilot 的四个 12-call 批次，总计 48 次调用。矩阵文件是已冻结的只读输入，不在运行时动态重算，也不从 `data/runtime` 反推选择结果。

## 3. 四个路由节点

V1 只对以下四个节点启用路由：

- `fact_extraction`
- `underlying_pain`
- `information_gap`
- `solution_recommendation`

## 4. 未评测节点为何继续使用 Default 模型

以下节点尚未进入正式路由评测：

- `explicit_need`
- `business_impact`
- `buying_intent`
- `stakeholder`
- `ai_opportunity`
- `risk`
- `next_best_action`

因此它们继续使用 Architecture C 当前默认模型，避免把没有 Benchmark 依据的猜测引入运行时。

## 5. Primary 选择原则

Primary 和 Fallback 都由 `data/evaluation/model_benchmark/node_model_routing_matrix.v1.json` 显式给出，并要求对应 `config_id` 必须存在于 `data/evaluation/model_benchmark/model_configs.deepseek_v4.json`，且属于该节点的 `eligible_model_config_ids`。

## 6. Fallback 只处理技术故障

Fallback 只在以下技术失败发生时启用一次：

- timeout
- authentication_error
- rate_limit
- provider_error
- network_error
- invalid_provider_response

每个节点最多执行：

`Primary 一次 -> 技术失败 -> Fallback 一次`

## 7. 为什么质量失败不触发 Fallback

以下失败属于模型质量结果，而不是 Provider 可用性问题，因此不触发 Fallback：

- JSON 解析失败
- Schema 校验失败
- Business Rule 失败
- Evidence 校验失败
- Candidate Boundary 失败
- Blocking Assertion 失败

如果这些失败触发模型切换，会把“质量问题”伪装成“路由问题”，破坏实验可解释性。

## 8. `no_eligible_model` 的 Fail Closed 策略

当某个已路由节点在矩阵中标记为 `no_eligible_model` 时：

- 不自动回退到默认模型
- 不自动选择别的候选模型
- 不发起 API 请求
- 直接进入现有 Human Review 路径

Dry Run 会提前显示 `Routing unavailable for: <node_name>`。

## 9. Dry Run 与 Live 命令

Dry Run：

```bash
python scripts/run_workflow_c.py --case DEV-05 --model-routing
```

特点：

- 只加载并校验路由策略
- 不读取 `.env`
- 不创建 LLM Client
- 不发起网络请求
- 不创建 runtime 目录

Live：

```bash
python scripts/run_workflow_c.py --case DEV-05 --live --model-routing
```

只有显式加上 `--model-routing` 才会启用节点级模型路由。

## 10. Runtime 审计字段

启用路由后，单次 LLM 调用会追加以下审计字段：

- `routing_enabled`
- `selected_model_config_id`
- `selected_provider`
- `selected_model`
- `selected_tier`
- `thinking_mode`
- `reasoning_effort`
- `route_role`
- `fallback_used`
- `fallback_reason`
- `routing_policy_version`

Run Metadata 会追加：

- `model_routing_enabled`
- `routing_policy_version`
- `routing_matrix_file`
- `model_configs_file`
- `routed_nodes`
- `unavailable_routed_nodes`
- `fallback_call_count`
- `models_used`

这些字段不保存 API Key、不保存 Authorization，也不保存 `.env` 内容。

## 11. 成本计算

V1 继续复用现有 Usage 和 Pricing 快照。若 Primary 技术失败、Fallback 成功：

- 两次调用都保留 Call Record
- 两次调用的 Token 与 estimated cost 都计入 Run 总成本

## 12. 当前限制

- 路由只适用于当前 Prompt、Schema 和数据版本
- 未评测节点仍走默认模型
- 不包含质量失败后的自动修复
- 不包含动态重算 Routing Matrix
- 不包含多级 Fallback

## 13. v1.1E2 完整案例复测计划

下一步需要在固定 Routing Matrix 下进行完整案例复测，验证：

- 路由后的端到端稳定性
- fallback 触发频率
- 各节点实际成本与延迟分布
- Human Review 收口比例
- 默认模型与路由模型的最终差异
