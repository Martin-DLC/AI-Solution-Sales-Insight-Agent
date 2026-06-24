# AI Solution Sales Insight Agent

> 一个面向企业 AI 解决方案销售场景的可审计分析 Agent，将客户访谈转化为需求洞察、商机判断、AI 机会、方案建议、风险与下一步行动。

这是一个求职展示型企业 Agent MVP，不是生产级自动销售系统。所有最终结果都需要 Human Review。

## Project Charter

本项目的目标是把销售分析从“单次生成一整份大报告”改造成“可验证、可定位、可审计的节点式 Workflow”。

我们关注的是：

- 业务事实是否被正确提取
- 推断是否和证据一致
- 方案是否受候选集约束
- Deal Score 是否可解释
- 失败是否能被准确定位
- 最终结果是否适合 Human Review

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

## Guardrails 设计亮点

1. 未验证销售备注不能成为客户事实
2. Evidence ID 必须来自 Source Index
3. 未确认 Stakeholder 不能直接升级成决策人
4. Solution 只能来自企业方案库和 Top-K 候选
5. Deal Score 由确定性规则计算
6. Final Report 必须通过 Final Validation 并等待 Human Review

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
