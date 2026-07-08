# GitHub Agent Project Benchmark

> 更新时间：2026-07-08  
> 研究范围：GitHub 上与 enterprise agent、RAG agent、skills/tools、MCP、evaluation、deployment 最相关、且对本项目 v0.3 有直接借鉴价值的开源项目。  
> 说明：本分析优先看“可借鉴工程价值”，不是单纯按 star 排名。

## 1. Why This Benchmark Exists

AI Solution Sales Insight Agent 已经具备：

- Solution Insight Agent Service
- CLI / FastAPI
- Formal Retrieval Benchmark v2
- Shadow Hierarchical Retrieval
- Skills Registry
- MCP-style Enterprise Context Mock
- LLM Evaluation Harness
- Provider Comparison Framework
- Fallback / Human Confirmation

下一步不再只是“继续加功能”，而是要回答更具体的问题：

1. Skills Registry 要不要继续抽象成 Tool Interface
2. MCP Mock 是不是该直接接真实 MCP SDK
3. LLM Evaluation 是否该进入人工评分集
4. Shadow Retrieval 是否值得做更强 observability
5. 当前 README / Demo 是否已经足够支撑作品集展示
6. 是否需要一个简单前端

下面这份 benchmark 的目的，就是用同类开源项目的公开设计，反推我们自己的 v0.3 backlog。

## 2. Selected Projects

本轮对标的 7 个项目：

