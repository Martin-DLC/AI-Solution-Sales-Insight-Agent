# Demo and Reproduction Guide V1

## 1. Demo 目标

这份指南面向招聘展示和现场复现，目标是让观看者快速理解：

- 这个项目解决什么问题
- Architecture C 为什么比单 Prompt 更可控
- 为什么最终结果仍然需要 Human Review
- 如何安全地运行 Dry Run 和 Live Run

## 2. 环境要求

- Python 3.11
- 项目内 `.venv`
- Git 仓库根目录
- 不需要网络即可完成 Dry Run
- Live Run 需要本地 `.env`

## 3. 安装与初始化

先确认项目环境可用：

```bash
./scripts/preflight.sh
```

如果只是演示 Workflow 和文档，不必先跑 Live Run。

## 4. Dry Run

Dry Run 是推荐的第一步：

```bash
python scripts/run_workflow_c.py --case DEV-01
```

Dry Run 的行为是：

- 不读取 API Key
- 不创建 LLM Client
- 不调用真实模型
- 不调用 Graph 的 live 执行路径
- 不产生 API 成本

Dry Run 的用途：

- 验证案例名称
- 验证 Workflow 版本
- 查看节点清单
- 确认运行入口可用

## 5. Live Run

Live Run 需要显式开启：

```bash
python scripts/run_workflow_c.py --case DEV-01 --live
```

Live Run 的行为是：

- 读取本地 `.env`
- 使用 DeepSeek OpenAI-compatible API
- 产生真实 Token 成本
- 保存运行产物到 `data/runtime`

Live Run 的注意事项：

- 不要提交 `.env`
- 不要在演示中暴露 API Key
- 不建议在面试现场把整条 Live Run 作为唯一演示手段

## 6. 如何查看安全运行元数据

推荐优先看这些内容：

- `run_metadata.json`
- `workflow_state.json`
- `final_validation_result.json`
- `report_draft.json`

这些文件应该能帮助观看者理解：

- 运行是否成功
- 在哪个节点停止
- 为什么停止
- 是否生成最终报告

## 7. 如何解释结果

当你展示这个项目时，建议把重点放在“合同和边界”上，而不是“模型多会编”上。

可以这样解释：

- A 是最快的，但控制最弱
- B 把结构化结果做强了，但一次性大报告仍不稳定
- C 把错误拆成多个节点后，定位更清晰，审计更强
- 但是 C 的 live 端到端结果还没有稳定到可以假装生产可用

## 8. 常见失败类型

- JSON parse
- schema validation
- evidence reference
- cross-node business rule
- candidate boundary
- final validation
- API / network

遇到失败时，不要把错误解释成“模型偶尔发挥失常”就结束，而要指出：

- 是哪一层失败
- 是否继续下游
- 是否进入 Human Review
- 是否保留诊断留痕

## 9. 数据安全说明

安全边界要讲清楚：

- `data/runtime` 被 Git 忽略
- `.env` 不应提交
- Hidden Reference Pack 不作为运行时输入
- Live CLI 不打印完整 Prompt 和模型回答
- 所有最终输出都要经过 Human Review

## 10. 面试现场演示建议

推荐顺序：

1. 展示 README 首页和 Architecture C 简图
2. 运行 Dry Run
3. 展示 A/B/C 实验总结
4. 展示系统架构与 Workflow
5. 展示 Failure Taxonomy
6. 展示 Demo / Live 运行指南

不建议：

- 现场直接进行 11 次真实 API 调用
- 展示 `.env`
- 展示完整客户原文
- 展示 Hidden Reference Pack
- 把网络稳定性作为核心演示环节

