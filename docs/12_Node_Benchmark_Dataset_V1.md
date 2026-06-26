# Node Benchmark Dataset V1

## 1. 文档目标

本文记录 v1.1B 节点级 Model Benchmark 数据集的文件结构、样本范围和隔离规则。

本轮只建立离线评测数据，不调用真实模型 API，不引入模型路由，也不修改 Architecture C 的业务节点。

## 2. Development Cases

正式 Development 数据集扩展为 12 条：

- `DEV-01`
- `DEV-04`
- `DEV-05`
- `DEV-06`
- `DEV-07`
- `DEV-08`
- `DEV-09`
- `DEV-10`
- `DEV-11`
- `DEV-12`
- `DEV-13`
- `DEV-14`

其中前三条保持原有内容、ID 和顺序不变。新增九条为虚构、脱敏的销售洞察评测样本，覆盖预算未知、权力未知、方案不匹配、销售备注冲突、紧急时间线、干系人分歧、集成负责人缺失、POC 就绪以及安全合规阻塞等场景。

## 3. Reference Pack

`data/evaluation/development_reference.jsonl` 与 Development Cases 一一对应，共 12 条。

Reference Pack 仍只用于离线 Evaluation，不进入 runtime fixture，不进入节点输入，也不提供给模型。

## 4. Node Benchmark Cases

节点级 Benchmark 数据位于：

```text
data/evaluation/model_benchmark/node_cases.jsonl
```

当前共 16 条，分布如下：

- `fact_extraction`: 4
- `underlying_pain`: 4
- `information_gap`: 4
- `solution_recommendation`: 4

这些样本覆盖不少于 8 个不同的 `source_case_id`，用于第一轮 4 节点、3 模型档位、每节点 4 样本的 Pilot 矩阵。

## 5. Fixture 结构

每个 Benchmark Case 指向一个独立 fixture：

```text
data/evaluation/model_benchmark/fixtures/*.json
```

Fixture 只包含目标节点真实 `required_state_fields` 所需的 runtime state。

它不包含：

- Reference Pack
- expected output
- API Key
- Secret
- `data/runtime` 历史运行内容

Assertions 存放在 `node_cases.jsonl` 中，不写入 fixture。

## 6. Assertions

每个 Benchmark Case 至少包含一个 blocking assertion。

当前断言类型覆盖：

- `json_parse_success`
- `schema_validation_success`
- `business_rule_success`
- `evidence_reference_valid`
- `candidate_boundary_valid`
- `required_value_equals`
- `forbidden_value_absent`
- `referenced_id_exists`

这些断言只描述离线评测合同，不执行任意代码。

## 7. 加载与校验

数据加载入口位于：

```text
evaluation/model_benchmark/dataset.py
```

它负责：

- 加载 Development Cases
- 加载 Reference Packs
- 加载 Node Benchmark Cases
- 加载节点输入 fixture
- 校验 fixture metadata 与 case metadata 一致
- 校验 fixture 只使用相对路径
- 校验 fixture 不包含 forbidden 字段
- 统计节点分布、source case 覆盖和 assertion 类型覆盖

## 8. 当前不做什么

v1.1B 不做：

- 不调用真实模型 API
- 不读取 `.env`
- 不读取 `data/runtime`
- 不把 Hidden Reference Pack 放入 runtime fixture
- 不修改 Architecture C 节点、Graph、Prompt 或 Schema
- 不增加新依赖
- 不做模型路由决策

## 9. 下一步

后续 v1.1C 可以基于本数据集接入实际模型配置，执行 48 次 Pilot Benchmark，并生成节点级模型路由建议。
