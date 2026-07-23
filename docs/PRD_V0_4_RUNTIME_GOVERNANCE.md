# AI Solution Sales Insight Agent — PRD V0.4 Runtime Governance

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 文档名称 | AI Solution Sales Insight Agent — PRD V0.4 Runtime Governance |
| 版本 | V0.4 Runtime Governance |
| 更新时间 | 2026-07-23 |
| 适用范围 | AI Solution Sales Insight Agent 从 v0.3 Agent MVP 升级到 Runtime Governance v0.1 的产品范围 |
| 文档目标 | 明确企业级 Agent 产品的业务问题、用户角色、试点场景、功能范围、治理边界、验收标准和后续路线 |

## 2. 产品背景

AI Solution Sales Insight Agent 面向企业 AI 售前、需求分析与方案咨询场景，目标是将客户输入转化为结构化方案洞察，包括客户需求摘要、业务痛点、AI 机会点、方案建议、证据引用、风险提示、fallback 与人工复核状态。

v0.3 阶段已经完成可运行的 Agent MVP，包括 FastAPI `/solution-insight` API、CLI、Agent Demo Console `/demo`、Human Review Console `/human-eval`、Formal Retrieval、Shadow Retrieval、Skills Registry、Context Provider Interface、MCP-style Enterprise Context Mock、LLM Evaluation Harness、Human Evaluation Layer 和 Observability Report。

V0.4 的产品方向从继续增加表面功能，调整为 Runtime Governance v0.1。调整原因是：企业 Agent 进入真实业务流程前，不仅要能生成答案，还要能说明执行过程、权限边界、风险状态、评测依据、人工复核状态、失败处理方式、成本估算和交付治理边界。

Runtime Governance v0.1 是围绕现有 Agent 主链路增加的运行治理层，不替换 v0.3 的需求分析与方案洞察能力。

## 3. 业务问题

在企业 AI 售前与方案咨询场景中，团队需要从客户会议、客户背景、销售备注和方案库中判断客户需求、AI 机会、交付风险和下一步动作。传统方式依赖个人经验，容易出现输出标准不一致、证据链不透明、风险不可追踪和复盘困难等问题。

V0.4 需要解决三层问题：

| 层级 | 问题 | 产品要求 |
| --- | --- | --- |
| 业务问题 | 售前方案洞察依赖人工经验，输出标准不一致，证据和风险难以复盘 | 用 Agent 将客户需求转化为结构化方案洞察 |
| 治理问题 | Agent 执行过程不可追踪，权限不可控，失败不可恢复，审核状态容易失真 | 用 Runtime Governance 管理 trace、permission、evaluation、review、fallback 和 metrics |
| 试点问题 | 企业无法判断哪些能力可试点、哪些仍是 mock / preset / designed-only | 明确 local-first boundary、试点假设、验收指标和 non-goals |

重点问题包括：

- 执行过程不可追踪：无法确认 Agent 经过哪些节点、用了哪些上下文、是否触发 fallback、是否被策略停止。
- Tool 权限不可控：无法区分只读、写入、发送、删除等不同风险级别。
- 高风险操作缺少审批：CRM 写入、Ticket 更新、邮件发送、删除记录等动作不能被 Agent 自动执行。
- 失败后缺少停止、回退和恢复机制：模型失败、检索失败、权限失败、评测失败不应全部进入继续生成。
- 成本与调用链路不可观测：缺少运行步骤、调用次数、延迟、人审触发和 Estimated Cost（估算成本）的统一摘要。
- 人工审核状态容易失真：pending review、completed review、human score、Evaluation Gate decision 必须区分。
- 评测只看最终输出：只评测答案内容会漏掉权限、fallback、Shadow Retrieval、policy stop 等过程风险。

## 4. Business Value

### 4.1 售前效率价值

该 Agent 可帮助售前与解决方案团队更快完成以下工作：

