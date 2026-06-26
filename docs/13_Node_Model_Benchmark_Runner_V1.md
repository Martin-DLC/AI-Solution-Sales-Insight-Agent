# Node Model Benchmark Runner V1

## 文档目标

本文记录 v1.1C 节点级多模型 Benchmark Runner 的最小可用闭环。该能力用于离线回放模型响应、执行真实 Architecture C 节点代码、计算节点级断言结果，并把不含真实 API 调用的运行产物保存到指定 runtime 目录。

## 范围

本版本覆盖四个节点：

- fact_extraction
- underlying_pain
- information_gap
- solution_recommendation

本版本不调用真实模型 API，不读取 `.env`，不读取 Hidden Reference Pack，不执行完整 Evaluation 评分，也不改变 Architecture C 的业务节点、Prompt、Schema 或路由逻辑。

## 核心模块

- `models.py` 定义模型配置、节点 Benchmark Case、断言、观测、运行结果、Manifest 和 Report。
- `clients.py` 提供 Replay Client，用 JSONL 中的离线响应模拟 `WorkflowJSONClient`。
- `assertions.py` 执行离线断言，包括 JSON、Schema、业务规则、Evidence、候选方案边界、字段值、禁用内容和引用 ID。
- `executor.py` 加载单个节点 fixture，运行真实节点代码，并把节点结果转换为 Benchmark 观测与运行结果。
- `runner.py` 负责批量执行 Case 与模型配置组合，支持过滤和 fail-fast。
- `storage.py` 负责写入 run manifest、report、case artifact 和 LLM call 记录。
- `scripts/run_node_model_benchmark.py` 提供 Plan、Validate 和 Replay CLI。

## CLI 模式

Plan 模式：

```bash
./.venv/bin/python scripts/run_node_model_benchmark.py
```

只输出计划，不创建 runtime 目录。

Validate 模式：

```bash
./.venv/bin/python scripts/run_node_model_benchmark.py --validate
```

只校验正式 Benchmark 数据集，不创建 runtime 目录。

Replay 模式：

```bash
./.venv/bin/python scripts/run_node_model_benchmark.py \
  --configs path/to/configs.json \
  --replay path/to/replay_records.jsonl
```

只有 Replay 模式会创建运行目录。Replay 输入必须显式提供，不支持 `--live`。

## Runtime 产物

Replay 运行会在指定 output root 下创建一次运行目录，包含：

- `run_manifest.json`
- `benchmark_report.json`
- 每个 Case 的 `artifact.json`
- 每个 Case 的 `observation.json`
- 每个 Case 的 `assertion_results.json`
- 每个 Case 的 `run_result.json`
- 每次 LLM 回放调用的 metadata、messages、raw_response 和 parsed_response

测试中必须使用临时目录，不写入真实 `data/runtime`。

## 安全边界

- 不读取 `.env`。
- 不调用真实 API。
- 不读取 Hidden Reference Pack。
- Runtime fixture 不包含 Reference Pack 或 expected output。
- 断言与 fixture 分离，避免把评测答案写入运行输入。
- Offline assertion 失败时，运行结果为 `failed`，`error_type` 为稳定的 `assertion_failure`，不会伪装成 request error。
