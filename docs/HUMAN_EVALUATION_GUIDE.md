# Human Evaluation Guide

## Purpose

这套 Human Evaluation Layer 用于补充现有自动规则评测，帮助人工评审从业务、证据、风险和产品思维角度审阅 Solution Insight Agent 的输出。

注意：

- 当前只提供 review packet、annotation template 和 summary 流程
- 当前 `human_review_status = not_started`
- 不得把空 annotation 当作已完成评审

## Scoring Rubric

六个维度都使用 1-5 分，最终：

`overall_human_score = 六个维度平均分 × 20`

满分 100。

### 1. Business Relevance

- 1 分：明显没有抓住客户业务目标，输出和 AI 解决方案场景关系弱
- 3 分：能理解大方向，但聚焦点不够准，业务语义较泛
- 5 分：准确理解业务目标，聚焦在合理的 AI 方案场景
- 常见扣分项：
  - 只复述用户输入
  - 方向太泛，没有落到 AI 解决方案语境
- 示例评语：
  - “理解了销售转化和客户成功两个目标，但优先级还不够清晰。”

### 2. Evidence Grounding

- 1 分：明显脱离正式 evidence，或混入未检索内容
- 3 分：基本依赖 evidence，但证据和结论的连接还不够稳
- 5 分：明确基于正式 evidence，且没有把 shadow debug 当正式证据
- 常见扣分项：
  - 把 shadow / debug 内容当正式引用
  - 用证据覆盖不到的内容做强结论
- 示例评语：
  - “证据引用方向正确，但方案建议和证据之间的映射还能更明确。”

### 3. Risk & Fallback Appropriateness

- 1 分：证据不足时仍过度承诺，风险表达缺失
- 3 分：能提到风险，但 fallback 触发和表述不够克制
- 5 分：证据不足时清楚 fallback，没有过度承诺
- 常见扣分项：
  - 明明证据不足却给出确定性承诺
  - 没有把人工确认讲清楚
- 示例评语：
  - “fallback 触发是合理的，但仍可更明确指出需补充哪些信息。”

### 4. Actionability

- 1 分：建议抽象，难以指导售前或产品下一步
- 3 分：有方向，但执行性一般
- 5 分：建议可执行，能指导售前 / 产品 / 业务下一步
- 常见扣分项：
  - 只有方向没有动作
  - 下一步过于笼统
- 示例评语：
  - “试点路径是有的，但优先试点对象和落地前提还能更具体。”

### 5. Communication Quality

- 1 分：中文表达混乱，不适合业务阅读
- 3 分：基本清晰，但不够自然或略机械
- 5 分：中文表达清晰、克制、适合业务人员阅读
- 常见扣分项：
  - 术语堆砌
  - 语气过度技术化
- 示例评语：
  - “整体表达清楚，但部分句子可以更像面向业务人员的建议。”

### 6. Product Thinking

- 1 分：没有体现约束、边界或确认项
- 3 分：提到了边界，但产品落地意识一般
- 5 分：体现约束、边界、确认项和企业落地思维
- 常见扣分项：
  - 忽略实施前提
  - 不区分 demo 和企业落地条件
- 示例评语：
  - “有边界意识，也能指出人工确认节点，比较像真实企业项目推进方式。”

## Pass / Fail Suggestion

建议：

- `overall_human_score >= 70` 可标为 `pass`
- `overall_human_score < 70` 可标为 `fail`

这只是建议，不是强制规则。评审者可以结合 notes 做最终判断。

## Review Workflow

1. 运行 packet builder 生成 review packet 和 annotation template
2. 人工阅读 packet
3. 填写 annotation template
4. 运行 summary 脚本生成汇总

## Commands

```bash
python scripts/build_solution_insight_human_eval_packet.py
python scripts/build_solution_insight_human_eval_packet.py --write
python scripts/build_solution_insight_human_eval_packet.py --check

python scripts/summarize_solution_insight_human_eval.py
python scripts/summarize_solution_insight_human_eval.py --write
python scripts/summarize_solution_insight_human_eval.py --check
```
