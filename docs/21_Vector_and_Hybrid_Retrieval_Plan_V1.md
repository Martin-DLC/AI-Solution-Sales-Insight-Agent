# Vector and Hybrid Retrieval Plan V1

## 1. Lexical Baseline现状

- `lexical_v1` 当前指标：
  - `recall@1 = 0.25`
  - `recall@3 = 0.703125`
  - `recall@5 = 0.921875`
  - `precision@3 = 0.9375`
  - `precision@5 = 0.796875`
  - `MRR = 1.0`
  - `forbidden_hit_rate = 0.0`
  - `solution_boundary_violation_rate = 0.4375`
- 当前 `eligible_for_rag = false`
- 当前失败案例：
  - `RET-001`
  - `RET-002`
  - `RET-003`
  - `RET-004`
  - `RET-005`
  - `RET-006`
  - `RET-009`

## 2. 为什么进入Vector与Hybrid实验

Lexical 基线已经提供了一个可解释、可复现、零模型依赖的基准线，但它仍然受到纯词项匹配的局限。下一步需要在不改变 Gold 数据、知识库和评测口径的前提下，引入向量检索与 Hybrid 检索，观察是否能在召回和边界控制之间取得更好的平衡。

## 3. 为什么选择 multilingual-e5-small

- 可在本地 CPU 模式下运行
- 同时适合中英混合查询
- Query / Passage 前缀约定成熟
- 模型体量适合作为第一轮公开 Demo 基线
- 冻结模型 revision：
  `614241f622f53c4eeff9890bdc4f31cfecc418b3`

## 4. Query 与 Passage 前缀

- Query 前缀：`query: `
- Document 前缀：`passage: `

## 5. Embedding Provider抽象

本轮建立窄接口：

- `encode_queries(texts)`
- `encode_documents(texts)`
- `provider_id`
- `dimension`

同时提供：

- `FakeEmbeddingProvider`
- `SentenceTransformerEmbeddingProvider`

默认实现不在初始化阶段加载模型，也不自动下载模型。

## 6. 为什么当前使用精确余弦而不是 FAISS

当前语料只有 40 个 Chunk。这个规模下，精确余弦检索已经足够快，而且更容易审计、测试和解释。当前没有引入：

- FAISS
- Vector Database
- Approximate Nearest Neighbor 索引

## 7. Vector Filters 与 Active Document 规则

Vector 检索必须与 Lexical 使用完全一致的：

- 文档状态过滤
- 生效日期过滤
- `document_types / industries / solution_ids / tags / statuses / effective_on`

Operational Filters 先执行，再进行向量排序。

## 8. Embedding缓存

- 缓存目录：`data/runtime/retrieval_embeddings`
- 缓存 Key 由以下信息构成：
  - knowledge base version
  - chunk id
  - chunk content hash
  - provider id
  - model name
  - normalization 配置

缓存不保存：

- API Key
- Gold IDs
- 完整 Prompt
- 本机绝对路径

## 9. RRF Hybrid算法

Hybrid 检索使用 Reciprocal Rank Fusion：

```text
score =
lexical_weight / (rrf_k + lexical_rank)
+
vector_weight / (rrf_k + vector_rank)
```

固定参数：

- `rrf_k = 60`
- `lexical_weight = 1.0`
- `vector_weight = 1.0`

## 10. 冻结参数

本轮固定：

- `top_k = 5`
- `candidate_k = 20`
- `lexical_candidate_k = 20`
- `vector_candidate_k = 20`
- `device = cpu`
- `batch_size = 16`
- `normalize_embeddings = true`

本轮不根据 16 条 case 调整权重或阈值。

## 11. 三种 Retriever 统一评测方法

`lexical_v1`、`vector_v1`、`hybrid_v1` 都将使用相同的：

- 16 条 Retrieval Cases
- Gold document / chunk IDs
- 相同 Metrics
- 相同 blocking gate

## 12. 实验纪律

- 当前尚未执行 Vector 或 Hybrid 正式实验
- 当前不生成正式 Vector / Hybrid 结果文件
- 当前不下载模型，除非后续显式允许
- 当前不默认 Vector 或 Hybrid 优于 Lexical
- 正式 `run/check` 必须从固定 revision 的本地 snapshot 离线加载
- 正式路径不得再直接用 Hub repo ID 初始化 Sentence Transformers

## 13. 数据、Gold 与 Runtime 隔离

- 只使用 6 个 Demo Solutions 与合成知识库
- 不修改 Knowledge Documents、Chunks、Manifest
- 不修改 16 条 Retrieval Cases 与 Gold IDs
- Runtime 缓存仅写入 `data/runtime`

## 14. 当前限制

- 当前没有 Vector Database
- 当前没有 Reranker
- 当前没有接入 Architecture C
- `model_revision` 已固定到冻结 commit
- 正式路径依赖本地 snapshot、`local_files_only=True` 与离线环境变量三重防线

## 15. v1.2D2真实实验步骤

下一轮真实实验将：

1. 确认 sentence-transformers 依赖可用
2. 确认本地模型是否存在
3. 在同一 16 条 Case 上运行 `vector_v1`
4. 在同一 16 条 Case 上运行 `hybrid_rrf_v1`
5. 生成正式结果与 comparison artifacts
6. 对比 `lexical_v1 / vector_v1 / hybrid_v1`
