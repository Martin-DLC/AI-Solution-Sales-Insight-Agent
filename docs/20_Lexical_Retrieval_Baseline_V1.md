# Lexical Retrieval Baseline V1

## 1. Baseline目标

本轮建立 `lexical_v1` 作为公开合成企业知识库的第一条可解释、可复现实验基线。

目标不是追求最优召回，而是提供：

* 一个不依赖外部服务的稳定对照组；
* 一套可审计的 tokenizer、过滤规则和排序规则；
* 一份冻结结果，供后续 Vector / Hybrid Retrieval 比较。

## 2. 为什么先做 Lexical

在 v1.2C 中先做 lexical retrieval，而不是直接做向量检索，原因有三点：

* 词法基线没有模型、Embedding、索引服务或网络依赖，便于先验证知识库和评测集本身是否稳定。
* 当后续 Vector / Hybrid 结果出现变化时，lexical_v1 可以作为最低复杂度的参照系。
* 对于 Demo Scope 内的 6 个 solution_id，词法基线已经能直接暴露过滤、边界和 Gold 设计问题，不需要先把系统复杂化。

## 3. Demo Solution Scope

当前 Retrieval Benchmark 只覆盖公开合成 Demo Scope 中的 6 个 solution_id：

* `合规政策RAG检索助手`
* `客户身份统一与数据集成方案`
* `商品知识库RAG方案`
* `客服辅助回复方案`
* `服务工单系统集成方案`
* `私有化大模型部署方案`

这 6 个 ID 来自 Development Cases 中的 63 个 case-local solution candidates，但不代表未来企业正式主目录。

## 4. Mixed-language Tokenizer

`mixed_lexical_v1` 的目标是稳定、透明，而不是生产级中文分词。

规则：

* 先做 Unicode `NFKC` 规范化；
* ASCII 文本统一转小写；
* 折叠多余空白；
* 英文、数字、连字符和下划线标识符整体保留，例如 `solution-ai-ops`；
* 连续中文文本按重叠二元切分，例如 `数据治理` 生成 `数据`、`据治`、`治理`；
* 单独出现的单个中文字符保留为单 token；
* 不使用 jieba、LLM 或外部词典。

## 5. Weighted BM25 算法

本轮检索器采用确定性的本地内存 Weighted BM25：

* `k1 = 1.5`
* `b = 0.75`
* `top_k = 5`
* `score_round_digits = 6`

实现方式：

* 先对每个 Chunk 的多个字段分别分词；
* 用字段权重做 token 重复扩展；
* 基于扩展后的 token 序列计算 term frequency 和文档长度；
* IDF 基于当前知识库 Chunk corpus 一次性计算；
* 检索时先执行 operational filters，再打分排序。

排序规则固定为：

1. `score` 降序
2. `document_id` 升序
3. `chunk_id` 升序

## 6. 字段权重

固定权重如下，不根据 Gold 结果动态调参：

* `content = 1`
* `citation_label = 2`
* `tags = 2`
* `industries = 1`
* `solution_ids = 3`
* `document_type = 1`

这组权重的含义是：在 Demo Scope 中，方案 ID、引用标签和结构化标签比正文弱匹配更值得保留，但仍然维持可解释的词法逻辑。

## 7. Filters 与 Active Retrieval

当前 16 条 Retrieval Cases 实际使用的 filters 是：

* `document_types`
* `industries`

Retriever 同时支持但当前数据未使用的字段：

* `solution_ids`
* `tags`
* `statuses`
* `effective_on`

默认 Active Retrieval 规则：

* 只检索 `approved` 文档；
* 同时要求在固定 `evaluation_date = 2026-06-29` 上有效；
* `draft`、`deprecated`、`expired` 默认不进入可检索集合。

多个字段之间是 AND，同一字段多个值之间是 OR。

## 8. Failure Taxonomy

为保证 baseline 失败也能安全分析，本轮聚合以下失败类型：

* `no_relevant_hit_at_5`
* `insufficient_relevant_hits`
* `forbidden_document_hit`
* `solution_boundary_violation`
* `operational_filter_excluded_all`
* `empty_query_tokens`
* `retrieval_error`

这些标签只用于结果说明，不会自动修改检索器行为。

## 9. Frozen Artifacts

Tracked 文件：

* `data/evaluation/retrieval/lexical_baseline_config.v1.json`
* `data/evaluation/retrieval/lexical_baseline_results.v1.jsonl`
* `data/evaluation/retrieval/lexical_baseline_summary.v1.json`

命令：

* Plan: `./.venv/bin/python scripts/run_lexical_retrieval_baseline.py`
* Check: `./.venv/bin/python scripts/run_lexical_retrieval_baseline.py --check`
* Write: `./.venv/bin/python scripts/run_lexical_retrieval_baseline.py --write`

`--check` 会忽略 `latency_ms` 和 `average_latency_ms` 这类天然波动字段，其余输出必须与 tracked 结果一致。

## 10. 当前结论

`lexical_v1` 已经形成了稳定可复现的对照组，但当前 summary 中：

* `eligible_for_rag = false`

主要原因是：

* 存在 `solution_boundary_violation`
* 聚合后的 `recall_at_5` 仍未达到 `1.0`

这符合本轮目标：先冻结真实 baseline，再把它作为后续 Vector / Hybrid 的统一比较基线。