- 客户需求整理。
- 业务痛点识别。
- AI 机会点判断。
- 方案建议生成。
- 风险提示。
- 下一步行动建议。

当前版本不提供真实效率提升百分比，不报告真实 ROI。所有效率与 ROI 指标仅作为未来 pilot 的采集框架。

### 4.2 标准化价值

系统通过结构化输出、formal evidence、fallback notice 和 review status，降低不同人员之间的方案分析差异，让需求分析、证据引用、风险提示和下一步动作更容易复盘。

### 4.3 治理价值

Runtime Governance 的价值不是让 Agent “更聪明”，而是让 Agent：

- 行为可追踪。
- 权限可控制。
- 风险可审核。
- 结果可评测。
- 成本可观测。
- 失败可恢复。

### 4.4 试点价值

当前版本可用于低风险试点前的产品验证、治理机制验证和业务流程验证。试点可以验证 Agent 输出结构是否可用、证据和风险提示是否可复核、人工审核触发是否合理、运行摘要是否支持复盘。

当前没有真实业务 ROI，所有 ROI 指标仅作为未来 pilot 的指标框架。

## 5. 产品目标

V0.4 Runtime Governance 的产品目标如下：

1. 建立可追踪的 Agent runtime trace：系统需要为每次 Agent 运行生成 `run_id` 和 `trace_id`，用于跨节点追踪、问题复盘、治理评估和试点验收。
2. 建立 runtime status 与 policy stop：系统需要记录运行状态，并在达到策略限制时停止继续执行。
3. 建立 trajectory events：系统需要记录需求理解、上下文读取、检索、权限检查、fallback、人审触发、生成和完成等关键事件。
4. 建立 Tool 权限与风险分级：系统需要识别 tool action、permission scope、risk level 和是否需要确认。
5. 建立高风险审批预设：系统需要为 CRM 写入、Ticket 更新、邮件发送、删除记录等高风险动作设计 approval state machine。
6. 建立运行指标与成本估算：系统需要输出 run metrics、token estimate、Estimated Cost 和 run summary。
7. 建立轨迹级 Evaluation Gate：系统不仅需要检查最终输出，也需要检查运行路径是否符合治理规则。
8. 建立 Human Review Trigger 与 Review Queue（人审队列）：系统需要在证据不足、风险较高或评测触发时创建待审核状态。
9. 建立 Retry / Fallback / Recovery 机制：系统需要按错误类型判断 retry、fallback、stop 或 human review。
10. 建立 Model Provider 抽象：系统需要用统一 provider interface 描述模型能力、成本、延迟、健康状态和 fallback 策略。
11. 建立企业交付治理文档和 ROI 指标框架：系统需要支持企业 pilot 范围定义、验收标准和后续 ROI 数据采集设计。

## 6. 用户角色

| 用户角色 | 关注点 |
| --- | --- |
| 售前顾问 / 解决方案顾问 | 如何从客户需求中快速形成结构化方案洞察，并知道哪些结论有证据、哪些需要补充确认 |
| 销售运营负责人 | 如何提升商机分析标准化程度，降低不同人员输出不一致的问题 |
| 企业 AI 项目负责人 | 如何判断 Agent 是否适合进入低风险试点，以及试点范围如何控制 |
| IT / 集成负责人 | 如何评估上下文接入、Tool 权限、系统边界和后续集成方式 |
| 风控 / 合规负责人 | 如何确认高风险操作不会被自动执行，审批和审计如何预设 |
| 人工审核人员 | 如何处理待审核结果，判断是否批准、驳回或要求补充信息 |

## 7. 使用场景

