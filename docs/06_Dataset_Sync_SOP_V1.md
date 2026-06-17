# Dataset Sync SOP V1

## 1. 文档目标

本文档定义 Development 与 Holdout 数据从业务源信息同步到仓库运行数据的标准流程，确保数据可审阅、可校验、可复现，并保护 Runtime Cases 与 Hidden Reference Pack 的边界。

## 2. 数据源与文件关系

- 飞书负责项目管理、摘要和原始信息提取。
- 完整 Markdown 是可审阅的业务源文档，保留案例上下文、会议纪要、销售备注、限制条件和评测参考。
- JSONL 是程序运行数据，只保存经过 Schema 校验的结构化记录。
- Runtime Cases 文件只包含运行时可见输入。
- Hidden Reference Pack 文件只包含离线 Evaluation 可见标准。

## 3. 飞书的职责

飞书用于协同收集案例、记录项目状态、提炼会议摘要和整理原始信息。飞书内容进入仓库前必须经过人工审阅，不应直接作为程序运行数据。

真实客户数据进入仓库前必须脱敏，包括公司名、个人姓名、联系方式、合同金额、系统地址、账号、API Key 和其他可识别敏感信息。

## 4. Markdown源文档的职责

Markdown 源文档是业务事实和评测参考的可读审阅层。它应完整保留案例事实、会议纪要、销售备注、已知限制、可用方案库以及隐藏评测标准。

不得把销售推测写成客户事实。销售备注中的主观判断只能作为备注、风险或评测陷阱来源，不得污染 Runtime Cases。

## 5. JSONL运行数据的职责

JSONL 是程序读取的数据格式，每个非空物理行必须是一个完整 JSON 对象。Development Cases 必须通过 `EvaluationCaseInput` 校验，Development Reference 必须通过 `HiddenReferencePack` 校验。

JSONL 不承担业务解释职责；任何语义争议应回到 Markdown 源文档审阅。

## 6. Runtime Cases与Hidden Reference Pack隔离

Cases 允许运行时读取，用于 Agent 或未来模型适配层的输入。

Reference Pack 只允许 Evaluation 读取，禁止传入运行时 Agent 上下文。运行时代码必须使用 `load_runtime_cases`，评测代码必须显式从 `dataio.evaluation_references` 导入 `load_reference_packs`。

## 7. 标准同步步骤

1. 在飞书中确认待同步案例范围和状态。
2. 将完整业务内容整理到 Markdown 源文档。
3. 人工审阅 Markdown，确认事实、备注、限制和评测参考分区清晰。
4. 将 Runtime Cases 转换为 `data/evaluation/development_cases.jsonl` 或对应数据集文件。
5. 将 Hidden Reference Pack 转换为 `data/evaluation/development_reference.jsonl` 或对应数据集文件。
6. 确认每条 JSONL 记录一行，顺序与案例列表一致。
7. 运行数据集校验脚本和完整 pytest。

## 8. Schema校验步骤

每次同步必须先运行：

```bash
./.venv/bin/python scripts/validate_seed_dataset.py
./.venv/bin/python -m pytest -q
```

如果任一步失败，停止同步并修复数据或源文档。不得静默跳过失败记录。

## 9. 人工业务语义检查

人工检查至少包括：

- Case ID、顺序和数据集划分正确。
- 会议纪要未被总结或缩短。
- 销售推测没有写成客户事实。
- Reference Pack 没有进入 Runtime Cases。
- 不新增源文档没有支持的量化事实。
- 方案白名单、黑名单、前提条件和硬性失败陷阱符合源文档。

## 10. Git提交与版本冻结

正式实验开始后要冻结数据版本。任何数据变更都必须通过独立提交记录说明原因、影响范围和是否会影响历史评测可比性。

提交前必须运行校验脚本、完整 pytest、`git diff --check` 和依赖 diff 检查。

## 11. 常见错误处理

- JSONL 行数不正确：检查是否存在空行、换行拆分或漏写案例。
- Schema 校验失败：根据错误字段回到 Markdown 源文档确认映射。
- Runtime 误读 Reference：确认路径和 loader，Reference Pack 只能由 Evaluation 模块读取。
- 发现业务语义问题：停止修改 JSONL，先修订源 Markdown 或发起人工审阅。
- 出现真实敏感信息：立即停止同步，完成脱敏后重新校验。

## 12. Holdout数据管理原则

Holdout 数据用于最终泛化评估，必须独立管理。不得根据 Holdout 结果修改 Prompt、模型策略或评测标准。

Holdout Reference Pack 必须保持隐藏，仅 Evaluation Pipeline 可读取。正式实验前应冻结 Holdout 数据版本，并避免在开发调试中反复查看标准答案。
