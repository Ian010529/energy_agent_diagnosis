# Energy Agent Diagnosis

一期后端采用 FastAPI 模块化单体，保留 gateway、agent、retrieval、tool 和 memory
逻辑边界。当前 Phase 3 已包含同步知识入库、MinIO 原件存储和完整混合 RAG。

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