| 使用场景 | 说明 |
| --- | --- |
| AI 方案需求分析 | 将客户会议纪要、背景摘要、销售备注和约束条件整理为结构化需求 |
| 方案洞察生成 | 基于 Formal Retrieval evidence 输出业务痛点、AI 机会点和方案建议 |
| 证据与风险复盘 | 检查每条建议的证据、fallback notice 和人工复核状态 |
| Agent 运行过程审计 | 通过 `run_id`、`trace_id` 和 trajectory events 复盘执行过程 |
| 高风险操作审批预设 | 对写入、发送、删除等高风险动作进入审批或人工复核 |
| 失败原因复盘 | 基于 error taxonomy 和 recovery decision 判断失败类型和处理策略 |
| 试点评估与 ROI 估算 | 用 metrics framework 设计未来 pilot 的成功率、人审率、成本和 ROI 采集方式 |

## 8. 当前版本基线

v0.3 Agent MVP 已完成以下能力：

- FastAPI `/solution-insight` API。
- CLI 本地运行入口。
- Agent Demo Console `/demo`。
- Human Review Console `/human-eval`。
- Formal Retrieval Benchmark。
- Shadow Retrieval Debug。
- Skills Registry 与 skill trace。
- Context Provider Interface。
- MCP-style Enterprise Context Mock。
- LLM Evaluation Harness。
- Human Evaluation Layer。
- Observability Report。
- Fallback 与人工确认建议。
- Deterministic local mode。

v0.3 的价值是提供可运行、可演示、可评测的方案洞察 Agent。V0.4 在此基础上增加 Runtime Governance，不改变 Formal Retrieval answer 的主链路边界。

## 9. Enterprise Pilot Scenario

### 9.1 试点背景

一家 B2B SaaS 企业希望提升 AI 方案售前效率，减少方案分析对个人经验的依赖，并提高客户需求、方案建议和风险提示的可复盘性。

### 9.2 输入数据

试点阶段优先使用只读数据源，例如：

- 客户会议纪要。
- 客户背景摘要。
- 销售备注。
- 方案知识库。
- CRM read-only summary。
- Ticket read-only summary。
- BI summary。

### 9.3 Agent 输出

Agent 输出包括：

- Customer Requirement Summary。
- Business Pain Points。
- AI Opportunity Points。
- Solution Recommendation。
- Evidence Items。
- Risk and Fallback Notice。
- Human Review Status。
- Next Action Suggestion。

### 9.4 Runtime Governance

试点中需要记录：

- `run_id` / `trace_id`。
- Trajectory events。
- Permission checks。
- Fallback status。
- Human review trigger。
- Trajectory evaluation result。
- Run metrics。
- Estimated Cost。

### 9.5 试点验收

试点验收关注：

- 输出结构完整性。
- 证据引用质量。
- 风险识别质量。
- 人审触发合理性。
- 运行轨迹可复盘性。
- Estimated Cost 可解释性。
- 业务方是否认为结果具备可行动性。

不得将试点设计写成真实上线结果，也不得将示例场景写成真实客户结果。

## 10. V0.4 Runtime Governance Scope and Implementation Plan

### 10.1 Batch 1 Runtime Governance Foundation

| 项目 | 内容 |
| --- | --- |
| 目标 | 建立一次 Agent 运行的最小可追踪基础 |
| 核心能力 | `run_id`、`trace_id`、runtime status、trajectory event schema、policy stop、execution step limit、consecutive failure limit |
| 主要产出 | Runtime governance models、TrajectoryRecorder、runtime summary、`config/runtime_limits.yaml`、`docs/AGENT_RUNTIME_GOVERNANCE.md` |
| 验收标准 | 能记录核心节点事件；能导出治理摘要；策略停止和运行限制可被测试；不记录 API key、完整 prompt、benchmark gold 或敏感详情 |

### 10.2 Batch 2 Permission and Approval

| 项目 | 内容 |
| --- | --- |
| 目标 | 建立 Tool 权限、风险分级和审批状态基础 |
| 核心能力 | Tool permission metadata、risk level、default deny policy、high-risk operation preset、approval request lifecycle、approval state machine、simulated approval / rejection |
| 主要产出 | `config/tool_permissions.yaml`、PermissionChecker、ApprovalManager、`docs/PERMISSION_MODEL.md` |
| 验收标准 | 未知 tool 默认拒绝；高风险操作要求 human review；审批状态可进入 pending、approved、rejected、expired；不执行真实 CRM/email/ticket 写操作 |