1. OpenAI Agents SDK  
   GitHub: [openai/openai-agents-python](https://github.com/openai/openai-agents-python)
2. LangGraph  
   GitHub: [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph)
3. AutoGen  
   GitHub: [microsoft/autogen](https://github.com/microsoft/autogen)
4. Semantic Kernel  
   GitHub: [microsoft/semantic-kernel](https://github.com/microsoft/semantic-kernel)
5. CrewAI  
   GitHub: [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI)
6. Haystack  
   GitHub: [deepset-ai/haystack](https://github.com/deepset-ai/haystack)
7. Onyx  
   GitHub: [onyx-dot-app/onyx](https://github.com/onyx-dot-app/onyx)

---

## 3. Benchmark Matrix

| Project | Use Case | Agent Framework | Tools / Skills | RAG | Evaluation | MCP / External Systems | Deployment | Relevance Score | Key Takeaway |
|---|---|---|---|---|---|---|---|---:|---|
| OpenAI Agents SDK | General-purpose agent workflows | Lightweight SDK with agents, handoffs, tools, guardrails | Strong tool abstraction, MCP, tracing, sessions | Optional, not RAG-first | Tracing + guardrails, but app-level eval left to user | MCP supported directly | SDK-focused, examples/docs strong | 5 | Tool interface、guardrails、human-in-the-loop 的抽象很值得学 |
| LangGraph | Stateful / resilient long-running agents | Graph-based orchestration | Subgraphs, branching, persistence patterns | Optional, user-defined | Strong observability story via LangSmith | Integrates through ecosystem rather than MCP-first | Production/deployment story mature | 5 | Durable execution + memory/persistence + observability 的组合很强 |
| AutoGen | Multi-agent orchestration and MCP demos | Multi-agent framework | AgentTool, MCP server workbench | Optional | More framework-level than app-specific | MCP examples clear | Good examples, but project now maintenance mode | 3 | MCP 接入样例可借鉴，但不适合重仓依赖 |
| Semantic Kernel | Enterprise agent orchestration | SDK / orchestration framework | Plugins, planners, memory, process framework | Strong connector/vector integrations | More enterprise platform oriented | MCP + OpenAPI + plugins | Enterprise-oriented, cross-language | 5 | Plugin / tool 接口和“business process as workflow”很有参考价值 |
| CrewAI | Multi-agent business workflows | Crews + Flows | Skills, memory, guardrails, human review | Optional knowledge sources | Control-plane / observability emphasis | Docs MCP server + enterprise integrations | Cloud / on-prem story成熟 | 4 | “Flows for deterministic steps” 很接近我们当前设计方向 |
| Haystack | Production-ready RAG & agents | Modular pipelines + components | Consistent component interface | Very strong | Built-in evaluation components | Broad ecosystem integrations | Docker/docs/examples complete | 5 | Retrieval、routing、memory、evaluation 的模块化边界值得借鉴 |
| Onyx | Enterprise AI chat / agentic RAG platform | Full application platform | Connectors, custom agents, UI-centric workflows | Core capability | Benchmark mentioned, product telemetry strong | 50+ connectors and MCP | Docker/K8s/Helm/cloud guides | 4 | 企业级“connectors + audit + RBAC + UI” 视角很有价值 |

---

## 4. Project-by-Project Breakdown

### 4.1 OpenAI Agents SDK

- `project_name`: OpenAI Agents SDK
- `GitHub URL`: [openai/openai-agents-python](https://github.com/openai/openai-agents-python)
- `one_line_summary`: 一个轻量但完整的 multi-agent workflow SDK，强调 tools、guardrails、handoffs、sessions 和 tracing。
- `target_use_case`: 通用 agent workflows，从单 agent 到 multi-agent，再到带 sandbox / MCP 的工具型代理。
- `agent_architecture`: 以 agent 为中心，围绕 instructions、tools、handoffs、guardrails 组织。
- `workflow_design`: 更偏 SDK 风格，不强制图式 workflow；通过 handoff / agents-as-tools 组合复杂流程。
- `skills_or_tools_design`: 这是它最强的部分。工具抽象很清楚，而且直接把 MCP 作为一等工具类型。
- `MCP_or_external_system_integration`: 原生支持 MCP；README 里明确把 tools 定义为 functions、MCP、hosted tools。
- `RAG_or_retrieval_design`: 不以 RAG 为中心，需要开发者自己接。
- `memory_design`: 有 session 概念，能自动管理跨 runs 的会话状态。
- `evaluation_design`: 更强调 tracing / guardrails；应用级质量评测仍需要业务方自己建立。
- `fallback_or_guardrails`: guardrails、人类参与、trace 都很明确。
- `API_or_UI`: SDK + 文档 + 示例，而不是完整 app。
- `deployment`: 偏 SDK 集成，不是完整产品 deployment 框架。
- `README_quality`: 很强，核心概念清楚，examples 与 docs 指向明确。
- `what_we_can_learn`:
  - 统一 Tool Interface
  - Guardrails 显式化
  - sessions / traces 作为一等能力
  - MCP 不应只是“未来可能接”，而应有明确 adapter 边界
- `what_not_to_copy`:
  - 不要为了对齐 SDK 而重构掉我们现在已经稳定的 service / retriever 结构
  - 不要直接把 generic multi-agent 复杂度带进当前 portfolio prototype
- `relevance_to_our_project`: 很高。最适合借鉴的是 tool abstraction、tracing、human-in-the-loop，而不是照搬 agent runtime。

### 4.2 LangGraph

- `project_name`: LangGraph
- `GitHub URL`: [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph)
- `one_line_summary`: 面向 stateful、resilient、long-running agent workflows 的图式编排框架。
- `target_use_case`: 长流程 agent、需要 durable execution、memory、human review、resume 的系统。
- `agent_architecture`: Graph-first，状态和节点编排是核心。
- `workflow_design`: 非常成熟，尤其适合复杂 branching、subgraph、resume、checkpoint。
- `skills_or_tools_design`: 不是我们当前意义上的 skills registry，但状态机 + graph node 的工程感很强。
- `MCP_or_external_system_integration`: 不是 README 主角，更多通过 LangChain 生态整合。
- `RAG_or_retrieval_design`: 不是固定实现，但很适合做 retrieval + generation + validation 组合。
- `memory_design`: 很强，明确强调 short-term / long-term memory、persistence。
- `evaluation_design`: 通过 LangSmith 走强 observability / eval / production visibility。
- `fallback_or_guardrails`: human-in-the-loop 做得很清楚。
- `API_or_UI`: 核心是框架；上层 observability / deployment 更依赖 LangSmith。
- `deployment`: 对 stateful production agents 的叙事很完整。
- `README_quality`: 强，文档体系成熟。
- `what_we_can_learn`:
  - 如果我们未来从轻量 skills 走向更复杂 orchestration，图式 workflow 是自然升级路径
  - shadow retrieval / fallback / final validation 这类分支很适合图式表达
  - observability 不能只看最终 response，要能看 node / state transition
- `what_not_to_copy`:
  - 当前不适合为了“更先进”把现有 service 直接改造成 LangGraph 风格
  - 我们现在最需要的是最小增量，而不是新 runtime
- `relevance_to_our_project`: 很高，但更像 v0.4+ 的演进参考，而不是马上替换当前 service。

### 4.3 AutoGen

- `project_name`: AutoGen
- `GitHub URL`: [microsoft/autogen](https://github.com/microsoft/autogen)
- `one_line_summary`: 面向 multi-agent 协作与 MCP 工具接入的老牌框架。
- `target_use_case`: multi-agent 协作、tool use、MCP demo。
- `agent_architecture`: assistant agents + tool agents + orchestration。
- `workflow_design`: 适合做多 agent 交互，但不是我们当前最优先的问题。
- `skills_or_tools_design`: `AgentTool` 和 MCP workbench 的例子很直观。
- `MCP_or_external_system_integration`: 有清晰 MCP server 示例，甚至直接给了 Playwright MCP 的接法。
- `RAG_or_retrieval_design`: 不是它的重心。
- `memory_design`: 有一定能力，但不是现在我们关心的差异点。
- `evaluation_design`: 偏框架层，业务评测仍靠自己搭。
- `fallback_or_guardrails`: 有一些，但不是它最强的公开卖点。
- `API_or_UI`: 框架与示例导向。
- `deployment`: 不如 newer enterprise-oriented stacks 完整。
- `README_quality`: 示例清楚。
- `what_we_can_learn`:
  - MCP workbench / agent-tool 的样例能帮助我们设计真实 MCP adapter
  - 工具代理与主代理分层的思路值得看
- `what_not_to_copy`:
  - 项目已处于 maintenance mode
  - 不应该把它作为主架构依赖方向
- `relevance_to_our_project`: 中等。更适合当作 MCP 接入参考样例，而不是长期框架目标。

### 4.4 Semantic Kernel

- `project_name`: Semantic Kernel
- `GitHub URL`: [microsoft/semantic-kernel](https://github.com/microsoft/semantic-kernel)
- `one_line_summary`: 企业级 agent orchestration SDK，强调 plugins、process framework、multi-provider 和 MCP。
- `target_use_case`: enterprise-ready agent / multi-agent systems。
- `agent_architecture`: plugin / process / memory / planning 组合，偏企业 workflow。
- `workflow_design`: 不只是“agent 调工具”，而是“把业务流程当作结构化过程”。
- `skills_or_tools_design`: plugin ecosystem 很成熟，支持 native code、prompt templates、OpenAPI、MCP。
- `MCP_or_external_system_integration`: 很强，而且 README 直说了 MCP / A2A / enterprise interoperability。
- `RAG_or_retrieval_design`: 通过 vector DB / connectors 组合，不是单一实现。
- `memory_design`: 有 memory 能力，但对 README 来说更强调 orchestration + plugins。
- `evaluation_design`: 不像我们这样显式 benchmark-first，但更偏 enterprise runtime quality。
- `fallback_or_guardrails`: 企业级稳定性、可观测性、process control 更受重视。
- `API_or_UI`: SDK 중심，多语言支持很强。
- `deployment`: 企业叙事完整，跨语言和生产稳定性强。
- `README_quality`: 强，目标用户明确。
- `what_we_can_learn`:
  - Skills Registry 可以逐步演进为 Tool / Plugin Interface
  - enterprise context 不该直接塞进 agent prompt，应先有 plugin-style contract
  - “process framework” 特别适合我们这种业务节点明显的系统
- `what_not_to_copy`:
  - 不要把当前项目拉成一个多语言大平台
  - 不要在作品集阶段引入过重 enterprise abstraction
- `relevance_to_our_project`: 很高，尤其对 MCP-style mock 之后的下一步很有指导意义。

### 4.5 CrewAI

- `project_name`: CrewAI
- `GitHub URL`: [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI)
- `one_line_summary`: 以 Crews + Flows 组织 agent collaboration 和 deterministic workflow 的框架。
- `target_use_case`: 需要 role-based agents + event-driven flows 的 business automation。
- `agent_architecture`: agent roles + tasks + crews；同时强调 deterministic flows。
- `workflow_design`: “Flows” 很关键，适合把确定性步骤和 agent 推理混合起来。
- `skills_or_tools_design`: 官方已经在做 agent-facing skills，说明他们把“教会 coding agent 框架模式”当一等需求。
- `MCP_or_external_system_integration`: 文档 MCP server + enterprise integration 叙事都比较完整。
- `RAG_or_retrieval_design`: 可接 knowledge sources，但不是它独有优势。
- `memory_design`: 有 memory、checkpointing、async execution。
- `evaluation_design`: 更偏 control plane、tracing、analytics。
- `fallback_or_guardrails`: human review、structured outputs、deterministic steps 都在强调。
- `API_or_UI`: 框架 + enterprise plane。
- `deployment`: on-prem / cloud 叙事成熟。
- `README_quality`: 很强，尤其是场景化说明和 docs 路径。
- `what_we_can_learn`:
  - Deterministic workflow 与 agent reasoning 应该长期并存，而不是二选一
  - Skills / docs / examples 面向“如何被其他 agent 正确使用”这一点很值得学
  - observability dashboard 价值很大
- `what_not_to_copy`:
  - 不要为了“multi-agent”而引入并不必要的 agent proliferation
  - 当前我们的需求分析主链还不需要多个专职 agents 互相对话
- `relevance_to_our_project`: 高。很适合作为 v0.3 workflow/productization 参考。

### 4.6 Haystack

- `project_name`: Haystack
- `GitHub URL`: [deepset-ai/haystack](https://github.com/deepset-ai/haystack)
- `one_line_summary`: 一个强调 retrieval、routing、memory、generation 显式控制的生产级 RAG/agent orchestration 框架。
- `target_use_case`: production-ready RAG、agent workflows、semantic search、多模态 pipeline。
- `agent_architecture`: component/pipeline-first，而不是纯“agent persona”风格。
- `workflow_design`: 很强调 modular pipelines、conditional routing、deep customization。
- `skills_or_tools_design`: 用一致的 component interface 承载 retrieval、tool calling、evaluation。
- `MCP_or_external_system_integration`: 不是 MCP-first，但生态集成广。
- `RAG_or_retrieval_design`: 这是它最值得学的部分，特别是 context engineering 和 retrieval modularity。
- `memory_design`: 有，但不是唯一核心。
- `evaluation_design`: README 明确把 evaluation 当 built-in component 类别之一。
- `fallback_or_guardrails`: 更偏 pipeline 显式控制，而不是 prompt-level guardrails。
- `API_or_UI`: 以框架为主，不是产品 UI。
- `deployment`: Docker/docs/examples 完整。
- `README_quality`: 很成熟，工程导向强。
- `what_we_can_learn`:
  - Retrieval 和 generation 必须继续解耦
  - evaluation 需要像 retrieval pipeline 一样模块化
  - 我们的 benchmark-first 路线是对的，而且应该继续强化
- `what_not_to_copy`:
  - 不要把当前项目做成通用 orchestration 框架
  - 我们更需要面向单产品闭环，而不是通用组件大全
- `relevance_to_our_project`: 非常高，尤其对 retrieval observability 和 evaluation productization。

### 4.7 Onyx

- `project_name`: Onyx
- `GitHub URL`: [onyx-dot-app/onyx](https://github.com/onyx-dot-app/onyx)
- `one_line_summary`: 一个完整的企业 AI 平台，把 agentic RAG、connectors、UI、RBAC、部署和审计整合成产品。
- `target_use_case`: 企业内部 AI Chat / Agent 平台。
- `agent_architecture`: 更偏 full application platform，而不是纯 SDK。
- `workflow_design`: 围绕 agentic RAG、connectors、research flows 和 productized usage 展开。
- `skills_or_tools_design`: custom agents + actions + connectors，而不是轻量 skill registry。
- `MCP_or_external_system_integration`: 很强，README 明确提到 50+ connectors 和 MCP。
- `RAG_or_retrieval_design`: 是核心能力之一，而且直接强调 hybrid index + agentic RAG。
- `memory_design`: 更偏产品侧 usage / history / audit，而不是研究型记忆设计。
- `evaluation_design`: benchmark 叙事存在，但产品 telemetry 和 enterprise analytics 更突出。
- `fallback_or_guardrails`: 更偏 RBAC、query history、enterprise controls。
- `API_or_UI`: 这类项目的最大差异点就是 UI 和完整产品层。
- `deployment`: Docker / K8s / Helm / cloud guides 非常完整。
- `README_quality`: 很强，产品展示力比纯框架更强。
- `what_we_can_learn`:
  - 作品集项目如果要更像“可交付产品”，最终还是需要一个简单前端或更完整 demo surface
  - connectors / RBAC / audit / analytics 是企业场景的关键
  - deployment 叙事和 enterprise features 展示可以更产品化
- `what_not_to_copy`:
  - 现在不适合往“大而全 AI 平台”方向发散
  - 我们当前体量还不需要 RBAC、SSO、query audit 这一整套
- `relevance_to_our_project`: 高，但更偏产品展示和 enterprise packaging 的参考。

---

## 5. Cross-Project Synthesis

### 5.1 我们的 Skills Registry 是否需要进一步抽象 Tool Interface？

结论：**需要，但不应在 v0.3 直接做成重型框架。**

原因：

- OpenAI Agents SDK、Semantic Kernel、CrewAI 都把 tools/plugins 当一等能力
- 我们现在的 Skills Registry 更像“内部编排层”，还不是“统一工具接口层”
- MCP-style Mock 已经证明，我们很快会遇到：
  - context provider
  - retrieval provider
  - external system adapter
  - generator / evaluator provider

因此 v0.3 更合适的方向是：

- 在 Skills Registry 之上加一个 **轻量 Tool Interface / Context Provider Interface**
- 不重构掉现有 skills
- 先把 EnterpriseContext 这类外部数据源抽象出来

### 5.2 MCP Mock 下一步是否应该接真实 MCP SDK？

结论：**不建议立刻接。**

原因：

- AutoGen / Semantic Kernel / OpenAI Agents SDK 都说明 MCP 是强能力，但真实 MCP 会立刻带来：
  - tool trust boundary
  - auth / secret handling
  - local command execution risk
  - observability / permission policy
- 我们当前连 enterprise context 的业务语义都还在 mock 阶段

更稳妥的顺序：

1. 继续用 mock 扩充 context contract
2. 先把 Tool Interface / Context Provider contract 稳住
3. 再接一个最小真实 MCP demo

### 5.3 LLM Evaluation 是否需要人工评分集？

结论：**需要，且这是 v0.3 P0。**

原因：

- OpenAI Agents SDK / CrewAI / LangGraph 都更强调 tracing、guardrails、human loop，而不是只看自动指标
- 我们现在的 LLM evaluation harness 仍是 rule-based
- rule-based 非常适合 baseline，但不足以评价：
  - 中文业务表达质量
  - 证据是否“说得像人话”
  - fallback 是否“合理而不僵硬”

### 5.4 Shadow Retrieval 是否需要更好的 observability dashboard？

结论：**需要，而且这是 retrieval 继续推进前的关键补强。**

原因：

- LangGraph、CrewAI、Onyx、Haystack 都在不同程度上强调 observability
- 我们已经有 formal benchmark、shadow pipeline、candidate recall experiment
- 但从作品集和工程调试角度看，当前“结果有了，观察界面不足”

### 5.5 README / Demo 是否还缺关键展示内容？

结论：**主文档已经不错，但还缺一个更“面向招聘方的对比式价值展示”。**

缺口主要在：

- “和同类 agent 项目相比，我们独特在哪”
- “为什么 boundary blind validation failed 反而是优点”
- “为什么我们没有急着接真实 MCP / fancy frontend”

### 5.6 是否需要一个简单前端，还是 FastAPI + CLI 已经够作品集展示？

结论：**FastAPI + CLI 已经足够支撑技术可信度，但如果是求职展示，简单前端是高性价比增强。**

原因：

- Onyx 这类项目的产品感来自 UI，而不是仅靠 API
- 我们已经有结构化 response，非常适合包一个很薄的 demo UI
- 但它不应先于人工评分集、retrieval observability、tool interface contract

---

## 6. v0.3 Candidate Backlog

### P0

#### 1. Human-scored LLM evaluation set

- `title`: 建立 Solution Insight 输出的人类评分集
- `why_it_matters`: 现在的 rule-based harness 能兜底，但不能真正评价业务表达、证据解释质量和 fallback 合理性。
- `expected_impact`: 让 provider comparison 从“安全比较框架”升级成“真正可用于模型选择”的依据。
- `implementation_complexity`: 中
- `suggested_scope`:
  - 选 12-20 条代表性 case
  - 定义 4-6 个人工维度
  - 输出冻结 rubric 与评分表
- `source_project_inspiration`: OpenAI Agents SDK、CrewAI、LangGraph（更重视 tracing/human review than purely automatic scores）

#### 2. Shadow retrieval observability report / mini dashboard

- `title`: 为 shadow retrieval 增加更强的可视化观察层
- `why_it_matters`: 现在 benchmark 和 recall 实验都做了，但平时调试与 demo 展示还缺“看得懂的运行时可视化”。
- `expected_impact`: 提升 retriever 迭代效率，也更适合面试展示。
- `implementation_complexity`: 中
- `suggested_scope`:
  - 按 request 输出 candidate pool 对比
  - 显示 formal vs shadow 命中差异
  - 显示 fallback 触发原因与 boundary 状态
- `source_project_inspiration`: LangGraph、CrewAI、Onyx、Haystack

#### 3. Lightweight tool / context provider interface

- `title`: 在 Skills Registry 之上补一层 Tool / Context Provider contract
- `why_it_matters`: 真实 MCP、BI、CRM、KB、future evaluators 都会需要统一外部能力接入口。
- `expected_impact`: 让 EnterpriseContextSkill、future MCP adapter、retrieval diagnostics 更可扩展。
- `implementation_complexity`: 中
- `suggested_scope`:
  - 不替换现有 skills
  - 先定义 `ContextProvider` / `ToolAdapter` 接口
  - 先让 MCP-style mock 使用这层接口
- `source_project_inspiration`: OpenAI Agents SDK、Semantic Kernel

### P1

#### 4. Thin web demo UI

- `title`: 增加一个轻量前端展示页
- `why_it_matters`: CLI / API 已经够技术验证，但对招聘方和非工程面试官来说，UI 会显著提升可理解性。
- `expected_impact`: 提升作品集展示力。
- `implementation_complexity`: 中
- `suggested_scope`:
  - 单页输入表单
  - JSON-to-card 输出
  - skill trace / enterprise context / shadow debug 可折叠展示
- `source_project_inspiration`: Onyx

#### 5. EnterpriseContext contract expansion before real MCP

- `title`: 继续扩展 mock enterprise context contract，而不是直接接真实 MCP
- `why_it_matters`: 先把上下文语义设计清楚，比先接 SDK 更有价值。
- `expected_impact`: 为真实 MCP 接入减少返工。
- `implementation_complexity`: 低到中
- `suggested_scope`:
  - 增加 account/stage/contact summary
  - 增加 ticket trend / SLA risk
  - 增加 BI KPI schema 约束
- `source_project_inspiration`: Semantic Kernel、Onyx

#### 6. Skill trace -> request timeline view

- `title`: 将 skill trace 升级成更面向产品和调试的 request timeline
- `why_it_matters`: 现在 trace 只有 executed_skills 和耗时，缺少更细的 status / output summary。
- `expected_impact`: 更容易解释“agent 是怎么一步步走出来的”。
- `implementation_complexity`: 低到中
- `suggested_scope`:
  - 每个 skill 增加 output summary
  - 区分 skipped / failed / success 原因
  - 不暴露敏感原文
- `source_project_inspiration`: OpenAI Agents SDK tracing、LangGraph observability

#### 7. Retrieval / generation split demo artifact

- `title`: 单独产出“retrieval证据链”和“generation响应”双视图 demo
- `why_it_matters`: 这是我们和很多“黑盒聊天式 agent”最大的差异点，值得更明确展示。
- `expected_impact`: 更容易向面试官说明这个项目为什么可信。
- `implementation_complexity`: 低
- `suggested_scope`: docs + demo JSON + maybe UI tab
- `source_project_inspiration`: Haystack、Onyx

### P2

#### 8. Real MCP minimal pilot

- `title`: 接一个最小真实 MCP pilot
- `why_it_matters`: 最终还是要验证 mock 到真实外部系统的替换路径。
- `expected_impact`: 提升“企业集成感”。
- `implementation_complexity`: 中到高
- `suggested_scope`:
  - 只接 1 个最小 server
  - 只做只读能力
  - 严格限制权限与 secrets
- `source_project_inspiration`: OpenAI Agents SDK、AutoGen、Semantic Kernel

#### 9. Session-level memory experiments

- `title`: 评估是否需要 session memory / conversation state
- `why_it_matters`: 如果从单次 insight 走向持续售前辅助，session memory 会变重要。
- `expected_impact`: 中
- `implementation_complexity`: 中
- `suggested_scope`: 先做 design + limited mock
- `source_project_inspiration`: LangGraph、OpenAI Agents SDK

#### 10. Frontend deployment starter

- `title`: 为 demo UI 增加最小部署模板
- `why_it_matters`: 作品集展示更顺手，但不是当前阻塞项。
- `expected_impact`: 中
- `implementation_complexity`: 中
- `suggested_scope`: Vercel/static frontend + FastAPI backend guide
- `source_project_inspiration`: Onyx

---

## 7. What We Should Not Copy Blindly

这些设计看起来很强，但不适合我们直接照搬：

1. **直接上重型 multi-agent framework**  
   当前我们的价值不在“代理数量多”，而在“检索、证据、fallback、边界控制清楚”。

2. **直接接真实 MCP SDK**  
   在 tool trust boundary、auth、permission、audit 都没收口前，直接接真实 MCP 会放大复杂度和风险。

3. **为了产品感过早堆大平台功能**  
   比如 RBAC、SSO、全套 admin plane、复杂 analytics。Onyx 值得参考，但不值得在 v0.3 全量复制。

4. **把 evaluation 交给“未来再说”**  
   Haystack / LangGraph / OpenAI Agents SDK 的公开叙事都说明：没有 observability 和 eval，agent 很难可信。

---

## 8. Final Recommendation

如果只压缩成一句话：

> v0.3 最值得做的不是“再加一个炫的 agent 能力”，而是把 **模型评测、retrieval 观测、tool/context 接口** 三件事补成真正可迭代的工程面。

对当前项目来说，最优先的路线不是“更复杂”，而是“更可比较、更可观察、更可替换”。
