# Interview Talk Track

## 1. 项目背景

销售和售前场景里，最难的不是“生成文本”，而是“生成可证明、可复核、可追踪的洞察”。

## 2. 业务场景

这个 Agent 面向的是：

- AI 解决方案售前
- 企业咨询
- 需求澄清
- 方案建议
- 风险和人工确认边界

## 3. 技术架构

核心结构是：

- CLI / FastAPI 作为入口
- Solution Insight Service 作为统一业务层
- Formal Retriever 提供正式证据
- Fallback Assessor 决定是否需要人工确认
- Deterministic / LLM Generator 输出结构化结果
- Shadow retrieval 仅做诊断

## 4. 为什么做 formal benchmark

因为没有 benchmark，就很难说清楚“检索结果到底是不是可靠”，也很难区分：

- 模型不行
- 证据不够
- 规则不对
- 边界不合理

benchmark 的作用不是刷分，而是把问题拆清楚。

## 5. 为什么做 blind boundary validation

boundary validation 是为了验证“候选边界”是否真的被尊重。

它的意义是：

- 避免模型推荐范围外方案
- 避免把不可用候选当成可用候选
- 让失败被准确定位，而不是被一句“模型不稳定”糊过去

## 6. 为什么 boundary P0 failed 反而可信

因为它说明我们没有用后验信息作弊，也没有为了通过结果去放宽规则。

换句话说：

- 失败不是坏事
- 关键是失败原因是否清楚
- 清楚的失败比“看起来全都过了”更可靠

## 7. 为什么 hierarchical retrieval 解决的是 candidate model 问题

chunk-only 表示往往会漏掉文档级上下文。

hierarchical retrieval 的价值在于：

- 给候选池补上 document-level 视角
- 让 parent-child candidate pool 更完整
- 改善 candidate recall，而不是直接改写正式答案

## 8. 为什么 shadow feature flag 是正确上线方式

因为它让我们可以：

- 看见新方法带来的增益
- 但不污染正式输出
- 保持回滚简单
- 避免一刀切替换正式链路

## 9. Agent Service 如何产生业务价值

这个 service 不是只会“说话”，而是能输出：

- 需求摘要
- 业务痛点
- AI 机会点
- 推荐方案方向
- 证据链
- fallback / 人工确认建议

这让它能更像售前协作工具，而不是单纯的聊天机器人。

## 10. 如果进入企业，下一步如何推进到生产

合理顺序通常是：

1. 加强部署和监控
2. 接入企业身份和权限
3. 引入真实知识库和更多业务数据源
4. 把 fallback 和人工审批流做完整
5. 再考虑更复杂的工作流扩展