### 10.3 Batch 3 Observability and Cost

| 项目 | 内容 |
| --- | --- |
| 目标 | 建立运行指标、成本估算和本地报告 |
| 核心能力 | Run metrics、model call count、tool count、permission count、fallback count、human review count、latency、estimated token、Estimated Cost |
| 主要产出 | `config/model_costs.yaml`、RunMetrics、CostTracker、run summary report、`docs/OBSERVABILITY_AND_COST.md` |
| 验收标准 | 能生成 run summary；成本字段明确标记 estimated；deterministic local mode 不冒充真实 billing；报告可通过 `--check` 校验 |

### 10.4 Batch 4 Trajectory Evaluation and Human Review

| 项目 | 内容 |
| --- | --- |
| 目标 | 建立轨迹级评测门和人审触发机制 |
| 核心能力 | Rule-based Trajectory Evaluation、Evaluation Gate、Review Queue Item、review status model、human review trigger |
| 主要产出 | `config/trajectory_evaluation_rules.yaml`、trajectory evaluator、ReviewQueueManager、`docs/TRAJECTORY_EVALUATION_AND_HUMAN_REVIEW.md`、`docs/HUMAN_REVIEW_POLICY.md` |
| 验收标准 | 能基于运行轨迹输出 pass、retry、human_review、stop；pending review 不被当作 completed review；不填充或伪造 human score |

### 10.5 Batch 5 Fallback, Recovery, and Model Provider

| 项目 | 内容 |
| --- | --- |
| 目标 | 建立失败分类、恢复决策和模型 provider 抽象 |
| 核心能力 | Error taxonomy、retry/fallback/stop/human review decision、fallback taxonomy、idempotency key、compensation plan schema、model provider interface、mock provider fallback |
| 主要产出 | `config/recovery_policies.yaml`、`config/model_providers.yaml`、RecoveryDecisionEngine、IdempotencyKeyGenerator、BaseModelProvider、MockModelProvider、`docs/FALLBACK_AND_RECOVERY.md`、`docs/MODEL_PROVIDER_STRATEGY.md` |
| 验收标准 | 不同错误类型能返回不同 recovery decision；idempotency key 可生成和校验；model provider fallback 为 mock/preset，不声称真实生产路由 |

### 10.6 Batch 6 Enterprise Delivery Governance

| 项目 | 内容 |
| --- | --- |
| 目标 | 将 Runtime Governance v0.1 整理为企业交付可讨论的产品材料 |
| 核心能力 | Enterprise governance、human review policy、enterprise delivery blueprint、ROI metric framework、release notes、readiness checklist、gap matrix |
| 主要产出 | `docs/ENTERPRISE_AI_GOVERNANCE.md`、`docs/HUMAN_REVIEW_POLICY.md`、`docs/ENTERPRISE_DELIVERY_BLUEPRINT.md`、`docs/ROI_METRIC_FRAMEWORK.md`、`docs/RUNTIME_GOVERNANCE_V0_1_RELEASE_NOTES.md`、`docs/RUNTIME_GOVERNANCE_V0_1_CHECKLIST.md`、`docs/GOVERNANCE_GAP_MATRIX.md` |
| 验收标准 | 明确 local-first boundary；不声称 production SaaS；不声称真实 IAM、真实审批、真实人工评分、真实 ROI 或真实企业客户数据 |

## 11. 核心用户流程

