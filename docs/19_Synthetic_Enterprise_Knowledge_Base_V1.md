# Synthetic Enterprise Knowledge Base V1

## 1. 知识库业务目标

本阶段的目标不是实现完整 RAG，而是为后续 Retrieval Baseline 建立一套公开、合成、可重复验证的数据基础，包括：

- 公开 Demo 方案范围
- 企业知识文档合同
- 确定性 Chunk 规则
- Manifest 与版本信息
- Retrieval Evaluation 数据集

这些数据用于后续 Lexical、Vector 和 Hybrid Retrieval 的对比实验。

## 2. 为什么使用合成企业数据

当前项目禁止把真实企业知识、真实客户资料、真实合同条款或真实项目内容写入仓库。

因此本轮使用：

- `synthetic`
- `local_static`
- `public demo data`

这些数据的目标是验证方法论、检索边界和评测结构，而不是模拟真实企业资料的完整细节。

## 3. 与真实企业知识库的差异

当前知识库：

- 不接企业真实系统
- 不含真实价格
- 不含真实员工与客户信息
- 不含真实合同条款
- 不含 Embedding
- 不含 Vector Database
- 不含 Reranker

未来真实企业知识库会额外需要：

- 权限治理
- 文档生命周期管理
- 来源审计
- 多团队主数据维护
- 合规审批流程

## 4. 三层 Solution 数据模型的区别

### Case-local Available Solution Library

它来自单个 Evaluation Case 的 `available_solution_library`，作用是：

- 限制该 Case 当次允许推荐的方案集合
- 服务于 Evaluation 场景输入
- 不等于正式企业产品目录

### Demo Enterprise Solution Scope

本轮从 63 个 case-local `solution_id` 中选出 6 个，作为公开合成 Demo 范围。  
Knowledge Base、Chunk、Retrieval Benchmark 只覆盖这 6 个 ID。

### Future Enterprise Master Catalog

这应当是未来真实生产环境中的正式方案主数据，由产品、交付、商业和合规团队维护。  
本项目当前未实现这一层。

必须明确：

- 63 个 ID 不等于正式企业产品数量
- 当前选择 6 个是为了建立高质量、可评测的公开 Demo
- 这是有意控制范围，不是遗漏
- 后续扩展应通过新版本增加 Solution，而不是直接修改 v1 数据

## 5. 为什么只选 6 个 Demo Solution

如果直接把 63 个 case-local `solution_id` 全部当成企业主目录，本轮将无法在 20 份知识文档内建立高质量覆盖，也会模糊“场景候选”和“企业目录”的边界。

因此当前采用 Demo 子集策略：

- 保持数据规模可审查
- 明确范围边界
- 确保每个入选方案都能被多种知识文档充分覆盖
- 为后续 Retrieval Benchmark 提供稳定的 gold 数据

## 6. 选中的 6 个 Solution

本轮固定选择：

1. `合规政策RAG检索助手`
2. `客户身份统一与数据集成方案`
3. `商品知识库RAG方案`
4. `客服辅助回复方案`
5. `服务工单系统集成方案`
6. `私有化大模型部署方案`

选择原则：

- 都真实存在于 63 个 case-local ID 集合中
- 覆盖合规、集成、准备度、边界、案例说明等不同问题类型
- 避免高度重复命名的近似方案
- 不按“模型容易回答”来挑选

## 7. 20 个 Document 的分类与覆盖

当前知识文档总数固定为 20，覆盖 10 种文档类型：

- `solution`: 6
- `capability`: 2
- `case_study`: 2
- `implementation_playbook`: 2
- `security_compliance`: 1
- `delivery_constraint`: 1
- `integration_requirement`: 2
- `commercial_rule`: 1
- `unsupported_scenario`: 1
- `readiness_requirement`: 2

覆盖规则：

- 每个选中 Solution 至少 1 份 `solution` 文档
- 每个选中 Solution 至少被 2 份非 `solution` 文档引用
- 文档中的 `solution_ids` 不允许超出 6 个 Demo ID

