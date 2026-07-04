# AI Solution Sales Insight Agent

一个面向企业 AI 解决方案销售场景的可审计 Sales Insight Agent，将客户访谈、销售备注和企业方案资料转化为结构化需求洞察、商机资格判断、AI 机会、方案建议、风险识别与下一步行动。

系统通过 Evidence Grounding、节点级 Schema、跨节点 Business Rules、候选方案约束、确定性 Deal Score、Final Validation 和 Human Review，将传统的“一次性生成销售报告”升级为可验证、可定位、可追踪的企业级 Agent Workflow。

## Project Charter

本项目的目标是把销售分析从“单次生成一整份大报告”改造成“可验证、可定位、可审计的节点式 Workflow”。

我们关注的是：

- 业务事实是否被正确提取
- 推断是否和证据一致
- 方案是否受候选集约束
- Deal Score 是否可解释
- 失败是否能被准确定位
- Human Review Gate 的输入是否达到业务审批标准

## Evaluation Rubric

这个项目的好坏，不看“模型说得多漂亮”，主要看以下几件事：

- 证据是否 grounded
- Schema 是否稳定遵守
- 跨节点业务规则是否一致
- 候选边界是否被尊重
- 纯代码节点是否可验证
- 失败是否能被清晰归类
- 是否保留 Human Review 边界

## 业务问题

传统销售分析常见的问题是：

- 客户需求、痛点和事实混在一起
- 销售容易把积极联系人误判成决策人
- LLM 容易推荐企业并不存在的方案
- 大模型生成的 Deal Score 不可解释
- 单 Prompt 复杂 JSON 难以稳定遵守业务合同
- 错误通常只能在整份报告完成后发现

## 项目核心能力

1. Evidence-grounded Fact Extraction
2. Explicit Need / Underlying Pain / Business Impact
3. Buying Intent 与 Stakeholder 判断
4. Information Gap 与澄清问题
5. AI Opportunity 适配性判断
6. 受候选集约束的 Solution Recommendation
7. 纯代码 Deal Score
8. Risk、Next Best Action、Final Validation 与 Human Review

## Architecture C 简图

```mermaid
flowchart LR
    A[Customer Input] --> B[Evidence & Facts]
    B --> C[Needs & Business Impact]
    C --> D[Buying Intent & Stakeholders]
    D --> E[Information Gaps]
    E --> F[AI Opportunity]
    F --> G[Solution Retrieval]
    G --> H[Solution Recommendation]
    H --> I[Deterministic Deal Score]
    I --> J[Risk & Next Best Action]
    J --> K[Report Composer]
    K --> L[Final Validation]
    L --> M[Human Review]
```

这张图只表达主流程，不展开每个节点的全部细节。

## 为什么比较 A / B / C

| Architecture | 方式 | 优点 | 主要限制 |
| --- | --- | --- | --- |
| A | 普通单 Prompt 文本输出 | 快、便宜 | 缺少 Schema 和业务规则控制 |
| B | 单次完整 JSON Schema 输出 | 结构更强 | 复杂合同仍不稳定 |
| C | 分节点 Workflow 与 Guardrail | 可定位、可隔离、可审计 | Token 和延迟更高 |

如实地说：

- A 两次都返回文本，但不等于业务正确
- B 最终仍未生成完整合法报告
- C 真实实验尚未生成稳定的 Live Final Report
- C 的价值主要体现在发现并隔离不合法结果

## 冻结实验结果

| 运行 | 调用数 | Tokens | 最后停止节点 |
| --- | ---: | ---: | --- |
| DEV-01 | 7 | 63,604 | Information Gap |
| DEV-04 | 3 | 23,879 | Underlying Pain |
| DEV-05 v1 | 1 | 5,917 | Fact Extraction |
| DEV-05 v2 | 9 | 81,082 | Solution Recommendation |

补充说明：

- Evidence 合同 v2 让 DEV-05 从第 1 个 LLM 节点推进到了第 9 个
- 4 次运行都没有让不合法结果进入最终报告
- 当前 Live Final Report 成功率为 0，这一点不回避
- 详细分析见 [A/B/C 实验总结](docs/08_Architecture_ABC_Experiment_Report_V1.md)

## v1.1 进展

- 12 个 Development Cases
- 16 个 Node Benchmark Cases
- 48 次 DeepSeek V4 节点 Pilot
- Node Model Routing Matrix
- Architecture C 运行时路由
- Runtime 路由审计
- DEV-01 和 DEV-05 路由 Live 复测

## v1.1 实验结论

- 48 次节点 Pilot 中 43 次通过、5 次失败
- 0 request error
- 总估算成本 0.893536 元
- Routing Matrix 为 4 个节点选出 Primary 和 Fallback
- 两次路由复测都推进到了更后的节点
- 仍未生成 Live Final Report
- 当前不能证明异构模型切换带来稳定质量增益

## Guardrails 设计亮点

1. 未验证销售备注不能成为客户事实
2. Evidence ID 必须来自 Source Index
3. 未确认 Stakeholder 不能直接升级成决策人
4. Solution 只能来自企业方案库和 Top-K 候选
5. Deal Score 由确定性规则计算
6. Final Report 必须通过 Final Validation；在进入客户沟通、方案决策或外部系统前，由 Human Review Gate 完成业务审批