1. 用户提交 AI 方案需求，包括客户背景、会议纪要、销售备注、行业、现有系统、目标和限制条件。
2. Agent 执行需求理解，提取业务目标、上下文约束和可分析字段。
3. Agent 读取企业上下文，通过 Context Provider Interface 和 MCP-style Enterprise Context Mock 获取本地 fixture 级上下文。
4. Agent 使用 formal retriever 检索正式证据。
5. 如启用 Shadow Retrieval，系统只生成 debug 信息，不影响 Formal Retrieval evidence。
6. Agent 生成结构化方案洞察，包括需求摘要、业务痛点、AI 机会点、方案建议、证据和 fallback 提示。
7. Runtime Governance 记录 trajectory events，包括节点、状态、fallback、人审、权限和完成事件。
8. 系统对工具或工具样操作做 permission check，未知 tool 或超范围 action 默认拒绝。
9. Observability 模块生成 run metrics，包括步骤数、模型调用数、权限检查数、fallback 数、人审数、延迟和 Estimated Cost。
10. Trajectory Evaluation 对运行轨迹做规则评测，输出 pass、retry、human_review 或 stop。
11. 必要时触发 Human Review，创建 pending Review Queue item。
12. 如发生失败，Recovery Decision Engine 根据错误类型进入 retry、fallback、stop 或 human review decision。
13. 最终输出可复盘结果，包括业务输出、证据、fallback 说明、governance summary、run metrics 和必要的人审状态。

## 12. 功能需求

### 12.1 Runtime Trace

| 项目 | 内容 |
| --- | --- |
| 功能描述 | 为每次 Agent 运行建立可追踪的 runtime trace |
| 输入 | 用户请求、任务上下文、节点执行状态、错误与 fallback 信息 |
| 输出 | `run_id`、`trace_id`、runtime status、trajectory events、governance summary |
| 状态 | 已实现 local-first 基础 |
| 规则 | 只记录摘要信息；不记录完整 prompt、API key、traceback dump、benchmark gold 或敏感原文 |
| 验收方式 | `tests/test_runtime_governance_foundation.py`、service response 检查、runtime summary 检查 |

### 12.2 Permission and Approval

| 项目 | 内容 |
| --- | --- |
| 功能描述 | 对 tool 操作进行权限判断、风险分级和审批状态管理 |
| 输入 | Tool name、action、scope、risk level、是否需要确认 |
| 输出 | Permission decision、approval request、approval status、permission trajectory events |
| 状态 | 已实现 local-first 权限与模拟审批 |
| 规则 | 未知 tool 默认拒绝；高风险操作要求 human review；模拟审批不代表真实审批 |
| 验收方式 | `tests/test_permission_and_approval.py`、`config/tool_permissions.yaml` 校验 |

### 12.3 Observability and Cost

| 项目 | 内容 |
| --- | --- |
| 功能描述 | 汇总一次运行的指标、延迟、调用数量和估算成本 |
| 输入 | Trajectory events、model metadata、cost config、运行开始和结束时间 |
| 输出 | RunMetrics、run summary JSON、Estimated Cost report |
| 状态 | 已实现 local-first metrics 和 Estimated Cost |
| 规则 | `cost_is_estimated` 必须明确；Estimated Cost 不等于真实 billing；deterministic local mode 不代表真实模型账单 |
| 验收方式 | `tests/test_observability_and_cost.py`、`scripts/generate_run_summary_report.py --check` |

### 12.4 Trajectory Evaluation

| 项目 | 内容 |
| --- | --- |
| 功能描述 | 基于运行轨迹判断 Agent 是否走过可接受路径 |
| 输入 | Trajectory events、runtime status、permission events、fallback events、Shadow Retrieval 状态 |
| 输出 | Evaluation result、gate decision、trigger reason |
| 状态 | 已实现 rule-based Evaluation Gate |
| 规则 | 检查 policy stop、permission denied、high-risk review gap、fallback explanation、human review consistency、core node presence、Shadow Retrieval 不污染 Formal Retrieval |
| 验收方式 | `tests/test_trajectory_evaluation_and_human_review.py`、`config/trajectory_evaluation_rules.yaml` |

### 12.5 Review Queue

