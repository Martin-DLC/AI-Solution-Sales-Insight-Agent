# Demo Script

## 1. 30 秒项目介绍

“AI Solution Sales Insight Agent 是一个 local-first AI Agent MVP，用于把客户业务需求整理成结构化洞察。它把正式检索证据、fallback 机制、人工确认和 shadow 诊断放进同一条可演示的服务链路里。”

## 2. Demo 前准备

建议先启动服务：

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

可选检查：

```bash
curl http://127.0.0.1:8000/health
```

## 3. Web Demo 演示步骤

打开：

```text
http://127.0.0.1:8000/demo
```

建议讲解顺序：

1. 展示左侧输入表单
2. 点击 `Load SaaS Example`
3. 说明默认使用 deterministic mode
4. 点击 `Run Agent`
5. 依次讲 Requirement Summary、Pain Points、AI Opportunity、Proposed Solution
6. 展示 Evidence、Fallback、Enterprise Context、Skill Trace
7. 最后点开 Shadow Debug 和 Raw JSON

重点说明：

- 正式答案只依赖 formal retriever
- shadow retrieval 只做诊断
- fallback 负责暴露证据不足和边界风险

## 4. CLI 演示步骤

```bash
./.venv/bin/python run.py solution-insight \
  --query "一家中型 SaaS 公司想提升销售线索转化和客户成功效率" \
  --company-id demo_saas_001 \
  --industry "SaaS" \
  --shadow \
  --llm-mode deterministic
```

讲解顺序：

1. 输入是普通业务语言
2. 输出是结构化 JSON
3. evidence 只来自正式检索链路
4. `--shadow` 只增加 debug 视图
5. 无 API key 也可以稳定复现

## 5. API 演示步骤

请求示例：

```bash
curl -X POST http://localhost:8000/solution-insight \
  -H "Content-Type: application/json" \
  -d '{
    "user_query": "一家中型 SaaS 公司想提升销售线索转化和客户成功效率",
    "company_id": "demo_saas_001",
    "industry": "SaaS",
    "company_size": "中型",
    "current_systems": ["CRM", "客服系统"],
    "target_goal": "提升转化和客户成功效率",
    "constraints": ["不改变现有CRM主流程"],
    "enable_shadow_retrieval": true,
    "llm_mode": "deterministic"
  }'
```

适合强调：

- 输入和输出契约清晰
- Web Demo 只是 `/solution-insight` 的展示层
- API、CLI 和 Demo 共用同一个 service

## 6. 如何解释 Shadow Retrieval

建议统一表述：

- 正式 evidence 只来自 formal retriever
- shadow retrieval 是旁路诊断链路
- 它帮助观察 hierarchical candidate pool 的覆盖情况
- 它不会改写正式 evidence，也不会进入正式 prompt

## 7. 如何解释 Fallback

当 `fallback_recommended=true` 时，可以这样解释：

- 系统没有伪造结论
- 当前证据不足或边界存在风险
- 需要人工确认或补充资料
- 这是为了控制风险，而不是隐藏失败

## 8. 如何展示 Observability

可选运行：

```bash
./.venv/bin/python scripts/run_solution_insight_observability_demo.py --write
```

然后展示：

- `data/observability/latest_solution_insight_snapshot.json`
- `data/observability/latest_solution_insight_report.md`

讲解重点：

1. formal path 和 shadow path 被分开展示
2. provider trace 体现 CRM / Ticket / BI / Knowledge 的上下文状态
3. fallback reasons 会被明确保留
4. debug 信息不会污染正式输出

## 9. 如何描述当前边界

建议保持公开表述一致：

- 这是一个 local-first MVP
- 当前 formal retriever 尚未通过最终 blocking gate
- hierarchical retrieval 仍然只在 shadow 模式下使用
- deterministic mode 主要用于演示和可复现测试

## 10. 推荐 Demo Recording 顺序

0:00 - Project overview
0:20 - Open Web Demo
0:40 - Load SaaS Example
1:00 - Show generated insight
1:20 - Show evidence / fallback / enterprise context
1:40 - Show skill trace / shadow debug
2:00 - Show human review workflow or observability report