## 8. Solution Library 映射

Knowledge Base 中的 `solution_ids` 来自当前 Demo Scope，而 Demo Scope 又来自 Development Cases 的 case-local 候选集合。

也就是说：

- Knowledge Base 没有发明新的 `solution_id`
- 也没有回写或修改 Development Cases
- 57 个未选中 ID 只保存在 `demo_solution_scope.v1.json` 的 `excluded_solution_ids`

## 9. Document 内容设计原则

每份文档至少强调以下项目中的 3 项以上：

- confirmed capability
- applicable condition
- unsupported condition
- prerequisite
- implementation risk
- integration dependency
- security requirement
- delivery constraint
- commercial limitation
- customer readiness requirement
- synthetic case context
- version / effective period

知识文档不是 FAQ 集合，也不应被当作客户事实来源。

## 10. Chunk 生成规则

当前 Chunk Builder 是纯代码、确定性的：

1. 优先按 Markdown 二级标题切 Section
2. Section 过长时按段落切分
3. 段落过长时按句子边界切分
4. 只在必要时做安全硬切
5. 不使用外部 Tokenizer
6. 不调用模型
7. 相同输入生成完全相同的结果

## 11. Chunk ID 与 Citation 设计

Chunk ID 使用稳定规则生成：

- `document_id`
- `chunk_index`
- `content hash`

Citation 使用：

- 文档标题
- Section 标题

这样做的目标是保证：

- Chunk ID 可重复生成
- 引用标签适合最终报告使用
- 同一文档顺序稳定

## 12. Manifest 与版本管理

Manifest 记录：

- `knowledge_base_version`
- `document_count`
- `chunk_count`
- `document_type_counts`
- `solution_ids`
- `generated_at`
- `source_mode`
- `synthetic_data`
- `validation_status`

当前固定要求：

- `synthetic_data = true`
- `source_mode = local_static`

## 13. 16 条 Retrieval Case 分布

当前固定为 16 条：

- `solution_discovery`: 2
- `capability_check`: 2
- `solution_boundary`: 2
- `implementation_risk`: 2
- `compliance_requirement`: 2
- `integration_requirement`: 2
- `customer_readiness`: 2
- `case_study_search`: 2

这些 Case 只评测 Demo Scope，不代表覆盖全部 63 个 case-local 候选方案。

## 14. Gold IDs 与 Runtime 隔离

Retrieval Evaluation 使用：

- expected relevant document IDs
- expected relevant chunk IDs
- forbidden document IDs
- required / forbidden solution IDs

这些 Gold 信息只属于离线评测。

它们：

- 不会传给 Architecture C Runtime
- 不会传给模型
- 不会作为客户事实使用

## 15. 不支持场景与方案边界

知识库专门保留了 unsupported boundary 文档，用于说明：

- 哪些需求当前不支持
- 哪些前置条件没满足时不应推荐
- 哪些能力必须保留人工复核
- 哪些方案不能被误解为自动承诺工具

这类边界文档对后续 Retrieval Benchmark 很重要，因为它们帮助我们验证“检索到不该推荐的内容”这一失败模式。

## 16. 数据安全

当前数据全部是：

- synthetic
- public demo
- local static

禁止内容包括：

- 真实客户名称
- 真实企业内部资料
- 真实员工姓名
- 真实价格
- 真实合同条款
- Hidden Reference Pack
- Runtime 路径
- API Key 或 Secret

## 17. 当前限制

当前明确还没有实现：

- 完整 RAG
- Embedding
- Vector Database
- Reranker
- Architecture C 接入
- 在线知识同步
- 真实企业主目录

## 18. v1.2C Lexical Retrieval Baseline 计划

下一步优先做：

- 基于当前 20 份文档与 40 个 Chunk 跑 Lexical Retrieval Baseline
- 使用 16 条 Retrieval Cases 做离线评测
- 记录 recall / precision / MRR / boundary violation

后续再比较：

- Lexical
- Vector
- Hybrid

这里不预设向量检索一定优于词法检索，而是用同一评测集做可比实验。