| 项目 | 内容 |
| --- | --- |
| 功能描述 | 当运行风险较高或不确定性较强时创建人审触发项 |
| 输入 | Evaluation gate decision、fallback flag、permission risk、trigger reason |
| 输出 | ReviewQueueItem、review status、pending review |
| 状态 | 已实现 in-memory queue schema 和 pending 状态 |
| 规则 | Pending review 不是 completed review；Human Evaluation Layer 可保持 `not_started`；不伪造 reviewer identity 或 human score |
| 验收方式 | trajectory/human review tests、human eval artifact check、`docs/HUMAN_REVIEW_POLICY.md` |

### 12.6 Fallback and Recovery

| 项目 | 内容 |
| --- | --- |
| 功能描述 | 对错误进行分类，并给出 retry、fallback、stop 或 human review 决策 |
| 输入 | Error type、runtime status、permission result、evaluation result、provider health |
| 输出 | RecoveryDecision、fallback type、stop flag、retry flag、human review flag、idempotency key、compensation plan schema |
| 状态 | 已实现 decision foundation；未执行真实外部恢复 |
| 规则 | Transient error 可 retry；高风险或权限问题进入 human review；策略限制可 stop；不执行真实 rollback 或 compensation |
| 验收方式 | `tests/test_fallback_recovery_and_model_provider.py`、`config/recovery_policies.yaml` |

### 12.7 Model Provider

| 项目 | 内容 |
| --- | --- |
| 功能描述 | 用统一接口描述模型能力、成本、延迟、健康检查和 fallback provider |
| 输入 | Provider config、model metadata、prompt、health check result |
| 输出 | Provider selection、mock response、Estimated Cost、fallback provider decision |
| 状态 | 已实现 mock/preset provider abstraction |
| 规则 | 不声称真实生产模型路由；不声称真实延迟或真实 billing；provider comparison artifact 仍作为现有评测历史 |
| 验收方式 | model provider tests、`docs/MODEL_PROVIDER_STRATEGY.md`、`config/model_providers.yaml` |

### 12.8 Enterprise Delivery Docs

| 项目 | 内容 |
| --- | --- |
| 功能描述 | 为企业试点沟通提供治理、交付、ROI 和 release readiness 文档 |
| 输入 | v0.3 MVP 能力、Batch 1-6 governance 能力、可信边界、验收命令 |
| 输出 | Enterprise governance doc、delivery blueprint、ROI metric framework、release notes、checklist、gap matrix |
| 状态 | 已完成文档化 |
| 规则 | 文档必须明确 local-first、非 production SaaS、无真实企业客户数据、无真实 IAM、无真实审批、无真实人工评分、无真实 ROI |
| 验收方式 | 文档审阅、trust boundary grep、release checklist |

## 13. 非功能需求

| 需求 | 说明 |
| --- | --- |
| 可解释性 | 输出应能解释需求、证据、fallback 原因、人审触发原因和治理摘要 |
| 可审计性 | 每次运行应有 `run_id`、`trace_id`、runtime status 和 trajectory events，但当前不是不可变审计系统 |
| 可测试性 | 核心治理能力应有单元测试和 `--check` 脚本覆盖 |
| 可扩展性 | Tool permission、model provider、recovery policy、trajectory rules 应以配置和接口方式扩展 |
| 可信边界 | 所有模拟、估算、fixture 和 preset 必须明确标注，不得写成真实生产能力 |
| 数据最小化 | Runtime trace 只保存摘要，不保存敏感原文、API key、完整 prompt、benchmark gold 或隐藏参考答案 |
| local-first 可运行 | 无真实 API key、无外部企业系统、无生产依赖时，仍能通过 deterministic local mode、本地 fixture 和测试运行 |

## 14. 评测与验收标准

本节验收标准分为两类：一类是工程验收，用于确认代码、配置、评测脚本和文档之间保持一致；另一类是未来企业 pilot 验收，用于验证业务可用性、治理可解释性和试点边界。当前版本已经具备 local-first 工程验收基础，业务验收指标仍需在真实 pilot 中采集。

