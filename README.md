# Energy Agent Diagnosis

一期后端采用 FastAPI 模块化单体，保留 gateway、agent、retrieval、tool 和 memory
逻辑边界。Phase 1–6 后端包含诊断主链路、完整混合 RAG、人工协作、案例生命周期、
异步索引、图谱增强和试点硬化；Phase 7 已完成前端 MVP 与产品闭环。

Phase 7 已在 `frontend/` 中提供能源诊断工作台。浏览器只访问 Next.js BFF，
由服务端代理向 FastAPI 注入内部认证信息；内部 API Key 不进入浏览器 bundle。

## Local verification

```bash
uv sync
make up-phase3
make migrate
make phase3-check
```

Run the application with:

```bash
uv run uvicorn energy_agent.app:app --reload
```

健康检查端点为 `GET /health/live` 和 `GET /health/ready`。

## Phase 7 frontend

本地开发：

```bash
make up-phase7-dev-deps
make migrate
make backend-dev
make frontend-install
make frontend-dev
```

`backend-dev` 和 `frontend-dev` 都支持热更新。日常代码修改不需要重建镜像；只有
Dockerfile、系统包或依赖锁文件变化时才重建对应镜像。

完整 Compose 拓扑为 `browser → frontend → backend`：

```bash
make up-phase7
make migrate
```

前端单项检查和契约生成：

```bash
make openapi-export
make frontend-generate-client
make frontend-lint frontend-typecheck frontend-test frontend-build
```

服务端变量见 `.env.example`。`BACKEND_INTERNAL_API_KEY` 不得改为
`NEXT_PUBLIC_*`；生产模式不提供浏览器角色切换。

## Phase 3 operations

文档同步入库：

```bash
uv run python -m energy_agent.retrieval.ingestion.cli manual.docx \
  --doc-id MANUAL-PCS-001 \
  --version 1.0 \
  --device-type PCS \
  --device-model SC5000 \
  --manufacturer EnergyCo \
  --alarm-name 温度告警 \
  --approved \
  --effective
```

已审核工单同步索引：

```bash
uv run python -m energy_agent.retrieval.ingestion.index_tickets
```

真实模型和可观测性验证：

```bash
make smoke-model
make smoke-embedding
make smoke-reranker
make smoke-rag-live
make smoke-langfuse-rag
```

本地密钥只写入被 Git 忽略的 `.env`。可提交的变量清单和安全默认值见
`.env.example`。BGE-M3 固定验证 1024 维，reranker 使用
`BAAI/bge-reranker-v2-m3`，生成模型通过 OpenAI Responses API 调用。
