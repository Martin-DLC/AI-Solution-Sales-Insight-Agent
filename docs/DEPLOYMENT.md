# Deployment Guide

这是一个最小部署说明，目标是本地可跑、云服务器可演示，不追求复杂运维。

## Local Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Cloud Server Run

在普通 Linux 服务器上也可以直接使用 `uvicorn`：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

如果需要 systemd，可以把它包装成一个普通服务进程。最小原则是：

- 由 systemd 拉起 `uvicorn`
- 把 `.env` 放在受控目录
- 不把 API key 写进仓库
- 保持正式 retrieval 行为冻结

## Environment Variables

常见环境变量：

- `HIERARCHICAL_RETRIEVAL_MODE=off|shadow`
- `llm_mode=deterministic|auto` 由请求或 CLI 控制

如果没有 API key，deterministic mode 仍可运行。

## Health Check

```bash
curl http://127.0.0.1:8000/health
```

## Common Questions

### 1. 没有 API key 能不能跑？

能。默认 deterministic mode 不依赖 API key。

### 2. shadow 会不会改变正式答案？

不会。shadow 只进入 debug。

### 3. formal retriever 默认会不会变？

不会。正式默认行为保持冻结。

### 4. 当前是不是生产系统？

不是。它是 portfolio-grade prototype，适合展示架构和工程能力。