### 14.1 单元测试

必须覆盖 Runtime Governance、Permission、Observability、Trajectory Evaluation、Human Review、Fallback、Recovery、Model Provider 和 Solution Insight 主链路。

建议命令：

```bash
./.venv/bin/python -m pytest tests/test_runtime_governance_foundation.py -q
./.venv/bin/python -m pytest tests/test_permission_and_approval.py -q
./.venv/bin/python -m pytest tests/test_observability_and_cost.py -q
./.venv/bin/python -m pytest tests/test_trajectory_evaluation_and_human_review.py -q
./.venv/bin/python -m pytest tests/test_fallback_recovery_and_model_provider.py -q
./.venv/bin/python -m pytest tests/test_solution_insight_service.py -q
./.venv/bin/python -m pytest tests/test_solution_insight_api.py -q
./.venv/bin/python -m pytest tests/test_solution_insight_observability.py -q
```

### 14.2 全量 pytest

```bash
./.venv/bin/python -m pytest -q
```

### 14.3 Formal Retrieval Check

```bash
./.venv/bin/python scripts/run_retrieval_benchmark_v2.py --check
```

验收重点：Formal Retrieval 冻结结果可复现，Shadow Retrieval 不改写 Formal Retrieval answer。

### 14.4 LLM Eval Check

```bash
./.venv/bin/python scripts/run_solution_insight_llm_eval.py --check
./.venv/bin/python scripts/run_solution_insight_llm_eval.py --comparison-check
```

验收重点：deterministic baseline 稳定；provider comparison 可解析；不把 provider comparison 写成生产模型质量保证。

### 14.5 Human Eval Artifact Check

```bash
./.venv/bin/python scripts/build_solution_insight_human_eval_packet.py --check
./.venv/bin/python scripts/summarize_solution_insight_human_eval.py --check
```

验收重点：human eval packet 和 summary 可校验；human review status 可以是 `not_started`；不伪造人工评分。

### 14.6 Run Summary Check

```bash
./.venv/bin/python scripts/generate_run_summary_report.py --check
```

验收重点：run metrics schema、Estimated Cost 标记、报告安全说明均通过校验。

### 14.7 Preflight Check

```bash
./scripts/preflight.sh
```

验收重点：项目基础预检通过，Git 状态符合预期。

### 14.8 Trust Boundary Grep

```bash
grep -Rni "production deployed\|real customer\|真实客户\|生产上线\|已上线\|真实人工评分\|真实业务结果\|真实ROI\|真实 ROI" README.md docs/ || true
```

验收重点：命中内容只能出现在否定语境、边界说明或历史数据源示例中，不能出现正向夸大生产能力的表达。

### 14.9 Pilot Business Acceptance Metrics

| 指标 | 说明 | 当前状态 |
| --- | --- | --- |
| 输出结构完整率 | Agent 输出是否包含需求摘要、痛点、机会点、方案建议、证据、风险提示和下一步动作 | designed_only |
| 证据可追溯率 | 关键建议是否能追溯到 Formal Retrieval evidence | designed_only |
| 人审触发合理性 | 高风险、不确定或 fallback 场景是否进入 pending review | partially_implemented |
| 业务可行动性评分 | 业务方判断输出是否能支持下一步售前动作 | not_available |
| 单次运行估算成本 | 基于 run metrics 和 Estimated Cost 形成成本估算 | implemented / estimated |
| 运行轨迹可复盘性 | 是否可以通过 `run_id`、`trace_id` 和 trajectory events 复盘执行过程 | implemented |
| 风险提示有效性 | 是否能明确指出 fallback、权限、边界或人工复核原因 | partially_implemented |
| 试点任务成功率 | 在真实 pilot 中统计 Agent 输出被接受或进入下一步动作的比例 | not_available |

