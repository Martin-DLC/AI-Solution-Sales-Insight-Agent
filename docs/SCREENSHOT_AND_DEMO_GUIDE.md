# Screenshot and Demo Guide

## Purpose

这份文档用于指导如何为公开仓库补充截图和 demo recording，不涉及新的功能开发或结果重跑。

## Recommended Screenshots

建议至少准备三张截图：

1. `/demo` 首页或输入态
2. `/demo` 跑完 SaaS 示例后的结果态
3. `/human-eval` 的 case review 页面

建议文件路径：

- `docs/assets/web-demo-home.png`
- `docs/assets/web-demo-result.png`
- `docs/assets/human-review-case.png`

## Screenshot Tips

### 1. Web Demo Home

建议展示：

- 左侧输入表单
- deterministic mode 默认选项
- shadow retrieval 开关
- demo 页顶部说明

### 2. Web Demo Result

建议展示：

- requirement summary
- evidence cards
- fallback status
- enterprise context
- skill trace
- shadow debug

### 3. Human Review Case

建议展示：

- case 信息
- 结构化输出
- 人工评审表单或提交区域

## Demo Recording Outline

建议录屏时长控制在 2 分钟左右：

0:00 - Project overview  
0:20 - Open Web Demo  
0:40 - Load SaaS Example  
1:00 - Show generated insight  
1:20 - Show evidence / fallback / enterprise context  
1:40 - Show skill trace / shadow debug  
2:00 - Show human review workflow

## Recording Notes

- 使用 deterministic mode，确保结果稳定
- 明确说明 shadow retrieval 只用于 debug
- 明确说明 fallback 表示需要人工确认，而不是系统崩溃
- 不在录屏中展示任何 API key、真实客户数据或本机敏感路径

## Before Capturing

建议先确认：

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/python scripts/run_retrieval_benchmark_v2.py --check
```

然后启动：

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
