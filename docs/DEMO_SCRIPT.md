# Demo Script

## 1. 30 秒项目介绍

“AI Solution Sales Insight Agent 是一个面向 AI 解决方案售前和咨询场景的结构化分析 Agent。它会把客户需求整理成可审计的洞察，结合正式检索证据、fallback 机制和人工确认边界，输出一份更适合企业落地的 AI 方案建议。”

## 2. CLI 演示步骤

```bash
python run.py solution-insight \
  --query "一家中型 SaaS 公司想提升销售线索转化和客户成功效率" \
  --industry "SaaS" \
  --shadow \
  --llm-mode deterministic
```

讲解顺序：

1. 先展示输入是普通业务语言
2. 再展示输出是结构化 JSON
3. 指出 evidence 只来自 formal retriever
4. 说明 `--shadow` 只显示 debug，不改变正式答案
5. 说明 deterministic mode 可以在无 API key 的情况下运行

## 3. API 演示步骤

启动服务：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

健康检查：

```bash
curl http://localhost:8000/health
```

请求示例：

```bash
curl -X POST http://localhost:8000/solution-insight \
  -H "Content-Type: application/json" \
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

## 3.1 Web Demo 演示步骤

启动：

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000/demo
```

建议讲解顺序：

1. 先展示左侧输入表单
2. 点击 `Load SaaS Example`
3. 点击 `Run Agent`
4. 依次讲 Requirement Summary、Evidence、Fallback、Enterprise Context、Skill Trace
5. 最后点开 Shadow Debug 和 Raw JSON
6. 强调 demo 页面只是 `/solution-insight` 的展示层

## 3.2 推荐录屏顺序

1. 先展示 `/demo`
2. 再展示 observability report
3. 再讲 evaluation 与 limitations

## 4. 如何解释 shadow retrieval

可以这样说：

- 正式答案仍然只使用 formal retriever
- shadow retrieval 是一条旁路 debug
- 它用于观察 hierarchical candidate pool 的覆盖和边界表现
- 它不会污染正式 evidence，也不会改写正式输出

## 4.1 如何展示 observability report

可以在 CLI 演示后接着跑：

```bash
python scripts/run_solution_insight_observability_demo.py --write
```

然后打开：

- `data/observability/latest_solution_insight_snapshot.json`
- `data/observability/latest_solution_insight_report.md`

讲解重点：

1. formal path 和 shadow path 被并排展示
2. provider trace 能看出 CRM / Ticket / BI / Knowledge 是否成功
3. fallback reasons 被单独拉出来，方便解释为什么需要人工确认
4. report 明确写出 shadow does not affect formal answer

## 5. 如何解释 fallback_recommended=true

可以这样说：

- 这不是系统失败，而是系统主动把风险暴露给人工确认
- 触发原因可能是证据不足、边界阻塞或检索错误
- 这样做比让模型“硬编一个答案”更可靠

## 6. 如何解释 Runtime Governance v0.1

可以直接说明：

- 这是 portfolio-grade prototype
- Runtime Governance v0.1 增加了 `run_id` / `trace_id`、trajectory events、permission presets、estimated cost、trajectory evaluation、human review trigger、fallback recovery 和 model provider abstraction
- 当前没有真实 IAM、不可变审计日志、真实企业写入、真实人工评分或真实 ROI
- deterministic mode 是 demo 友好模式，不是生产质量保证
- ROI metric framework 是未来 pilot 的指标框架，不是当前业务结果

## 7. 2 分钟项目展示版本

“这个项目的核心价值不是让模型一次性写出漂亮报告，而是把销售分析拆成可审计的步骤。我们先做正式 Retrieval Benchmark，确认边界和证据质量；再做 Solution Insight Service，把检索、fallback、LLM 输出和人工确认串起来；最后用 CLI 和 FastAPI 包装成一个能实际展示的产品。它的亮点是能解释、能复现、能保留失败边界。”

## 8. 5 分钟深度技术展示版本

1. 业务问题：销售分析很容易把“看起来对”的内容当成“可证明对”的内容
2. 解决方案：用 formal retriever + structured output + fallback 机制约束模型
3. Benchmark：先把 retrieval 的质量和边界讲清楚，再决定是否往上游接
4. Shadow：hierarchical retrieval 只做 debug，避免污染正式结果
5. Service：CLI 和 FastAPI 都复用了同一个 service
6. 稳定性：deterministic mode 让 demo 在无 key 情况下可重复
7. 结论：项目不是“已经全面上线”，而是“具备可信的工程原型和清晰的演示路径”
