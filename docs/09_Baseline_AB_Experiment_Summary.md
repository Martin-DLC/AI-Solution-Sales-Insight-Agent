# Baseline A/B Experiment Summary

## 1. 实验目标

本阶段对比两种最小 Baseline 架构：

- Architecture A：普通单 Prompt 文本输出。
- Architecture B：高质量单 Prompt 结构化输出。

目标不是证明业务 ROI，而是验证在当前输入数据和模型适配层下，不同输出合同对运行稳定性、可校验性和错误定位的影响。

## 2. 固定条件

- 使用同一模型：`deepseek-v4-flash`。
- 主要使用同一输入案例：`DEV-01`。
- 使用同一 Input Schema。
- Architecture B 使用 `SalesInsightReport`。
- 不使用 RAG。
- 不使用 Workflow。
- 不使用 Critic。
- 不读取 Hidden Reference Pack。
- 每次只调用模型一次。

## 3. Baseline A结果

从 `data/runtime/baseline_runs` 中读取到 3 条 Architecture A 的 `DEV-01` metadata：

| Run ID | Status | Latency ms | Prompt Tokens | Completion Tokens | Total Tokens | Raw Text |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `A-DEV-01-20260617T154710Z-96184921` | success | 27135 | 1720 | 2283 | 4003 | yes |
| `A-DEV-01-20260617T155334Z-7be2fcf3` | failed | 4142 |  |  |  | no successful output |
| `A-DEV-01-20260617T161257Z-9138338e` | success | 37113 | 1720 | 2308 | 4028 | yes |

Architecture A 不要求 JSON 或业务 Schema 校验。它可以得到普通文本分析，但无法通过程序化 Schema 判断报告是否完整、字段是否合规或错误发生在何处。

## 4. Baseline B结果

从 `data/runtime/baseline_runs` 中读取到 5 条 Architecture B 的 `DEV-01` metadata：

| Run ID | Prompt Version | JSON Success | Schema Success | Error Count | Error Category | Latency ms | Total Tokens |
| --- | --- | --- | --- | ---: | --- | ---: | ---: |
| `B-DEV-01-20260617T164904Z-ee121178` | `baseline_b_v1` | false | false |  | invalid JSON response before structured diagnostics | 61953 |  |
| `B-DEV-01-20260617T171031Z-563ee52d` | `baseline_b_v1` | false | false |  | invalid JSON at position 22066 | 79380 |  |
| `B-DEV-01-20260617T171842Z-af0704ab` | `baseline_b_v1` | true | false | 12 | Claim Type, Deal Score, NextBestAction objective | 95875 | 20422 |
| `B-DEV-01-20260617T173349Z-debe0ce7` | `baseline_b_v2` | true | false | 5 | owner enum, Risk impact length, NextBestAction expected_output length | 147553 | 25937 |
| `B-DEV-01-20260617T174742Z-14ec5cf5` | `baseline_b_v3` | true | false | 2 | unconfirmed Stakeholder missing next_validation | 79723 | 19859 |

The summarizer also found one run directory without `run_metadata.json`: `A-DEV-01-20260617T154635Z-fcd70620`. It was reported as incomplete and was not used as a successful or failed run record.

## 5. 迭代变化

- `baseline_b_v1` initially produced invalid JSON.
- A later invalid JSON failure was diagnosed at position `22066`.
- A later `baseline_b_v1` run produced valid JSON, but failed Schema validation with 12 errors.
- `baseline_b_v2` reduced Schema errors to 5.
- `baseline_b_v3` reduced Schema errors to 2.

The remaining `baseline_b_v3` errors are both `confirmed=false` stakeholders missing `next_validation`.

If future runtime files differ from this document, `scripts/summarize_baseline_runs.py` should be treated as the source for the latest metadata summary.

## 6. 架构结论

- Prompt 合同强化有效降低错误。
- JSON 合法不等于业务 Schema 合法。
- 一次调用生成超大结构化报告稳定性不足。
- 不继续创建 v4，避免针对 `DEV-01` 过拟合。
- 下一阶段进入 Architecture C 分步 Workflow。
- Architecture C 不是因为“多 Agent 更高级”，而是为了缩小单节点输出合同、支持节点级校验和失败定位。

## 7. 当前限制

- Development 数据只有 3 条。
- 当前实验主要使用 `DEV-01`。
- 尚未执行完整 Reference Pack 自动评分。
- 尚不能宣称业务效果或商业 ROI。
- 当前结论属于工程可用性初步验证。
