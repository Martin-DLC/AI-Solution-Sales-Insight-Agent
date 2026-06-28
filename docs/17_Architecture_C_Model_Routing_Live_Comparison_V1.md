# Architecture C Model Routing Live Comparison V1

## 1. 文档目标

本文档用于汇总 v1.1 版本中 Architecture C 模型路由的正式节点级 Pilot、Routing Matrix，以及两条固定 Live 复测链路的脱敏运行结果。

本文档只使用以下冻结事实源：

- `data/evaluation/model_benchmark/formal_pilot_runs.v1.json`
- `data/evaluation/model_benchmark/formal_pilot_summary.v1.json`
- `data/evaluation/model_benchmark/node_model_routing_matrix.v1.json`
- `data/evaluation/model_benchmark/model_configs.deepseek_v4.json`
- 四个固定 Workflow Runtime Run 中的 `run_metadata.json`
- 四个固定 Workflow Runtime Run 中的 `workflow_state.json`
- 四个固定 Workflow Runtime Run 中的 `llm_calls/*/metadata.json`

本文档不读取 Prompt、客户原文、模型原始回答或 `.env`。

## 2. v1.1 版本边界

v1.1 的目标是打通：

- 节点级模型评测
- Routing Matrix 生成
- Architecture C 运行时路由
- Runtime 路由审计
- 固定案例的 Live 复测对比

v1.1 不声称已经实现：

- 端到端稳定 Final Report 产出
- 异构模型切换带来的稳定质量增益
- 生产级成功率或 ROI 结论

## 3. 48 次节点模型 Pilot

正式 Node Model Pilot 只统计四个节点、三个 DeepSeek 配置、四个固定 12-call 批次，共 48 次调用。

冻结统计如下：

| 指标 | 数值 |
| --- | ---: |
| Planned | 48 |
| Completed | 48 |
| Passed | 43 |
| Failed | 5 |
| Request Errors | 0 |
| Unknown Cost Runs | 0 |
| Estimated Cost (CNY) | 0.893536 |

这里的 `43/48` 表示节点级 Pilot 通过数：

- 不是 Architecture C 端到端准确率
- 不是生产级成功率
- 每个节点只有 4 个 Pilot 案例
- 只比较了 DeepSeek 单一 Provider 的 3 个配置

## 4. Routing Matrix

Routing Matrix 只覆盖 4 个已正式评测节点：

| Node | Primary | Fallback | Eligible Models |
| --- | --- | --- | --- |
| `fact_extraction` | `ds-v4-flash-non-thinking` | `ds-v4-pro-thinking-high` | `ds-v4-flash-non-thinking`, `ds-v4-pro-thinking-high` |
| `underlying_pain` | `ds-v4-flash-non-thinking` | `ds-v4-pro-non-thinking` | `ds-v4-flash-non-thinking`, `ds-v4-pro-non-thinking`, `ds-v4-pro-thinking-high` |
| `information_gap` | `ds-v4-flash-non-thinking` | `ds-v4-pro-non-thinking` | `ds-v4-flash-non-thinking`, `ds-v4-pro-non-thinking`, `ds-v4-pro-thinking-high` |
| `solution_recommendation` | `ds-v4-flash-non-thinking` | `ds-v4-pro-thinking-high` | `ds-v4-flash-non-thinking`, `ds-v4-pro-thinking-high` |

不合格模型与原因：

- `fact_extraction`
  - `ds-v4-pro-non-thinking`
  - `schema_validation_failure`
  - `blocking_assertion_failure`
  - `evidence_reference_failure`
- `solution_recommendation`
  - `ds-v4-pro-non-thinking`
  - `blocking_assertion_failure`
  - `candidate_boundary_failure`

当前四个 Primary 都来自 Routing Matrix 的正式选择结果，而不是按模型品牌、Tier 或“更强模型优先”的直觉硬编码。

## 5. Architecture C 路由接入方式

Architecture C 运行时只对以下 4 个节点使用 Routing Matrix：

- `fact_extraction`
- `underlying_pain`
- `information_gap`
- `solution_recommendation`

以下未评测节点继续使用默认模型：

- `explicit_need`
- `business_impact`
- `buying_intent`
- `stakeholder`
- `ai_opportunity`
- `risk`
- `next_best_action`

技术 Fallback 的边界保持严格：

- 只处理技术故障
- JSON、Schema、Business Rule、Evidence 和 Candidate Boundary 失败都不触发技术 Fallback
- `no_eligible_model` 保持 Fail Closed

## 6. DEV-01 历史与路由 Run 对比

固定 Run：

