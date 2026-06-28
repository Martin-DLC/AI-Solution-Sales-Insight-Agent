# Enterprise Knowledge Base and RAG Plan V1

## 1. 业务目标

本阶段只建立企业知识库与 Retrieval Evaluation 的数据合同、指标合同和后续接入计划，为 Architecture C 的知识增强路线打基础。

当前目标不是上线 RAG，而是先把以下几件事定义清楚：

- 企业知识如何被结构化保存
- 检索结果如何与销售分析节点解耦
- 检索质量如何离线评测
- 哪些检索结果可以进入后续实验

## 2. 为什么当前 Lexical Solution Retrieval 不足

当前 `solution_retrieval` 只针对 `available_solution_library` 里的方案名字符串做纯代码 lexical matching。它有几个明显边界：

- 只能检索案例输入里显式给出的方案名，无法覆盖能力文档、案例文档、交付约束和合规材料
- 方案文本过短时，词面重叠不足，容易漏召回
- 无法表达“适用条件 / 不适用条件 / 前置依赖 / 风险 / 商业限制 / 信息有效期”
- 无法支持后续对 Lexical、Vector、Hybrid 的可比实验

所以 v1.2A 要先把企业知识库和检索评测合同搭起来，而不是直接假设 Vector 一定更好。

## 3. 企业知识库内容分类

当前定义 10 类知识文档：

1. `solution`
2. `capability`
3. `case_study`
4. `implementation_playbook`
5. `security_compliance`
6. `delivery_constraint`
7. `integration_requirement`
8. `commercial_rule`
9. `unsupported_scenario`
10. `readiness_requirement`

这些类型共同覆盖：

- 企业确认能力
- 适用条件
- 不适用条件
- 前置依赖
- 风险
- 案例证据
- 商业限制
- 信息有效期

知识库不是 FAQ 集合，也不应被当作客户事实来源。

## 4. 文档与 Chunk 数据合同

### KnowledgeDocument

文档级合同描述知识源的业务身份：

- `document_id`
- `title`
- `document_type`
- `status`
- `version`
- `effective_from`
- `effective_until`
- `owner`
- `summary`
- `content`
- `tags`
- `industries`
- `solution_ids`
- `source_uri`
- `confidentiality`
- `created_at`
- `updated_at`

关键约束：

- `document_id` 唯一性由集合模型检查
- `title` / `summary` / `content` 不能为空
- `content` 不能只是标题重复
- `tags` / `industries` / `solution_ids` 去重并保持顺序
- `deprecated` 与 `expired` 文档默认不进入有效检索候选
- `effective_until` 不能早于 `effective_from`
- `source_uri` 只允许项目内相对路径或 `synthetic://` URI
- 不允许 HTTP 下载 URI

### KnowledgeChunk

Chunk 级合同描述可检索粒度：

- `chunk_id`
- `document_id`
- `document_type`
- `chunk_index`
- `content`
- `token_estimate`
- `tags`
- `industries`
- `solution_ids`
- `metadata`
- `citation_label`

关键约束：

- `chunk_id` 可稳定重复生成
- `chunk_index >= 0`
- `token_estimate > 0`
- `metadata` 只允许 JSON-safe 值
- 不包含 Embedding
- 不包含模型生成答案
- `citation_label` 必须适合最终报告引用

### KnowledgeBaseManifest

Manifest 只记录版本和统计，不承载业务内容：

- `knowledge_base_version`
- `document_count`
- `chunk_count`
- `document_type_counts`
- `solution_ids`
- `generated_at`
- `source_mode`
- `synthetic_data`
- `validation_status`

当前约束：

- `source_mode = local_static`
- `synthetic_data = true`
- 当前不连接企业真实系统

## 5. Metadata 和权限边界

知识库文档必须明确元信息与权限边界：

- `document_type`：文档业务分类
- `status`：批准 / 草稿 / 废弃 / 过期
- `effective_from` / `effective_until`：有效期
- `owner`：责任团队
- `confidentiality`：仅用于本地合成演示数据边界
- `source_uri`：只指向项目内或合成来源

本阶段不接真实企业系统，不读取外部企业文档，不保存凭证。

## 6. Retrieval Query 类型

当前定义 8 类查询：

1. `solution_discovery`
2. `capability_check`
3. `solution_boundary`
4. `implementation_risk`
5. `compliance_requirement`
6. `integration_requirement`
7. `customer_readiness`
8. `case_study_search`