这些指标不得被写成真实提升百分比、真实 ROI 或已完成业务结果。`designed_only`、`implemented / estimated` 和 `not_available` 仅表示当前产品与试点指标框架的准备状态。

## 15. Enterprise Pilot Assumptions

1. 试点场景限定在 AI 售前方案洞察与需求分析。
2. 优先接入只读数据源，例如知识库、CRM read-only、Ticket read-only 或 BI summary。
3. Agent 输出仅作为方案分析和决策辅助，不直接代表企业向客户作出正式商业承诺。
4. 不自动执行 CRM 写入、Ticket 更新、邮件发送、删除记录等外部系统写操作。
5. 高风险操作必须进入人工审批或人工复核。
6. 试点期间所有成本、ROI、任务成功率和人审率均需按真实运行数据采集，不能使用模拟数据代替正式结论。
7. Runtime trace、Evaluation Gate、Review Queue 和 run summary 作为试点验收的重要依据。
8. 当前版本仍是 local-first reference implementation，不是 production SaaS。

## 16. 可信边界

V0.4 必须集中说明以下边界：

- 当前是 local-first reference implementation。
- 不是 production SaaS。
- 没有真实企业客户数据。
- 没有真实 IAM。
- 没有真实审批系统。
- 没有真实人工评分。
- 没有真实 ROI。
- MCP-style mock 不等于真实生产 MCP 集成。
- Estimated Cost 不等于真实 billing。
- Runtime trace 不是不可变审计日志。
- Review Queue pending 不等于人工审核完成。
- Model Provider fallback 当前是 mock / preset，不等于生产模型路由。

## 17. Non-goals

V0.4 明确不做以下事项：

- 真实 CRM 写入。
- 真实 Ticket 更新、邮件发送或删除记录。
- 真实 RBAC。
- 真实审批平台。
- 真实多租户 SaaS。
- Kubernetes。
- 复杂 Dashboard。
- 真实人工评分伪造。
- 真实业务 ROI 伪造。
- 为了表面功能数量而堆更多 Agent。
- 把 MCP-style mock 写成真实生产 MCP 集成。
- 把 Estimated Cost 写成真实 billing。

## 18. 后续 Roadmap

### 18.1 Read-only Context Provider Pilot

选择一个低风险、只读企业上下文源作为 pilot，例如知识库、CRM read-only 或 ticket read-only。

### 18.2 Human Review Small-sample Validation

选择少量代表性 case，由真实业务审核人员对 actionability、证据充分性、风险提示质量进行人工标注。只有真实 reviewer 标注后，才更新 human evaluation summary。

### 18.3 Real Model Provider Smoke Test

在不影响 deterministic baseline 的前提下，对一个真实模型 provider 做 smoke test，记录结构化输出稳定性、延迟、失败类型和真实 usage 字段。

### 18.4 Lightweight Internal Pilot Deployment

在保留 local-first 能力的基础上，考虑单机服务、内部 console 环境或只读 pilot 环境。暂不引入 Kubernetes、复杂 dashboard 或多租户 SaaS。

### 18.5 Pilot Enablement and Stakeholder Training

围绕企业低风险试点，整理面向售前团队、业务审核人员、技术集成人员和项目负责人的使用说明、治理边界说明、试点验收清单和常见问题。目标是让不同角色理解 Agent 的适用范围、不可自动执行的高风险操作、人工审核触发规则、成本估算方式和试点成功指标。

## 19. Change Log

| Version | Date | Change Summary |
| --- | --- | --- |
| V0.3 | 2026-07 | Completed Agent MVP with solution insight generation, Formal Retrieval, Shadow Retrieval, Agent Demo Console, Human Review Console and evaluation foundation |
| V0.4 | 2026-07 | Added Runtime Governance v0.1, including runtime trace, permission and approval, observability and Estimated Cost, Trajectory Evaluation, Review Queue, fallback and recovery, model provider abstraction and enterprise delivery governance |