- 历史单模型：`C-DEV-01-20260624T045625Z-d4e5b218`
- 路由版本：`C-DEV-01-20260628T150951Z-9dc43bda`

| Run | Routing | LLM Calls | Prompt Tokens | Completion Tokens | Total Tokens | Latency (ms) | Estimated Cost | Final Failure Node | Final Report |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| DEV-01 historical | No | 7 | 48636 | 14968 | 63604 | 151534 | 未记录 | `information_gap` | No |
| DEV-01 routed | Yes | 9 | 61849 | 18517 | 80366 | 170315 | 0.046596 | `solution_recommendation` | No |

路由版本的实际路由行为：

- 4 个路由节点都使用了 Routing Matrix 指定的 Primary
- 5 个未评测节点使用了 `default_unbenchmarked`
- `fallback_call_count = 0`
- 没有技术 Fallback

结论应如实表达：

- 路由版本推进到了更后的节点
- 但 DEV-01 历史 Run 早于部分 Prompt 合同优化
- 因此这不是严格单变量实验
- 不能把推进完全归因于模型路由

## 7. DEV-05 历史与路由 Run 对比

固定 Run：

- 历史单模型：`C-DEV-05-20260624T052909Z-518d3c69`
- 路由版本：`C-DEV-05-20260628T151426Z-cdb8d70b`

| Run | Routing | LLM Calls | Prompt Tokens | Completion Tokens | Total Tokens | Latency (ms) | Estimated Cost | Final Failure Node | Final Report |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| DEV-05 historical | No | 9 | 63196 | 17886 | 81082 | 164833 | 未记录 | `solution_recommendation` | No |
| DEV-05 routed | Yes | 10 | 71244 | 23969 | 95213 | 223905 | 0.046845 | `risk` | No |

路由版本的实际路由行为：

- 4 个路由节点都使用了 Routing Matrix 指定的 Primary
- 6 个未评测节点使用了 `default_unbenchmarked`
- `fallback_call_count = 0`
- 没有技术 Fallback

结论应如实表达：

- 路由版本通过了 `solution_recommendation` 并推进到 `risk`
- Token 和延迟有所增加
- 仍未生成 Final Report
- 单次运行存在模型输出随机性
- 不能把一次推进写成稳定质量提升

## 8. Runtime 审计与 Fallback 行为

两次路由 Run 的 Runtime 审计都已落盘：

- `model_routing_enabled = true`
- `routing_policy_version = v1`
- `routed_nodes` 已记录
- `fallback_call_count` 已记录
- `models_used` 已记录

两次路由 Run 的单次调用 metadata 中都能看到：

- `selected_model_config_id`
- `selected_model`
- `selected_tier`
- `route_role`
- `fallback_used`
- `routing_policy_version`

本轮复测的实际结果是：

- 两次都没有触发 Fallback
- Schema 和业务质量失败都没有被错误转成技术 Fallback
- 当前 Primary 与 Architecture C 原默认模型都落在 `deepseek-v4-flash` 非思考模式

因此本轮主要验证的是：

- 评测驱动模型选择
- 路由治理
- 未评测节点默认策略
- Runtime 审计
- 技术 Fallback 边界

而不是异构模型切换带来的质量提升。

## 9. 关键工程结论

1. 节点模型 Benchmark、Routing Matrix 和 Runtime 路由链路已经完整打通。
2. 模型路由由 Evaluation 结果驱动，而不是由模型品牌或 Tier 决定。
3. 当前四个 Primary 均由 Routing Matrix 选出，不能因为存在“更强模型”就默认强制切换。
4. 当前 Primary 与 Architecture C 原默认模型均属于 DeepSeek V4 Flash 非思考模式。
5. 本轮不能证明异构模型切换带来了稳定质量提升。
6. 两次复测都推进到了更后的节点，但仍未产生 Final Report。
7. Schema 和业务质量失败没有触发技术 Fallback，符合设计。
8. Human Review 和 Fail Closed 机制保持不变。

## 10. 当前限制

- 复测案例只有 DEV-01 和 DEV-05 两条固定链路
- 两次路由复测都没有触发技术 Fallback，因此还不能说明 Fallback 在真实线上负载下的收益
- Architecture C 仍存在 Token、延迟和节点合同稳定性问题
- 路由矩阵只适用于当前 Prompt、Schema、模型和数据版本

## 11. 下一阶段计划

- 在更多固定案例上复测 Runtime 路由
- 继续收敛节点合同稳定性
- 进入 v1.2 的 Enterprise Knowledge Base 与 RAG 阶段
- 继续把运行时治理与审计能力前移，而不是追求一次性“大模型更强”的错觉