这些类型用于后续离线评测，不等于直接暴露给生产 Prompt。

## 7. Retrieval Evaluation 数据集

`RetrievalEvaluationCase` 当前至少包括：

- `retrieval_case_id`
- `source_case_id`
- `query_type`
- `query`
- `filters`
- `expected_relevant_document_ids`
- `expected_relevant_chunk_ids`
- `forbidden_document_ids`
- `required_solution_ids`
- `forbidden_solution_ids`
- `minimum_relevant_hits`
- `tags`
- `notes`

边界要求：

- 至少有一个 expected relevant ID
- expected 与 forbidden 不能重叠
- `minimum_relevant_hits > 0`
- query 不应包含标准答案
- query 不应包含 Hidden Reference Pack 内容
- 不包含真实客户信息

## 8. 指标和 Blocking Gate

当前纯代码指标：

- `Recall@K`
- `Precision@K`
- `Mean Reciprocal Rank`
- `Forbidden Hit Rate`
- `Solution Boundary Violation Rate`

Pilot 阶段资格门槛仅用于实验挡板，不是生产 KPI：

- `recall_at_5 == 1.0`
- `forbidden_hit_rate == 0`
- `solution_boundary_violation_rate == 0`
- 不存在 `request_error`

当前不设计生产级百分比阈值。

## 9. 与 Source Index 的区别

`Source Index` 和企业知识库必须严格分开：

- Source Index：当前客户案例输入材料的运行时证据索引
- Knowledge Base：企业内部确认的方案、能力、案例、限制和规则知识

禁止：

- 用 Knowledge Base 覆盖客户证据
- 将检索结果直接当作客户事实
- 用 RAG 替代 Source Index

## 10. 与 Solution Library 的关系

当前 `available_solution_library` 只是案例输入里的方案白名单字符串列表。

未来关系应为：

- `available_solution_library`：客户场景允许进入推荐范围的方案边界
- Knowledge Base：关于这些方案的结构化企业知识
- Retrieval：从 Knowledge Base 中找出与当前 query 最相关的知识文档或 chunk

因此：

- 不允许推荐不存在的 `solution_id`
- 不允许绕开 Solution Library 直接扩展到案例外方案

## 11. Architecture C 接入位置

未来接入链路明确为：

`AI Opportunity -> Retrieval Query Builder -> Knowledge Retrieval -> Candidate Filtering -> Rerank -> Solution Recommendation -> Citation Validation`

Risk 节点后续也可以查询：

- `implementation_playbook`
- `security_compliance`
- `delivery_constraint`
- `integration_requirement`

当前不允许所有节点都直接检索知识库。

## 12. Citation 策略

后续引用策略保持两层：

- 客户事实引用：只能来自 Source Index
- 企业知识引用：只能来自 Knowledge Base 文档 / Chunk

最终报告需要能区分“客户证据”和“企业知识依据”，避免把内部知识误写成客户明确表述。

## 13. 数据更新与版本管理

知识库数据需要显式版本化：

- 文档保留 `version`
- Manifest 保留 `knowledge_base_version`
- 检索评测数据需要独立版本与冻结快照

正式实验前应冻结：

- Knowledge Base 文档集合
- Chunk 切分策略
- Retrieval Evaluation 数据集
- 指标计算逻辑

## 14. 安全与合规

当前阶段明确：

- 没有真实企业数据
- 没有 Embedding
- 没有向量数据库
- 没有外部下载
- 没有 API Key 落盘
- 没有联网检索

后续引入真实企业资料前，必须先完成脱敏、权限和生命周期管理设计。

## 15. v1.2B 到 v1.2F 路线

建议路线：

- `v1.2B`：构造合成企业知识库数据与静态样例
- `v1.2C`：建立 Retrieval Evaluation 正式数据集
- `v1.2D`：实现 Lexical Retrieval 基线并评测
- `v1.2E`：引入 Vector / Hybrid 实验框架
- `v1.2F`：接入 Architecture C 的受控知识增强路径

后续会对 Lexical、Vector 和 Hybrid 做实验对比，不预设 Vector 一定优于 Lexical。

## 16. 当前不做什么

当前明确还没有完成：

- RAG 生产接入
- Embedding 生成
- 向量数据库
- 真实企业知识导入
- 多节点通用知识检索
- 检索结果自动写入生产报告
- 用知识库替代客户证据

本轮只建立数据与评测合同，不实现完整 RAG。
