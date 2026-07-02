# Retrieval Metadata Blind Authoring Protocol v2.1

## 为什么当前合同仍是P1

- Runtime Boundary Contract 当前仅是 P1：content explainable but not blind validated。
- `runtime_scope_match_mode` 的规则可以被设计为不读取 Gold，但当前并未完成盲标、冻结与独立评估。
- 在盲标完成前，Metadata v2.1 不能正式版本化，Retriever v2 不能实现，Architecture C 继续 blocked。

## Blind Authoring目标

- 仅基于 Knowledge Base 内容与静态 Metadata 生成盲标包。
- 将原始 Document / Chunk ID 与 authoring 视图隔离。
- 让人工作者先给出静态标签，再进入冻结与独立评估。

## Packet允许的数据来源

- Knowledge Documents v2
- Knowledge Chunks v2
- Demo Solution Scope
- Knowledge Base Manifest v2
- 与 Document / Chunk Schema 相关的静态定义

## 禁止的数据来源

- Retrieval Cases
- Queries
- Evaluation Gold
- Formal Results / Summaries / Comparison
- Failure Taxonomy 与 Diagnosis
- Candidate Generation / Separability / Runtime Contract 冲突分析

## Opaque ID设计

- Opaque ID 使用 `retrieval_metadata_blind_authoring_v2_1` 与 source ID 做 SHA-256 截断，得到稳定但无业务语义的 blind authoring 标识。
- Blind Bundle 中只出现 opaque ID。
- 原始 ID 与 opaque ID 的双向映射只保存在密封 Mapping 文件中，不能带入 blind bundle。

## Document Default + Chunk Override

- 先判断 Document 默认值。
- 再判断某些 Chunk 是否需要覆盖 Document 默认值。
- 如果不能仅凭内容与静态 Metadata 确定，应标记 `manual_review_required`。

## 三种mode定义

### primary_in_scope

- 当证据主要服务某个 primary solution。
- 即使文档同时提到其他方案，只要该 primary solution 在 Runtime scope 中，证据即可安全使用。

### full_applicable_scope

- 只有当 Candidate 声明的全部 applicable solutions 同时位于 Runtime scope 中，证据才安全使用。

### global_reusable

- 证据不依赖具体 solution 组合，在允许的 document type、行业、时间等条件下可全局复用。

## 人工审核条件

- multi-solution 语义不清晰
- cross-cutting requirement 既像共享前置条件又像局部边界
- Document 默认值与某个 Chunk 的具体语义明显不同
- 作者无法仅根据知识内容判断静态模式

## Label Freeze流程

1. 先基于 blind bundle 独立赋值。
2. 提交空白模板的完整填充版本。
3. 在冻结前不得回看 Cases、Gold 或正式结果。
4. 先冻结标签，再进行独立评估。

## 为什么标签完成前不能加载Cases和Gold

- 一旦作者在赋值阶段看到 Case、Query 或 Gold，标签就不再是 blind authoring。
- 当前阶段必须把知识内容判断与评测结果完全隔离。

## 为什么当前Codex会话不能承担盲标

- 当前会话已经知道 Runtime Contract 的分析背景。
- 因此本会话只能构建 blind authoring packet，不能执行真正盲标。

## 新会话与隔离目录要求

- 盲标应在新会话中进行。
- 新会话只读取 blind bundle，不读取 mapping、cases、gold 或 results。
- 隔离目录必须先于任何评估工具开放。

## 标签提交必须先于评估

- 任何 retention / boundary / recall 评估都必须发生在标签冻结之后。

## 失败后禁止回改同一批标签

- 如果冻结后评估失败，不应在同一批标签上继续回改。
- 应开启新版本 blind authoring round，而不是污染已冻结标签。

## RET2-015/016仍是独立Recall问题

- Blind Authoring 只能验证 Metadata 侧静态合同是否可行。
- RET2-015 / RET2-016 仍属于 candidate recall 问题，不会因本 packet 自动消失。

## Architecture C继续blocked

- 在 blind authoring、label freeze 与独立评估完成前，Architecture C 仍然 blocked。