## 技术栈

- Python
- Pydantic
- LangGraph
- DeepSeek OpenAI-compatible API
- Provider-neutral LLM Adapter
- Deterministic lexical retrieval
- Pytest
- JSONL evaluation dataset

本项目没有使用：

- FAISS
- Vector Database
- Embedding RAG 主链路
- Multi-Agent
- LangSmith
- Database
- UI

## 快速开始

Dry Run：

```bash
python scripts/run_workflow_c.py --case DEV-01
```

这不会消耗 API。

Live Run：

```bash
python scripts/run_workflow_c.py --case DEV-01 --live
```

说明：

- 需要本地 `.env`
- 不要提交 `.env`
- Live 运行会产生 Token 成本
- 运行产物保存在 Git 忽略的 `data/runtime` 目录

详细步骤见 [Demo 与复现指南](docs/10_Demo_and_Reproduction_Guide_V1.md)。

### 最小端到端 Service CLI

当前仓库已提供一个最小可运行的作品集级 CLI Service：

```bash
./.venv/bin/python run.py solution-insight \
  --query "一家中型 SaaS 公司想提升销售线索转化和客户成功效率" \
  --industry "SaaS" \
  --shadow
```

说明：

- 正式证据仍来自当前 formal lexical retriever
- `--shadow` 只输出层级候选 debug，不影响正式 evidence
- 默认可在无 API Key 情况下运行 deterministic mode
- 当前由于 Retrieval v2 仍未通过正式 Blocking Gate，输出默认保留人工确认建议

### 最小 FastAPI 服务

本仓库也提供一个最小 HTTP 包装层，默认同样可以在无 API Key 情况下运行：

```bash
./.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

方案洞察请求：

```bash
curl -X POST http://127.0.0.1:8000/solution-insight \
  -H 'Content-Type: application/json' \
  -d '{
    "user_query": "一家中型 SaaS 公司想提升销售线索转化和客户成功效率",
    "industry": "SaaS",
    "company_size": "中型",
    "current_systems": ["CRM", "客服系统"],
    "target_goal": "提升转化和客户成功效率",
    "constraints": ["不改变现有CRM主流程"],
    "enable_shadow_retrieval": true,
    "llm_mode": "deterministic"
  }'
```

返回字段包括：

- 需求摘要
- 业务痛点
- AI 机会点
- 推荐方案方向
- 证据列表
- 证据完整性状态
- fallback / 人工确认建议
- 可选 shadow retrieval debug

当前限制：

- Boundary validation 仍是 blocked_with_known_limitations
- Hierarchical retrieval 只作为 shadow
- deterministic mode 是默认模式

## 仓库结构

```text
agent/workflow_c/
schemas/
evaluation/
data/evaluation/
docs/
scripts/
tests/
```

- `agent/workflow_c/`：Architecture C 的 Workflow、节点、运行器和留痕
- `schemas/`：输入与输出的 Pydantic 模型
- `evaluation/`：Baseline、Prompt 合同和评估相关内容
- `data/evaluation/`：正式种子数据集
- `docs/`：架构说明、实验总结和复现文档
- `scripts/`：运行、校验和 Smoke Test 脚本
- `tests/`：单元测试和回归测试

## 当前限制

- 真实模型尚未完成端到端 Final Report
- 节点较多，Token 和延迟偏高
- 当前检索是 lexical retrieval，不是向量 RAG
- 当前只使用 3 个种子案例进行重点实验
- 当前不包含 UI、CRM 写入和自动外部操作
- 当前不做自动重试和自动修复

## 项目展示价值

这个项目主要展示的是：

- AI 产品需求拆解
- 企业 Agent Workflow 设计
- LLM 业务合同与 Guardrail
- Evaluation 与 Failure Taxonomy
- 成本、延迟和可靠性权衡
- 从 Baseline 到可审计架构的演进

## 文档导航

- [Project Charter](README.md#project-charter)
- [Evaluation Rubric](README.md#evaluation-rubric)
- [Workflow Contract](docs/07_Architecture_C_Workflow_Contract_V1.md)
- [A/B/C Experiment Report](docs/08_Architecture_ABC_Experiment_Report_V1.md)
- [System Architecture and Workflow](docs/09_System_Architecture_and_Workflow_V1.md)
- [Demo and Reproduction Guide](docs/10_Demo_and_Reproduction_Guide_V1.md)
- [Data Sync SOP](docs/06_Dataset_Sync_SOP_V1.md)
- [Node Model Routing Matrix V1](docs/15_Node_Model_Routing_Matrix_V1.md)
- [Architecture C Model Routing V1](docs/16_Architecture_C_Model_Routing_V1.md)
- [Architecture C Model Routing Live Comparison V1](docs/17_Architecture_C_Model_Routing_Live_Comparison_V1.md)

## Roadmap

- v1.0: Architecture A/B/C 与可审计 Workflow，完成
- v1.1: Model Evaluation & Routing，完成
- v1.2: Enterprise Knowledge Base & RAG，下一阶段
- v1.3: Agent Skills & MCP
- v1.4: Harness、权限与成本优化
